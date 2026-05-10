import sys
import os
from pathlib import Path
from typing import List

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

_console = Console()

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
    history: bool = typer.Option(True, help="Also collect price history"),
) -> None:
    """Collect and store latest fundamentals (and optionally price history) for a ticker."""
    from src.orchestrator.orchestrator import Orchestrator

    logger.info(f"collect called | ticker={ticker} | history={history}")
    orch = Orchestrator()
    orch.collect_fundamentals(ticker)
    if history:
        orch.collect_history(ticker)


@app.command()
def report(
    ticker: str = typer.Argument(..., help="Ticker symbol, e.g. AAPL"),
) -> None:
    """Generate a report for a ticker."""
    logger.info(f"report called | ticker={ticker}")
    typer.echo(f"[report] {ticker} — reporter not yet implemented.")


@app.command()
def analisar(
    tickers: List[str] = typer.Argument(..., help="One or more ticker symbols, e.g. AAPL MSFT"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Skip opening report in browser"),
) -> None:
    """Run full analysis (fundamentals + technicals + HTML report) for one or more tickers."""
    from src.orchestrator.orchestrator import Orchestrator

    orch = Orchestrator()

    table = Table(title="Trading Analyzer — Resultados", show_header=True, header_style="bold cyan")
    table.add_column("Ticker", style="bold white", width=10)
    table.add_column("Score Geral", justify="right", width=12)
    table.add_column("Qualidade", justify="right", width=10)
    table.add_column("Valuation", justify="right", width=10)
    table.add_column("Momento", justify="right", width=10)
    table.add_column("Alertas", width=40)

    for ticker in tickers:
        ticker = ticker.upper()
        logger.info(f"analisar called | ticker={ticker}")
        try:
            result = orch.analyze(ticker, open_browser=not no_browser)

            def _fmt(v, suffix=""):
                return f"{v:.1f}{suffix}" if v is not None else "—"

            def _color(v):
                if v is None:
                    return "white"
                if v >= 70:
                    return "green"
                if v >= 45:
                    return "yellow"
                return "red"

            score_str = f"[{_color(result.score_geral)}]{_fmt(result.score_geral)}[/{_color(result.score_geral)}]"
            q_str = f"[{_color(result.score_qualidade)}]{_fmt(result.score_qualidade)}[/{_color(result.score_qualidade)}]"
            v_str = f"[{_color(result.score_valuation)}]{_fmt(result.score_valuation)}[/{_color(result.score_valuation)}]"
            m_str = f"[{_color(result.score_momento)}]{_fmt(result.score_momento)}[/{_color(result.score_momento)}]"
            alerts = "; ".join(result.alertas[:2]) if result.alertas else "—"

            table.add_row(ticker, score_str, q_str, v_str, m_str, alerts)

        except Exception as exc:
            logger.error(f"analisar falhou | ticker={ticker} | erro={exc}")
            table.add_row(ticker, "[red]ERRO[/red]", "—", "—", "—", str(exc)[:60])

    _console.print(table)


if __name__ == "__main__":
    app()
