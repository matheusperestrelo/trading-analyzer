import pytest
import pandas as pd
from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from src.collectors.finviz_collector import FinvizCollector
from src.collectors.yfinance_collector import YfinanceCollector
from src.collectors.schemas import FundamentosSnapshotSchema, CotacaoDiariaSchema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Minimal HTML with the 12 fields mapped in FinvizCollector._LABEL_MAP
FINVIZ_HTML = """
<html><body>
<table class="snapshot-table2">
  <td>P/E</td><td>25.00</td>
  <td>P/B</td><td>10.50</td>
  <td>Dividend %</td><td>0.55%</td>
  <td>ROE</td><td>147.25%</td>
  <td>ROI</td><td>62.34%</td>
  <td>Profit Margin</td><td>26.44%</td>
  <td>Oper. Margin</td><td>31.51%</td>
  <td>Debt/Eq</td><td>1.69</td>
  <td>Current Ratio</td><td>0.92</td>
  <td>EPS next 5Y</td><td>12.07%</td>
  <td>Payout</td><td>14.73%</td>
  <td>EV/EBITDA</td><td>26.41</td>
</table>
</body></html>
"""

YFINANCE_INFO = {
    "currentPrice":     185.92,
    "previousClose":    184.50,
    "marketCap":        2_850_000_000_000,
    "fiftyTwoWeekHigh": 199.62,
    "fiftyTwoWeekLow":  164.08,
    "currency":         "USD",
    "exchange":         "NMS",
}


def _history_df() -> pd.DataFrame:
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    return pd.DataFrame(
        {
            "Open":   [185.00, 184.00, 186.00],
            "High":   [188.00, 186.00, 189.00],
            "Low":    [184.00, 183.00, 185.00],
            "Close":  [187.15, 185.92, 188.01],
            "Volume": [50_000_000, 48_000_000, 52_000_000],
        },
        index=dates,
    )


def _redis_empty() -> MagicMock:
    """Redis disponível, cache vazio."""
    m = MagicMock()
    m.get.return_value = None
    return m


def _yf_ticker_mock(info: dict = YFINANCE_INFO, history: pd.DataFrame = None) -> MagicMock:
    if history is None:
        history = _history_df()
    mock = MagicMock()
    mock.info = info
    mock.history.return_value = history
    mock.fast_info = MagicMock()
    mock.fast_info.last_price = info.get("currentPrice")
    return mock


@contextmanager
def _patch_finviz(html: str = FINVIZ_HTML, status: int = 200):
    """Patches httpx.get, httpx.head, time.sleep and Redis for FinvizCollector."""
    http_resp = MagicMock()
    http_resp.text = html
    http_resp.status_code = status
    http_resp.raise_for_status = MagicMock()

    head_resp = MagicMock()
    head_resp.status_code = 200

    with patch("src.collectors.finviz_collector.httpx.get", return_value=http_resp), \
         patch("src.collectors.finviz_collector.httpx.head", return_value=head_resp), \
         patch("src.collectors.finviz_collector.time.sleep"), \
         patch("src.storage.sql.redis_client.get_client", return_value=_redis_empty()):
        yield


@contextmanager
def _patch_yfinance(info: dict = YFINANCE_INFO, history: pd.DataFrame = None):
    """Patches yf.Ticker and Redis for YfinanceCollector."""
    mock_ticker = _yf_ticker_mock(info, history)
    with patch("src.collectors.yfinance_collector.yf.Ticker", return_value=mock_ticker), \
         patch("src.storage.sql.redis_client.get_client", return_value=_redis_empty()):
        yield


# ---------------------------------------------------------------------------
# FinvizCollector
# ---------------------------------------------------------------------------

def test_finviz_healthcheck():
    with _patch_finviz():
        assert FinvizCollector().healthcheck() is True


def test_finviz_collect_success():
    with _patch_finviz():
        r = FinvizCollector().collect("AAPL")
    assert r.success is True
    assert r.source == "finviz"


def test_finviz_text_description():
    with _patch_finviz():
        r = FinvizCollector().collect("MSFT")
    assert "MSFT" in r.text_description


def test_finviz_raw_json_not_empty():
    with _patch_finviz():
        r = FinvizCollector().collect("NVDA")
    assert isinstance(r.raw_json, dict)
    assert len(r.raw_json) > 0


# ---------------------------------------------------------------------------
# YfinanceCollector
# ---------------------------------------------------------------------------

def test_yfinance_healthcheck():
    with _patch_yfinance():
        assert YfinanceCollector().healthcheck() is True


def test_yfinance_collect_success():
    with _patch_yfinance():
        r = YfinanceCollector().collect("AAPL")
    assert r.success is True
    assert r.fundamentals["price"] is not None


def test_yfinance_history():
    with _patch_yfinance():
        h = YfinanceCollector().collect_history("AAPL")
    assert len(h) > 0
    assert all(x.fechamento is not None for x in h)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def test_schema_coerce_percent():
    s = FundamentosSnapshotSchema(
        ticker="X", fonte="t", pl="15.3%", raw_json={}, text_description=""
    )
    assert abs(s.pl - 0.153) < 1e-9


def test_schema_coerce_billion():
    s = FundamentosSnapshotSchema(
        ticker="X", fonte="t", pl="1.2B", raw_json={}, text_description=""
    )
    assert s.pl == 1_200_000_000.0


def test_schema_coerce_dash_none():
    s = FundamentosSnapshotSchema(
        ticker="X", fonte="t", pl="-", raw_json={}, text_description=""
    )
    assert s.pl is None


def test_schema_fechamento_required():
    with pytest.raises(ValidationError):
        CotacaoDiariaSchema(ticker="X", data=date(2024, 1, 1), fechamento=None)
