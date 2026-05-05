import random
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from loguru import logger
from selectolax.parser import HTMLParser

from .base import BaseCollector, CollectorResult
from .schemas import FundamentosSnapshotSchema

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
with open(_SETTINGS_PATH) as _f:
    _SETTINGS = yaml.safe_load(_f)

_SCRAPING = _SETTINGS["scraping"]
_REDIS_TTL = int(_SETTINGS["redis"]["ttl_fundamentals"])

_LABEL_MAP = {
    "P/E":           "pl",
    "P/B":           "pvp",
    "Dividend %":    "dy",
    "ROE":           "roe",
    "ROI":           "roic",
    "Profit Margin": "margem_liquida",
    "Oper. Margin":  "margem_ebitda",
    "Debt/Eq":       "divida_liquida_ebitda",
    "Current Ratio": "liquidez_corrente",
    "EPS next 5Y":   "cagr_receita_5a",
    "Payout":        "payout",
    "EV/EBITDA":     "ev_ebitda",
}


class FinvizCollector(BaseCollector):

    def collect(self, ticker: str) -> CollectorResult:
        ticker = ticker.upper()
        collected_at = datetime.now(timezone.utc)

        try:
            html = self._fetch_html(ticker)
            raw_data = self._parse_table(ticker, html)
            mapped = self._map_labels(raw_data)

            schema = FundamentosSnapshotSchema(
                ticker=ticker,
                fonte="finviz",
                raw_json=raw_data,
                text_description="",
                **mapped,
            )
            description = self._build_description(ticker, schema, collected_at)
            schema = schema.model_copy(update={"text_description": description})

            fundamentals = schema.model_dump(
                exclude={"ticker", "fonte", "raw_json", "text_description"}
            )

            return CollectorResult(
                ticker=ticker,
                source="finviz",
                collected_at=collected_at,
                fundamentals=fundamentals,
                raw_json=raw_data,
                text_description=schema.text_description,
                success=True,
            )

        except Exception as e:
            logger.error(f"[finviz] {ticker} coleta falhou: {e}")
            return CollectorResult(
                ticker=ticker,
                source="finviz",
                collected_at=collected_at,
                fundamentals={},
                raw_json={},
                text_description="",
                success=False,
                error=str(e),
            )

    def healthcheck(self) -> bool:
        try:
            resp = httpx.head(
                "https://finviz.com",
                headers={"User-Agent": _SCRAPING["user_agent"]},
                timeout=10,
                follow_redirects=True,
            )
            return resp.status_code < 400
        except Exception as e:
            logger.warning(f"[finviz] healthcheck falhou: {e}")
            return False

    # ------------------------------------------------------------------

    def _fetch_html(self, ticker: str) -> str:
        cache_key = f"finviz:{ticker}"

        try:
            from src.storage.sql.redis_client import get_client
            redis = get_client()
            cached = redis.get(cache_key)
            if cached:
                logger.debug(f"[finviz] {ticker} HTML servido do cache Redis")
                return cached
        except Exception as e:
            logger.warning(f"[finviz] Redis indisponível, prosseguindo sem cache: {e}")

        delay = random.uniform(_SCRAPING["request_delay_min"], _SCRAPING["request_delay_max"])
        logger.debug(f"[finviz] aguardando {delay:.2f}s antes de requisitar {ticker}")
        time.sleep(delay)

        url = f"https://finviz.com/quote.ashx?t={ticker}&p=d"
        resp = httpx.get(
            url,
            headers={"User-Agent": _SCRAPING["user_agent"]},
            timeout=_SCRAPING["timeout"],
            follow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text

        try:
            from src.storage.sql.redis_client import get_client
            redis = get_client()
            redis.set(cache_key, html, ex=_REDIS_TTL)
            logger.debug(f"[finviz] {ticker} HTML armazenado no cache Redis (TTL={_REDIS_TTL}s)")
        except Exception as e:
            logger.warning(f"[finviz] falha ao gravar cache Redis: {e}")

        return html

    def _parse_table(self, ticker: str, html: str) -> dict:
        tree = HTMLParser(html)
        table = tree.css_first("table.snapshot-table2")
        if table is None:
            raise ValueError(f"[finviz] tabela snapshot-table2 não encontrada para {ticker}")

        cells = table.css("td")
        raw: dict = {}
        for i in range(0, len(cells) - 1, 2):
            label = cells[i].text(strip=True)
            value = cells[i + 1].text(strip=True)
            raw[label] = value

        logger.debug(f"[finviz] {ticker} — {len(raw)} campos extraídos da tabela")
        return raw

    def _map_labels(self, raw: dict) -> dict:
        mapped: dict = {}
        for finviz_label, field_name in _LABEL_MAP.items():
            try:
                value = raw.get(finviz_label)
                mapped[field_name] = value
                logger.debug(f"[finviz] {finviz_label!r} → {field_name}={value!r}")
            except Exception as e:
                logger.warning(f"[finviz] falha ao mapear campo {finviz_label!r}: {e}")
                mapped[field_name] = None
        return mapped

    def _build_description(
        self, ticker: str, schema: FundamentosSnapshotSchema, collected_at: datetime
    ) -> str:
        def pct(v):
            return f"{v * 100:.2f}" if v is not None else "N/A"

        def num(v):
            return str(v) if v is not None else "N/A"

        return (
            f"{ticker} — "
            f"P/L: {num(schema.pl)}, "
            f"P/VP: {num(schema.pvp)}, "
            f"DY: {pct(schema.dy)}%, "
            f"ROE: {pct(schema.roe)}%, "
            f"ROIC: {pct(schema.roic)}%, "
            f"Margem Líquida: {pct(schema.margem_liquida)}%, "
            f"Dívida/EBITDA: {num(schema.divida_liquida_ebitda)}. "
            f"Fonte: Finviz. Coletado em: {collected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}."
        )
