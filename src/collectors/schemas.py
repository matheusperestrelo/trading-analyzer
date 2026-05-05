from datetime import date
from typing import Optional
from pydantic import BaseModel, field_validator


def _coerce_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)

    s = str(v).strip()

    if s in ("-", "", "N/A"):
        return None

    is_percent = s.endswith("%")
    if is_percent:
        s = s[:-1].strip()

    multiplier = 1.0
    upper = s.upper()
    if upper.endswith("B"):
        multiplier = 1_000_000_000.0
        s = s[:-1].strip()
    elif upper.endswith("M"):
        multiplier = 1_000_000.0
        s = s[:-1].strip()

    s = s.replace(",", "")

    try:
        value = float(s) * multiplier
        if is_percent:
            value /= 100.0
        return value
    except (ValueError, TypeError):
        return None


def _coerce_int(v) -> Optional[int]:
    result = _coerce_float(v)
    return int(result) if result is not None else None


class FundamentosSnapshotSchema(BaseModel):
    ticker: str
    fonte: str
    pl: Optional[float] = None
    pvp: Optional[float] = None
    dy: Optional[float] = None
    roe: Optional[float] = None
    roic: Optional[float] = None
    margem_liquida: Optional[float] = None
    margem_ebitda: Optional[float] = None
    divida_liquida_ebitda: Optional[float] = None
    liquidez_corrente: Optional[float] = None
    cagr_receita_5a: Optional[float] = None
    payout: Optional[float] = None
    ev_ebitda: Optional[float] = None
    raw_json: dict
    text_description: str

    @field_validator(
        "pl", "pvp", "dy", "roe", "roic", "margem_liquida", "margem_ebitda",
        "divida_liquida_ebitda", "liquidez_corrente", "cagr_receita_5a",
        "payout", "ev_ebitda",
        mode="before",
    )
    @classmethod
    def coerce_numeric(cls, v):
        return _coerce_float(v)


class CotacaoDiariaSchema(BaseModel):
    ticker: str
    data: date
    abertura: Optional[float] = None
    maxima: Optional[float] = None
    minima: Optional[float] = None
    fechamento: float
    volume: Optional[int] = None

    @field_validator("abertura", "maxima", "minima", "fechamento", mode="before")
    @classmethod
    def coerce_price(cls, v):
        return _coerce_float(v)

    @field_validator("volume", mode="before")
    @classmethod
    def coerce_volume(cls, v):
        return _coerce_int(v)
