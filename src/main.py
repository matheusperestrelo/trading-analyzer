import sys
import os
from pathlib import Path

import typer
from loguru import logger

# ---------------------------------------------------------------------------
# Loguru configuration
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger.remove()  # drop the default stderr handler

# Structured file logger — 10 MB rotation, 30 days retention
logger.add(
    LOG_DIR / "trading_analyzer.log",
    level="DEBUG",
    rotation="10 MB",
    retention="30 days",
    encoding="utf-8",
    enqueue=True,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} — {message}",
)

# Human-readable stderr logger (development only)
if os.getenv("ENV", "development") == "development":
    logger.add(
        sys.stderr,
        level="INFO",
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )

# ---------------------------------------------------------------------------
# Connection health-check on startup
# ---------------------------------------------------------------------------

def _check_connections() -> None:
    from src.storage.sql.database import test_connection as pg_test
    from src.storage.sql.redis_client import test_connection as redis_test

    if pg_test():
        logger.info("Startup check — Postgres OK")
    else:
        logger.error("Startup check — Postgres FAILED")

    if redis_test():
        logger.info("Startup check — Redis OK")
    else:
        logger.error("Startup check — Redis FAILED")

# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="trading-analyzer",
    help="Personal stock analysis CLI — US equities, decision support only.",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def startup(ctx: typer.Context) -> None:
    """Run connection checks before any sub-command."""
    if ctx.invoked_subcommand is not None:
        _check_connections()


@app.command()
def analyze(
    ticker: str = typer.Argument(..., help="Ticker symbol, e.g. AAPL"),
) -> None:
    """Run fundamental + technical analysis for a ticker."""
    logger.info(f"analyze called | ticker={ticker}")
    typer.echo(f"[analyze] {ticker} — analysis not yet implemented.")


@app.command()
def collect(
    ticker: str = typer.Argument(..., help="Ticker symbol, e.g. AAPL"),
) -> None:
    """Collect and store latest data for a ticker."""
    logger.info(f"collect called | ticker={ticker}")
    typer.echo(f"[collect] {ticker} — collector not yet implemented.")


@app.command()
def report(
    ticker: str = typer.Argument(..., help="Ticker symbol, e.g. AAPL"),
) -> None:
    """Generate a report for a ticker."""
    logger.info(f"report called | ticker={ticker}")
    typer.echo(f"[report] {ticker} — reporter not yet implemented.")


if __name__ == "__main__":
    app()
