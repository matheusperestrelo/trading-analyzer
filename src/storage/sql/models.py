import uuid
from datetime import datetime, date
from sqlalchemy import (
    String, Date, DateTime, Float,
    Integer, Text, JSON, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from .database import Base


class Ticker(Base):
    __tablename__ = "tickers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(200), nullable=True)
    setor: Mapped[str] = mapped_column(String(100), nullable=True)
    subsetor: Mapped[str] = mapped_column(String(100), nullable=True)
    exchange: Mapped[str] = mapped_column(String(50), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    fundamentos: Mapped[list["FundamentosSnapshot"]] = relationship(
        back_populates="ticker_rel"
    )
    cotacoes: Mapped[list["CotacaoDiaria"]] = relationship(
        back_populates="ticker_rel"
    )
    relatorios: Mapped[list["Relatorio"]] = relationship(
        back_populates="ticker_rel"
    )

class FundamentosSnapshot(Base):
    __tablename__ = "fundamentos_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(
        String(20), ForeignKey("tickers.ticker"), nullable=False
    )
    coletado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fonte: Mapped[str] = mapped_column(String(50), nullable=False)

    # fundamentos
    pl: Mapped[float] = mapped_column(Float, nullable=True)
    pvp: Mapped[float] = mapped_column(Float, nullable=True)
    dy: Mapped[float] = mapped_column(Float, nullable=True)
    roe: Mapped[float] = mapped_column(Float, nullable=True)
    roic: Mapped[float] = mapped_column(Float, nullable=True)
    margem_liquida: Mapped[float] = mapped_column(Float, nullable=True)
    margem_ebitda: Mapped[float] = mapped_column(Float, nullable=True)
    divida_liquida_ebitda: Mapped[float] = mapped_column(Float, nullable=True)
    liquidez_corrente: Mapped[float] = mapped_column(Float, nullable=True)
    cagr_receita_5a: Mapped[float] = mapped_column(Float, nullable=True)
    payout: Mapped[float] = mapped_column(Float, nullable=True)
    ev_ebitda: Mapped[float] = mapped_column(Float, nullable=True)

    # texto descritivo para RAG futuro
    text_description: Mapped[str] = mapped_column(Text, nullable=True)

    # payload bruto da fonte — nunca descartado
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    ticker_rel: Mapped["Ticker"] = relationship(back_populates="fundamentos")

    __table_args__ = (
        UniqueConstraint("ticker", "coletado_em", "fonte", name="uq_snapshot"),
    )

class CotacaoDiaria(Base):
    __tablename__ = "cotacoes_diarias"

    ticker: Mapped[str] = mapped_column(
        String(20), ForeignKey("tickers.ticker"), nullable=False, primary_key=True
    )
    data: Mapped[date] = mapped_column(Date, nullable=False, primary_key=True)
    abertura: Mapped[float] = mapped_column(Float, nullable=True)
    maxima: Mapped[float] = mapped_column(Float, nullable=True)
    minima: Mapped[float] = mapped_column(Float, nullable=True)
    fechamento: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=True)

    ticker_rel: Mapped["Ticker"] = relationship(back_populates="cotacoes")

class Relatorio(Base):
    __tablename__ = "relatorios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(
        String(20), ForeignKey("tickers.ticker"), nullable=False
    )
    gerado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    caminho_arquivo: Mapped[str] = mapped_column(String(500), nullable=True)
    score_geral: Mapped[float] = mapped_column(Float, nullable=True)
    score_qualidade: Mapped[float] = mapped_column(Float, nullable=True)
    score_valuation: Mapped[float] = mapped_column(Float, nullable=True)
    score_momento: Mapped[float] = mapped_column(Float, nullable=True)

    ticker_rel: Mapped["Ticker"] = relationship(back_populates="relatorios")