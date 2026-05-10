from loguru import logger

from src.collectors.finviz_collector import FinvizCollector
from src.collectors.schemas import FundamentosSnapshotSchema
from src.collectors.yfinance_collector import YfinanceCollector
from src.processors.fundamentals import FundamentalsProcessor, ScoreResult
from src.reporters.html_reporter import HtmlReporter
from src.storage.sql.connection import get_engine
from src.storage.sql.repository import Repository


class Orchestrator:
    def __init__(self) -> None:
        self._repo = Repository(get_engine())
        self._finviz = FinvizCollector()
        self._yfinance = YfinanceCollector()
        self._processor = FundamentalsProcessor()
        self._reporter = HtmlReporter(self._repo)

    def collect_fundamentals(self, ticker: str) -> None:
        ticker = ticker.upper()
        logger.info(f"collect_fundamentals start | ticker={ticker}")

        result = self._finviz.collect(ticker)
        if not result.success:
            logger.warning(f"collect_fundamentals falhou no collector | ticker={ticker} | erro={result.error}")
            return

        self._repo.upsert_ticker(
            ticker=result.ticker,
            nome="",
            setor="",
            subsetor="",
            segmento_listagem="",
        )

        schema = FundamentosSnapshotSchema(
            ticker=result.ticker,
            fonte=result.source,
            raw_json=result.raw_json,
            text_description=result.text_description,
            **result.fundamentals,
        )
        snapshot_id = self._repo.insert_fundamentos_snapshot(schema)
        logger.info(f"collect_fundamentals ok | ticker={ticker} | snapshot_id={snapshot_id}")

    def collect_history(self, ticker: str, period: str = "5y") -> None:
        ticker = ticker.upper()
        logger.info(f"collect_history start | ticker={ticker} | period={period}")

        cotacoes = self._yfinance.collect_history(ticker, period=period)
        if not cotacoes:
            logger.warning(f"collect_history retornou vazio | ticker={ticker}")
            return

        self._repo.upsert_ticker(
            ticker=ticker,
            nome="",
            setor="",
            subsetor="",
            segmento_listagem="",
        )

        inserted = self._repo.bulk_insert_cotacoes(cotacoes)
        logger.info(f"collect_history ok | ticker={ticker} | registros={inserted}")

    def collect_all(self, ticker: str) -> None:
        self.collect_fundamentals(ticker)
        self.collect_history(ticker)

    def analyze(self, ticker: str, open_browser: bool = True) -> ScoreResult:
        """Run full analysis pipeline: fetch latest snapshot + cotacoes, score, report."""
        ticker = ticker.upper()
        logger.info(f"analyze start | ticker={ticker}")

        snapshot = self._repo.get_latest_snapshot(ticker)
        if snapshot is None:
            logger.warning(
                f"analyze | snapshot não encontrado para {ticker} — coletando agora"
            )
            self.collect_fundamentals(ticker)
            snapshot = self._repo.get_latest_snapshot(ticker)

        if snapshot is None:
            raise RuntimeError(
                f"Não foi possível obter dados fundamentalistas para {ticker}. "
                "Verifique se o ticker é válido e tente novamente."
            )

        cotacoes = self._repo.get_cotacoes(ticker, limit=300)
        if not cotacoes:
            logger.info(f"analyze | cotacoes não encontradas para {ticker} — coletando agora")
            self.collect_history(ticker)
            cotacoes = self._repo.get_cotacoes(ticker, limit=300)

        result = self._processor.process(ticker, snapshot, cotacoes)
        report_path = self._reporter.generate(result, snapshot, open_browser=open_browser)
        logger.info(f"analyze done | ticker={ticker} | score={result.score_geral} | report={report_path}")
        return result
