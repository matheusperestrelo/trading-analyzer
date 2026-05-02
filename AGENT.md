# AGENT.md — trading-analyzer

Context for any AI agent working on this codebase. Read this before making changes.

---

## Project summary

Personal stock analysis system for **US equities**. Data is sourced from Finviz (fundamental scraping) and yfinance (market data and price history). The system stores data in PostgreSQL + TimescaleDB + pgvector, caches results in Redis, and exposes a Typer CLI.

**This is a decision-support tool only. It performs no automated trading.**

---

## Current phase

**Phase 0 — MVP**

The infrastructure is in place (database, migrations, CLI skeleton, connection layer). Business logic modules (collectors, processors, reporters, AI) are not yet implemented.

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Database | PostgreSQL 16 + TimescaleDB + pgvector |
| Cache | Redis 7 |
| ORM | SQLAlchemy 2 + Alembic |
| CLI | Typer + Loguru |
| Data processing | Polars |
| HTTP | httpx + selectolax |
| Market data | yfinance |
| Templating | Jinja2 |
| Testing | pytest |

---

## Architecture rules — never violate these

1. **Never hardcode credentials.** All secrets and connection strings must be read from `.env` via `python-dotenv`. The `.env` file is gitignored.

2. **Never skip Pydantic validation on collector output.** Every collector must validate its output through a Pydantic model before writing to the database.

3. **`raw_json` must always be populated.** The `raw_json` field in `fundamentos_snapshot` must always contain the raw source payload exactly as received. Never discard it.

4. **`text_description` must be populated at collection time.** This field in `fundamentos_snapshot` is used for future RAG. Generate a human-readable summary from the raw data at collection time so it is always available.

5. **Keep business logic pure and testable.** Functions in collectors, processors, and reporters must not import Celery or any task queue directly. Orchestration is handled separately.

6. **Every collector must implement the `BaseCollector` interface** with at minimum `collect(ticker: str)` and `healthcheck() -> bool` methods.

---

## Roadmap

| Phase | Description |
|---|---|
| 0 | MVP — data collection, storage, basic CLI reports |
| 1 | LLM summarization — Ollama integration for narrative reports |
| 2 | RAG + alerts — pgvector similarity search, threshold-based notifications |
| 3 | AI analyst chat — conversational interface over the collected data |
| 4 | Predictive models — ML-based price and quality scoring |
| 5 | Backtesting + LoRA finetuning — strategy validation and fine-tuned models |
| 6 | Portfolio monitoring — multi-ticker dashboard and position tracking |

---

## Data sources

| Source | Tier | Method | Data |
|---|---|---|---|
| Finviz | 1 (primary) | httpx + selectolax scraping | Fundamentals: P/L, P/VP, DY, ROE, ROIC, margins, debt, CAGR |
| yfinance | 1 (primary) | Official Python library | Price history, OHLCV, market cap, dividends |

---

## Key files

| File | Purpose |
|---|---|
| `src/storage/sql/models.py` | SQLAlchemy models — `Ticker`, `FundamentosSnapshot`, `CotacaoDiaria`, `Relatorio` |
| `src/storage/sql/database.py` | SQLAlchemy engine, `SessionLocal`, `Base`, `test_connection()` |
| `src/storage/sql/redis_client.py` | Redis singleton client, `get_client()`, `test_connection()` |
| `src/storage/sql/migrations/` | Alembic migrations directory |
| `src/main.py` | Typer CLI entry point — `analyze`, `collect`, `report` commands |
| `config/watchlist.yaml` | List of tickers the system tracks |
| `config/settings.yaml` | App, database, Redis, and scraping configuration |
| `config/sources.yaml` | Per-source enable/disable flags and settings |
| `docker/Dockerfile.postgres` | Custom image: TimescaleDB + pgvector compiled from source |
| `docker/setup_db.sh` | Creates TimescaleDB and pgvector extensions post-startup |
