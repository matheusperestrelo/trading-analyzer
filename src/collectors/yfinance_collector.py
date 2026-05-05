import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
import yfinance as yf
from loguru import logger

from .base import BaseCollector, CollectorResult
from .schemas import CotacaoDiariaSchema

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
with open(_SETTINGS_PATH) as _f:
    _SETTINGS = yaml.safe_load(_f)

_REDIS_TTL_QUOTE = int(_SETTINGS["redis"]["ttl_quote"])


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _json_safe_dict(raw: dict) -> dict:
    """Filter dict to only JSON-serializable scalar values."""
    result = {}
    for k, v in raw.items():
        if v is None or isinstance(v, (str, bool)):
            result[k] = v
        elif isinstance(v, int):
            result[k] = v
        elif isinstance(v, float):
            if not (math.isnan(v) or math.isinf(v)):
                result[k] = v
    return result


class YfinanceCollector(BaseCollector):

    def collect(self, ticker: str) -> CollectorResult:
        ticker = ticker.upper()
        collected_at = datetime.now(timezone.utc)

        try:
            info = self._fetch_info(ticker)

            price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
            previous_close = _safe_float(
                info.get("previousClose") or info.get("regularMarketPreviousClose")
            )
            market_cap = _safe_float(info.get("marketCap"))
            week52_high = _safe_float(info.get("fiftyTwoWeekHigh"))
            week52_low = _safe_float(info.get("fiftyTwoWeekLow"))

            change = None
            if price is not None and previous_close and previous_close != 0:
                change = round((price - previous_close) / previous_close * 100, 2)

            fundamentals = {
                "price": price,
                "previous_close": previous_close,
                "market_cap": market_cap,
                "week52_high": week52_high,
                "week52_low": week52_low,
            }

            description = (
                f"{ticker} — Preço atual: {price}, Variação: {change}%, "
                f"Máx 52s: {week52_high}, Mín 52s: {week52_low}. "
                f"Coletado em: {collected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}."
            )

            return CollectorResult(
                ticker=ticker,
                source="yfinance",
                collected_at=collected_at,
                fundamentals=fundamentals,
                raw_json=info,
                text_description=description,
                success=True,
            )

        except Exception as e:
            logger.error(f"[yfinance] {ticker} coleta falhou: {e}")
            return CollectorResult(
                ticker=ticker,
                source="yfinance",
                collected_at=collected_at,
                fundamentals={},
                raw_json={},
                text_description="",
                success=False,
                error=str(e),
            )

    def collect_history(self, ticker: str, period: str = "5y") -> list[CotacaoDiariaSchema]:
        ticker = ticker.upper()
        df = yf.Ticker(ticker).history(period=period)

        records = []
        for ts, row in df.iterrows():
            fechamento = _safe_float(row.get("Close"))
            if fechamento is None:
                logger.warning(f"[yfinance] {ticker} {ts.date()} descartado: fechamento ausente")
                continue

            try:
                vol = row.get("Volume")
                volume = int(vol) if _safe_float(vol) is not None else None

                record = CotacaoDiariaSchema(
                    ticker=ticker,
                    data=ts.date(),
                    abertura=_safe_float(row.get("Open")),
                    maxima=_safe_float(row.get("High")),
                    minima=_safe_float(row.get("Low")),
                    fechamento=fechamento,
                    volume=volume,
                )
                records.append(record)
            except Exception as e:
                logger.warning(f"[yfinance] {ticker} {ts.date()} ignorado: {e}")

        logger.debug(f"[yfinance] {ticker} histórico: {len(records)} registros válidos (period={period})")
        return records

    def healthcheck(self) -> bool:
        try:
            yf.Ticker("AAPL").fast_info
            return True
        except Exception as e:
            logger.warning(f"[yfinance] healthcheck falhou: {e}")
            return False

    # ------------------------------------------------------------------

    def _fetch_info(self, ticker: str) -> dict:
        cache_key = f"yfinance:{ticker}"

        try:
            from src.storage.sql.redis_client import get_client
            redis = get_client()
            cached = redis.get(cache_key)
            if cached:
                logger.debug(f"[yfinance] {ticker} info servido do cache Redis")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"[yfinance] Redis indisponível, prosseguindo sem cache: {e}")

        info = self._get_info_with_fallback(ticker)

        try:
            from src.storage.sql.redis_client import get_client
            redis = get_client()
            redis.set(cache_key, json.dumps(info), ex=_REDIS_TTL_QUOTE)
            logger.debug(f"[yfinance] {ticker} info armazenado no cache Redis (TTL={_REDIS_TTL_QUOTE}s)")
        except Exception as e:
            logger.warning(f"[yfinance] falha ao gravar cache Redis: {e}")

        return info

    def _get_info_with_fallback(self, ticker: str) -> dict:
        # .info é o endpoint preferido (payload completo), mas sujeito a rate limit do Yahoo.
        # fast_info usa endpoint diferente e serve como fallback confiável.
        try:
            raw_info = dict(yf.Ticker(ticker).info)
            info = _json_safe_dict(raw_info)
            if info.get("currentPrice") or info.get("regularMarketPrice"):
                logger.debug(f"[yfinance] {ticker} info obtido via .info")
                return info
            logger.debug(f"[yfinance] {ticker} .info sem preço, usando fast_info")
        except Exception as e:
            logger.warning(f"[yfinance] {ticker} .info falhou ({e}), usando fast_info")

        fi = yf.Ticker(ticker).fast_info
        return _json_safe_dict({
            "currentPrice":       fi.last_price,
            "previousClose":      fi.previous_close,
            "marketCap":          fi.market_cap,
            "fiftyTwoWeekHigh":   fi.year_high,
            "fiftyTwoWeekLow":    fi.year_low,
            "currency":           fi.currency,
            "exchange":           fi.exchange,
            "_source":            "fast_info",
        })
