"""
Repository integration tests — require the Postgres Docker Compose service running.

Run with:
    docker compose up -d
    alembic upgrade head
    pytest tests/test_storage.py -v
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.collectors.schemas import CotacaoDiariaSchema, FundamentosSnapshotSchema
from src.config.settings import get_settings
from src.storage.sql.repository import Repository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def engine() -> Engine:
    url = get_settings().database_url
    eng = create_engine(url, pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def repo(engine: Engine) -> Repository:
    return Repository(engine)


@pytest.fixture(autouse=True, scope="function")
def cleanup(engine: Engine):
    """Delete test rows after each test to keep the DB clean."""
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM fundamentos_snapshot WHERE ticker LIKE 'TEST_%'"))
        conn.execute(text("DELETE FROM cotacoes_diarias WHERE ticker LIKE 'TEST_%'"))
        conn.execute(text("DELETE FROM tickers WHERE ticker LIKE 'TEST_%'"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_TICKER = "TEST_AAPL"
_TEST_TICKER_2 = "TEST_MSFT"


def _make_snapshot(ticker: str = _TEST_TICKER, fonte: str = "test") -> FundamentosSnapshotSchema:
    return FundamentosSnapshotSchema(
        ticker=ticker,
        fonte=fonte,
        pl=25.5,
        pvp=3.2,
        dy=0.006,
        roe=0.42,
        roic=0.35,
        margem_liquida=0.27,
        divida_liquida_ebitda=1.1,
        liquidez_corrente=0.98,
        cagr_receita_5a=0.12,
        payout=0.15,
        raw_json={"P/E": "25.5", "P/B": "3.2"},
        text_description=f"{ticker} — test snapshot from pytest",
    )


def _make_cotacao(ticker: str = _TEST_TICKER, delta_days: int = 0) -> CotacaoDiariaSchema:
    return CotacaoDiariaSchema(
        ticker=ticker,
        data=date(2024, 1, 2) + timedelta(days=delta_days),
        abertura=180.0,
        maxima=185.0,
        minima=179.0,
        fechamento=182.5,
        volume=50_000_000,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUpsertTicker:
    def test_insert_new_ticker(self, repo: Repository, engine: Engine):
        repo.upsert_ticker(_TEST_TICKER, "Apple Inc.", "Technology", "Hardware", "NASDAQ")

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT nome, setor FROM tickers WHERE ticker = :t"),
                {"t": _TEST_TICKER},
            ).mappings().first()

        assert row is not None
        assert row["nome"] == "Apple Inc."
        assert row["setor"] == "Technology"

    def test_update_existing_ticker(self, repo: Repository, engine: Engine):
        repo.upsert_ticker(_TEST_TICKER, "Apple Inc.", "Technology", "Hardware", "NASDAQ")
        repo.upsert_ticker(_TEST_TICKER, "Apple Updated", "Tech", "Consumer Electronics", "NASDAQ")

        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT nome, setor FROM tickers WHERE ticker = :t"),
                {"t": _TEST_TICKER},
            ).mappings().all()

        assert len(rows) == 1, "upsert deve manter apenas uma linha"
        assert rows[0]["nome"] == "Apple Updated"
        assert rows[0]["setor"] == "Tech"


class TestInsertFundamentosSnapshot:
    def test_returns_valid_uuid(self, repo: Repository):
        repo.upsert_ticker(_TEST_TICKER, "", "", "", "")
        snapshot_id = repo.insert_fundamentos_snapshot(_make_snapshot())

        parsed = uuid.UUID(snapshot_id)
        assert str(parsed) == snapshot_id

    def test_raw_json_and_description_stored(self, repo: Repository, engine: Engine):
        repo.upsert_ticker(_TEST_TICKER, "", "", "", "")
        snapshot_id = repo.insert_fundamentos_snapshot(_make_snapshot())

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT raw_json, text_description FROM fundamentos_snapshot WHERE id = :id"),
                {"id": snapshot_id},
            ).mappings().first()

        assert row is not None
        assert row["raw_json"] is not None
        assert "P/E" in row["raw_json"]
        assert row["text_description"] != ""


class TestBulkInsertCotacoes:
    def test_inserts_batch(self, repo: Repository, engine: Engine):
        repo.upsert_ticker(_TEST_TICKER, "", "", "", "")
        cotacoes = [_make_cotacao(delta_days=i) for i in range(5)]
        repo.bulk_insert_cotacoes(cotacoes)

        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM cotacoes_diarias WHERE ticker = :t"),
                {"t": _TEST_TICKER},
            ).scalar()

        assert count == 5

    def test_idempotent_on_conflict(self, repo: Repository, engine: Engine):
        repo.upsert_ticker(_TEST_TICKER, "", "", "", "")
        cotacoes = [_make_cotacao(delta_days=i) for i in range(3)]

        repo.bulk_insert_cotacoes(cotacoes)
        repo.bulk_insert_cotacoes(cotacoes)  # second insert — must not duplicate

        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM cotacoes_diarias WHERE ticker = :t"),
                {"t": _TEST_TICKER},
            ).scalar()

        assert count == 3, "ON CONFLICT DO NOTHING deve evitar duplicatas"

    def test_returns_zero_for_empty_list(self, repo: Repository):
        assert repo.bulk_insert_cotacoes([]) == 0


class TestGetLatestSnapshot:
    def test_returns_none_when_no_snapshot(self, repo: Repository):
        repo.upsert_ticker(_TEST_TICKER, "", "", "", "")
        result = repo.get_latest_snapshot(_TEST_TICKER)
        assert result is None

    def test_returns_most_recent_snapshot(self, repo: Repository, engine: Engine):
        repo.upsert_ticker(_TEST_TICKER, "", "", "", "")

        # Insert first snapshot (will have earlier timestamp)
        id1 = repo.insert_fundamentos_snapshot(_make_snapshot(fonte="source_old"))

        # Force the second snapshot to have a later data_coleta
        id2 = repo.insert_fundamentos_snapshot(_make_snapshot(fonte="source_new"))
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE fundamentos_snapshot SET data_coleta = now() + interval '1 hour' WHERE id = :id"),
                {"id": id2},
            )

        result = repo.get_latest_snapshot(_TEST_TICKER)

        assert result is not None
        assert str(result["id"]) == id2, "deve retornar o snapshot mais recente"
        assert result["fonte"] == "source_new"

    def test_returns_dict_not_orm(self, repo: Repository):
        repo.upsert_ticker(_TEST_TICKER, "", "", "", "")
        repo.insert_fundamentos_snapshot(_make_snapshot())
        result = repo.get_latest_snapshot(_TEST_TICKER)
        assert isinstance(result, dict)
