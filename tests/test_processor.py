"""Unit tests for FundamentalsProcessor.

All tests run in isolation — no network, no database, no file I/O beyond
reading config/settings.yaml and prompts/veredito_template.txt which are
always present in the repo.
"""
import pytest

from src.processors.fundamentals import (
    FundamentalsProcessor,
    ScoreResult,
    _clamp,
    _compute_rsi,
    _linear,
    _moving_average,
)


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def processor() -> FundamentalsProcessor:
    return FundamentalsProcessor()


def _good_snapshot() -> dict:
    """A snapshot that should yield high sub-scores."""
    return {
        "roe": 0.25,
        "roic": 0.22,
        "margem_liquida": 0.28,
        "divida_liquida_ebitda": 0.5,
        "liquidez_corrente": 2.0,
        "pl": 14.0,
        "pvp": 1.2,
        "dy": 0.05,
        "cagr_receita_5a": 0.12,
        "payout": 0.40,
    }


def _bad_snapshot() -> dict:
    """A snapshot that should yield low sub-scores."""
    return {
        "roe": -0.05,
        "roic": -0.03,
        "margem_liquida": -0.10,
        "divida_liquida_ebitda": 8.0,
        "liquidez_corrente": 0.5,
        "pl": 80.0,
        "pvp": 10.0,
        "dy": 0.001,
        "cagr_receita_5a": -0.05,
        "payout": 1.5,
    }


def _trending_cotacoes(n: int = 250, uptrend: bool = True) -> list[dict]:
    """Generate synthetic daily quotes (ascending or descending trend)."""
    rows = []
    price = 100.0
    for i in range(n):
        price += (0.2 if uptrend else -0.2)
        rows.append({"fechamento": round(price, 2)})
    return rows


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_clamp_within(self):
        assert _clamp(50.0) == 50.0

    def test_clamp_below(self):
        assert _clamp(-10.0) == 0.0

    def test_clamp_above(self):
        assert _clamp(110.0) == 100.0

    def test_linear_best_value(self):
        assert _linear(20.0, worst=0.0, best=20.0) == pytest.approx(100.0)

    def test_linear_worst_value(self):
        assert _linear(0.0, worst=0.0, best=20.0) == pytest.approx(0.0)

    def test_linear_midpoint(self):
        assert _linear(10.0, worst=0.0, best=20.0) == pytest.approx(50.0)

    def test_moving_average_insufficient_data(self):
        assert _moving_average([1.0, 2.0], 5) is None

    def test_moving_average_exact(self):
        closes = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _moving_average(closes, 3) == pytest.approx(4.0)

    def test_rsi_insufficient(self):
        assert _compute_rsi([1.0] * 10, period=14) is None

    def test_rsi_constant_prices(self):
        # no gains, no losses → RSI should be 100 (avg_loss == 0 branch)
        closes = [100.0] * 20
        assert _compute_rsi(closes, 14) == pytest.approx(100.0)

    def test_rsi_only_gains(self):
        closes = [float(i) for i in range(1, 30)]
        rsi = _compute_rsi(closes, 14)
        assert rsi is not None and rsi > 70.0

    def test_rsi_only_losses(self):
        closes = [float(30 - i) for i in range(30)]
        rsi = _compute_rsi(closes, 14)
        assert rsi is not None and rsi < 30.0


# ---------------------------------------------------------------------------
# Processor integration tests (no I/O beyond local files)
# ---------------------------------------------------------------------------

class TestFundamentalsProcessor:
    def test_good_snapshot_high_quality_score(self, processor):
        result = processor.process("TEST", _good_snapshot(), [])
        assert result.score_qualidade is not None
        assert result.score_qualidade >= 60.0

    def test_bad_snapshot_low_quality_score(self, processor):
        result = processor.process("TEST", _bad_snapshot(), [])
        assert result.score_qualidade is not None
        assert result.score_qualidade <= 40.0

    def test_good_snapshot_high_valuation_score(self, processor):
        result = processor.process("TEST", _good_snapshot(), [])
        assert result.score_valuation is not None
        assert result.score_valuation >= 55.0

    def test_bad_snapshot_low_valuation_score(self, processor):
        result = processor.process("TEST", _bad_snapshot(), [])
        assert result.score_valuation is not None
        assert result.score_valuation <= 30.0

    def test_uptrend_high_momento_score(self, processor):
        cotacoes = _trending_cotacoes(250, uptrend=True)
        result = processor.process("TEST", _good_snapshot(), cotacoes)
        assert result.score_momento is not None
        assert result.score_momento >= 60.0

    def test_downtrend_low_momento_score(self, processor):
        cotacoes = _trending_cotacoes(250, uptrend=False)
        result = processor.process("TEST", _good_snapshot(), cotacoes)
        assert result.score_momento is not None
        assert result.score_momento <= 40.0

    def test_no_cotacoes_momento_none(self, processor):
        result = processor.process("TEST", _good_snapshot(), [])
        assert result.score_momento is None
        assert any("Histórico" in a or "histórico" in a or "preços" in a for a in result.alertas)

    def test_none_fields_trigger_alertas(self, processor):
        snap = {"roe": None, "roic": None, "margem_liquida": None,
                "divida_liquida_ebitda": None, "pl": None, "pvp": None, "dy": None}
        result = processor.process("TEST", snap, [])
        assert len(result.alertas) >= 4

    def test_score_geral_within_bounds(self, processor):
        for snap, cotacoes in [
            (_good_snapshot(), _trending_cotacoes(250)),
            (_bad_snapshot(), _trending_cotacoes(250, uptrend=False)),
            ({}, []),
        ]:
            result = processor.process("TEST", snap, cotacoes)
            assert 0.0 <= result.score_geral <= 100.0

    def test_score_result_type(self, processor):
        result = processor.process("AAPL", _good_snapshot(), _trending_cotacoes(250))
        assert isinstance(result, ScoreResult)
        assert result.ticker == "AAPL"
        assert isinstance(result.veredito, str)
        assert len(result.veredito) > 10

    def test_partial_snapshot_no_crash(self, processor):
        snap = {"roe": 0.18, "pl": 20.0}
        result = processor.process("TEST", snap, [])
        assert isinstance(result, ScoreResult)
        assert result.score_geral is not None
