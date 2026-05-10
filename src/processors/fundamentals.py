"""FundamentalsProcessor — computes quality, valuation, momentum sub-scores
and a weighted overall score for a given ticker.

Score range: 0–100 (higher = better).
Sub-scores use None when the underlying data is missing; the weighted average
excludes None dimensions and records an alerta for each one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from jinja2 import Environment, FileSystemLoader
from loguru import logger

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MomentoDetail:
    acima_mm200: Optional[bool] = None
    acima_mm50: Optional[bool] = None
    mm50_acima_mm200: Optional[bool] = None
    rsi: Optional[float] = None


@dataclass
class ScoreResult:
    ticker: str
    score_geral: float
    score_qualidade: Optional[float]
    score_valuation: Optional[float]
    score_momento: Optional[float]
    alertas: list[str] = field(default_factory=list)
    momento_detail: MomentoDetail = field(default_factory=MomentoDetail)
    veredito: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _linear(value: float, worst: float, best: float) -> float:
    """Map value linearly from [worst, best] → [0, 100]."""
    if best == worst:
        return 50.0
    score = (value - worst) / (best - worst) * 100.0
    return _clamp(score)


def _compute_rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Classic Wilder RSI over the last `period` closes."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-period - 1 + i] - closes[-period - 2 + i]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-diff)
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return _clamp(100.0 - 100.0 / (1.0 + rs))


def _moving_average(closes: list[float], window: int) -> Optional[float]:
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------

class FundamentalsProcessor:
    """Stateless: call `process()` with a snapshot dict and optional cotacoes."""

    def __init__(self) -> None:
        with open(_CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)
        sc = cfg.get("score", {})
        self._pesos = sc.get("pesos", {"qualidade": 0.40, "valuation": 0.35, "momento": 0.25})
        self._q_cfg = sc.get("qualidade", {})
        self._v_cfg = sc.get("valuation", {})

        # jinja2 for veredito
        self._jinja = Environment(
            loader=FileSystemLoader(str(_PROMPTS_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # ── qualidade ────────────────────────────────────────────────────────────

    def _score_qualidade(
        self,
        snap: dict,
        alertas: list[str],
    ) -> Optional[float]:
        scores: list[float] = []

        roe_exc = self._q_cfg.get("roe_excelencia", 0.20)
        roic_exc = self._q_cfg.get("roic_excelencia", 0.20)
        ml_exc = self._q_cfg.get("margem_liquida_excelencia", 0.30)
        div_max = self._q_cfg.get("divida_max", 4.0)

        roe = snap.get("roe")
        if roe is not None:
            scores.append(_linear(roe, worst=-0.10, best=roe_exc))
        else:
            alertas.append("ROE não disponível")

        roic = snap.get("roic")
        if roic is not None:
            scores.append(_linear(roic, worst=-0.10, best=roic_exc))
        else:
            alertas.append("ROIC não disponível")

        ml = snap.get("margem_liquida")
        if ml is not None:
            scores.append(_linear(ml, worst=-0.20, best=ml_exc))
        else:
            alertas.append("Margem líquida não disponível")

        div = snap.get("divida_liquida_ebitda")
        if div is not None:
            # lower = better; invert: score 0 when div ≥ div_max, 100 when div ≤ 0
            scores.append(_linear(div, worst=div_max, best=0.0))
        else:
            alertas.append("Dívida/EBITDA não disponível")

        if not scores:
            return None
        return _clamp(sum(scores) / len(scores))

    # ── valuation ────────────────────────────────────────────────────────────

    def _score_valuation(
        self,
        snap: dict,
        alertas: list[str],
    ) -> Optional[float]:
        scores: list[float] = []

        pl_barato = self._v_cfg.get("pl_barato", 10)
        pl_caro = self._v_cfg.get("pl_caro", 40)
        pvp_barato = self._v_cfg.get("pvp_barato", 1.0)
        pvp_caro = self._v_cfg.get("pvp_caro", 6.0)
        dy_exc = self._v_cfg.get("dy_excelencia", 0.06)

        pl = snap.get("pl")
        if pl is not None and pl > 0:
            scores.append(_linear(pl, worst=pl_caro, best=pl_barato))
        elif pl is None:
            alertas.append("P/L não disponível")

        pvp = snap.get("pvp")
        if pvp is not None and pvp > 0:
            scores.append(_linear(pvp, worst=pvp_caro, best=pvp_barato))
        elif pvp is None:
            alertas.append("P/VPA não disponível")

        dy = snap.get("dy")
        if dy is not None:
            scores.append(_linear(dy, worst=0.0, best=dy_exc))
        else:
            alertas.append("Dividend Yield não disponível")

        if not scores:
            return None
        return _clamp(sum(scores) / len(scores))

    # ── momento ──────────────────────────────────────────────────────────────

    def _score_momento(
        self,
        cotacoes: list[dict],
        alertas: list[str],
    ) -> tuple[Optional[float], MomentoDetail]:
        detail = MomentoDetail()

        if not cotacoes:
            alertas.append("Histórico de preços indisponível — momento neutro")
            return None, detail

        closes = [float(r["fechamento"]) for r in cotacoes if r.get("fechamento") is not None]

        if len(closes) < 21:
            alertas.append("Histórico insuficiente para cálculo de médias móveis")
            return None, detail

        price = closes[-1]
        mm200 = _moving_average(closes, 200)
        mm50 = _moving_average(closes, 50)
        mm21 = _moving_average(closes, 21)
        rsi = _compute_rsi(closes, 14)

        detail.rsi = rsi

        scores: list[float] = []

        if mm200 is not None:
            detail.acima_mm200 = price > mm200
            scores.append(100.0 if price > mm200 else 0.0)

        if mm50 is not None:
            detail.acima_mm50 = price > mm50
            scores.append(100.0 if price > mm50 else 0.0)

        if mm21 is not None:
            scores.append(100.0 if price > mm21 else 0.0)

        if mm200 is not None and mm50 is not None:
            detail.mm50_acima_mm200 = mm50 > mm200
            scores.append(100.0 if mm50 > mm200 else 0.0)

        if rsi is not None:
            # 50 = neutral; favor 40–65 range
            rsi_score = _linear(rsi, worst=85.0, best=50.0) if rsi > 50 else _linear(rsi, worst=15.0, best=50.0)
            scores.append(rsi_score)

        if not scores:
            return None, detail

        return _clamp(sum(scores) / len(scores)), detail

    # ── main entry point ──────────────────────────────────────────────────────

    def process(
        self,
        ticker: str,
        snapshot: dict,
        cotacoes: list[dict] | None = None,
    ) -> ScoreResult:
        logger.info(f"FundamentalsProcessor.process | ticker={ticker}")
        cotacoes = cotacoes or []
        alertas: list[str] = []

        sq = self._score_qualidade(snapshot, alertas)
        sv = self._score_valuation(snapshot, alertas)
        sm, momento_detail = self._score_momento(cotacoes, alertas)

        # Weighted average, skipping None dimensions
        parts: list[tuple[float, float]] = []
        if sq is not None:
            parts.append((sq, self._pesos["qualidade"]))
        if sv is not None:
            parts.append((sv, self._pesos["valuation"]))
        if sm is not None:
            parts.append((sm, self._pesos["momento"]))

        if parts:
            total_weight = sum(w for _, w in parts)
            score_geral = sum(s * w for s, w in parts) / total_weight
        else:
            score_geral = 50.0  # fully neutral fallback
            alertas.append("Dados insuficientes — score neutro aplicado")

        score_geral = _clamp(score_geral)

        # Generate veredito via Jinja2
        veredito = self._render_veredito(
            ticker=ticker,
            score_geral=score_geral,
            score_qualidade=sq,
            score_valuation=sv,
            score_momento=sm,
            alertas=alertas,
        )

        result = ScoreResult(
            ticker=ticker,
            score_geral=round(score_geral, 1),
            score_qualidade=round(sq, 1) if sq is not None else None,
            score_valuation=round(sv, 1) if sv is not None else None,
            score_momento=round(sm, 1) if sm is not None else None,
            alertas=alertas,
            momento_detail=momento_detail,
            veredito=veredito,
        )
        logger.info(
            f"FundamentalsProcessor.process ok | ticker={ticker} | "
            f"score_geral={result.score_geral} | Q={result.score_qualidade} "
            f"V={result.score_valuation} M={result.score_momento}"
        )
        return result

    def _render_veredito(self, **ctx) -> str:
        try:
            tmpl = self._jinja.get_template("veredito_template.txt")
            return tmpl.render(**ctx).strip()
        except Exception as exc:
            logger.warning(f"veredito template render falhou: {exc}")
            return f"{ctx['ticker']} — score geral: {ctx['score_geral']:.1f}/100."
