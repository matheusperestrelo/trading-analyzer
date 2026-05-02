# trading-analyzer

Personal stock analysis system for US equities. Collects fundamental and market data from Finviz and yfinance, stores it in a PostgreSQL database with TimescaleDB (time-series) and pgvector (embeddings), and exposes a Typer CLI for analysis and report generation. This is a **decision-support tool only** — it performs no automated trading.

---

## Requirements

- Python 3.12+
- Docker and Docker Compose
- DBeaver (optional — for inspecting the database)

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd trading-analyzer
```

### 2. Create and activate virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env if needed — defaults work with the Docker setup below
```

### 5. Start the database containers

```bash
docker compose up -d
```

### 6. Create PostgreSQL extensions

```bash
./docker/setup_db.sh
```

### 7. Run database migrations

```bash
alembic upgrade head
```

### 8. Verify the setup

```bash
python -m src.main --help
```

---

## Usage

```bash
python -m src.main analyze AAPL
python -m src.main collect MSFT
python -m src.main report NVDA
```

---

## Project structure

```
trading-analyzer/
├── config/                  # YAML configuration files
│   ├── settings.yaml        # App, database, Redis, scraping settings
│   ├── watchlist.yaml       # Tickers to track
│   ├── sources.yaml         # Data source toggles and config
│   └── ai.yaml              # Ollama / embeddings / RAG settings
├── src/
│   ├── main.py              # Typer CLI entry point
│   ├── collectors/          # Data collectors (Finviz, yfinance, …)
│   ├── processors/          # Data transformation layer
│   ├── storage/
│   │   ├── sql/             # SQLAlchemy models, engine, Alembic migrations
│   │   ├── vector/          # pgvector integration (future)
│   │   └── documents/       # Document storage (future)
│   ├── ai/                  # Embeddings, RAG, agents (future)
│   ├── reporters/           # Report generators
│   └── orchestrator/        # Workflow orchestration
├── tests/                   # pytest test suite
├── docker/
│   ├── Dockerfile.postgres  # Custom Postgres image (TimescaleDB + pgvector)
│   ├── init.sql             # Extension initialization
│   └── setup_db.sh          # Post-start extension setup script
├── data/                    # Raw data storage (gitignored)
├── logs/                    # Application logs (gitignored)
├── reports/                 # Generated reports (gitignored)
├── prompts/                 # Jinja2 prompt templates
├── notebooks/               # Jupyter notebooks
├── alembic.ini              # Alembic migration config
├── docker-compose.yml       # Postgres + Redis services
└── requirements.txt
```

---

## Docker notes

The custom `docker/Dockerfile.postgres` builds TimescaleDB + pgvector from source on Alpine Linux. Three fixes were required to work around LLVM version mismatches between Alpine's current packages and the LLVM version PostgreSQL 16 was compiled with:

1. **`clang-19` alias** — Alpine ships `clang21`; PostgreSQL's build system expects `clang-19`:
   ```dockerfile
   ln -sf /usr/bin/clang /usr/local/bin/clang-19
   ```

2. **`llvm19/bin` directory** — the path `/usr/lib/llvm19/bin/` does not exist on the Alpine base image:
   ```dockerfile
   mkdir -p /usr/lib/llvm19/bin
   ```

3. **`llvm-lto` stub** — `llvm-lto` was removed in LLVM 14+, but PostgreSQL's `pgxs.mk` still calls it to generate a JIT bitcode index. A no-op stub allows the build to complete; pgvector works normally for all non-JIT queries:
   ```dockerfile
   printf '#!/bin/sh\nexit 0\n' > /usr/lib/llvm19/bin/llvm-lto && chmod +x /usr/lib/llvm19/bin/llvm-lto
   ```

---

## Database

| Table | Description |
|---|---|
| `tickers` | Master list of tracked stocks |
| `fundamentos_snapshot` | Point-in-time fundamental snapshots (P/L, P/VP, DY, ROE, …) |
| `cotacoes_diarias` | Daily OHLCV prices — **TimescaleDB hypertable** partitioned on `data` |
| `relatorios` | Generated analysis reports and scores |

`cotacoes_diarias` is a TimescaleDB hypertable partitioned by the `data` column. The primary key is the composite `(ticker, data)` — required by TimescaleDB so the partitioning column is part of every unique index.
