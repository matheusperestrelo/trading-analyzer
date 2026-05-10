import json
from typing import Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.collectors.schemas import CotacaoDiariaSchema, FundamentosSnapshotSchema


class Repository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert_ticker(
        self,
        ticker: str,
        nome: str,
        setor: str,
        subsetor: str,
        segmento_listagem: str,
    ) -> None:
        stmt = text("""
            INSERT INTO tickers (ticker, nome, setor, subsetor, segmento_listagem)
            VALUES (:ticker, :nome, :setor, :subsetor, :segmento_listagem)
            ON CONFLICT (ticker) DO UPDATE SET
                nome = EXCLUDED.nome,
                setor = EXCLUDED.setor,
                subsetor = EXCLUDED.subsetor,
                segmento_listagem = EXCLUDED.segmento_listagem
        """)
        try:
            with self._engine.begin() as conn:
                conn.execute(stmt, {
                    "ticker": ticker,
                    "nome": nome,
                    "setor": setor,
                    "subsetor": subsetor,
                    "segmento_listagem": segmento_listagem,
                })
        except Exception as e:
            logger.error(f"upsert_ticker falhou | ticker={ticker} | erro={e}")
            raise

    def insert_fundamentos_snapshot(self, schema: FundamentosSnapshotSchema) -> str:
        stmt = text("""
            INSERT INTO fundamentos_snapshot (
                id, ticker, data_coleta, fonte,
                pl, pvp, dy, roe, roic, margem_liquida,
                divida_liquida_ebitda, liquidez_corrente, cagr_receita_5a, payout,
                market_cap, text_description, raw_json
            ) VALUES (
                gen_random_uuid(), :ticker, now(), :fonte,
                :pl, :pvp, :dy, :roe, :roic, :margem_liquida,
                :divida_liquida_ebitda, :liquidez_corrente, :cagr_receita_5a, :payout,
                :market_cap, :text_description, :raw_json::jsonb
            ) RETURNING id
        """)
        params = {
            "ticker": schema.ticker,
            "fonte": schema.fonte,
            "pl": schema.pl,
            "pvp": schema.pvp,
            "dy": schema.dy,
            "roe": schema.roe,
            "roic": schema.roic,
            "margem_liquida": schema.margem_liquida,
            "divida_liquida_ebitda": schema.divida_liquida_ebitda,
            "liquidez_corrente": schema.liquidez_corrente,
            "cagr_receita_5a": schema.cagr_receita_5a,
            "payout": schema.payout,
            "market_cap": None,
            "text_description": schema.text_description,
            "raw_json": json.dumps(schema.raw_json),
        }
        try:
            with self._engine.begin() as conn:
                result = conn.execute(stmt, params)
                row_id = str(result.scalar_one())
                logger.debug(
                    f"insert_fundamentos_snapshot ok | ticker={schema.ticker} | fonte={schema.fonte} | id={row_id}"
                )
                return row_id
        except Exception as e:
            logger.error(
                f"insert_fundamentos_snapshot falhou | ticker={schema.ticker} | fonte={schema.fonte} | erro={e}"
            )
            raise

    def bulk_insert_cotacoes(self, cotacoes: list[CotacaoDiariaSchema]) -> int:
        if not cotacoes:
            return 0

        stmt = text("""
            INSERT INTO cotacoes_diarias (ticker, data, abertura, maxima, minima, fechamento, volume)
            VALUES (:ticker, :data, :abertura, :maxima, :minima, :fechamento, :volume)
            ON CONFLICT (ticker, data) DO NOTHING
        """)
        rows = [c.model_dump() for c in cotacoes]
        try:
            with self._engine.begin() as conn:
                result = conn.execute(stmt, rows)
                inserted = result.rowcount
                logger.debug(
                    f"bulk_insert_cotacoes | ticker={cotacoes[0].ticker} | enviadas={len(rows)} | inseridas={inserted}"
                )
                return inserted
        except Exception as e:
            logger.error(
                f"bulk_insert_cotacoes falhou | ticker={cotacoes[0].ticker if cotacoes else '?'} | erro={e}"
            )
            raise

    def get_latest_snapshot(self, ticker: str) -> Optional[dict]:
        stmt = text("""
            SELECT * FROM fundamentos_snapshot
            WHERE ticker = :ticker
            ORDER BY data_coleta DESC
            LIMIT 1
        """)
        try:
            with self._engine.connect() as conn:
                result = conn.execute(stmt, {"ticker": ticker})
                row = result.mappings().first()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"get_latest_snapshot falhou | ticker={ticker} | erro={e}")
            raise

    def get_cotacoes(self, ticker: str, limit: int = 300) -> list[dict]:
        """Return up to `limit` daily quotes ordered oldest-first."""
        stmt = text("""
            SELECT ticker, data, abertura, maxima, minima, fechamento, volume
            FROM cotacoes_diarias
            WHERE ticker = :ticker
            ORDER BY data DESC
            LIMIT :limit
        """)
        try:
            with self._engine.connect() as conn:
                result = conn.execute(stmt, {"ticker": ticker, "limit": limit})
                rows = result.mappings().all()
                # Reverse so oldest comes first (ascending date order for indicators)
                return [dict(r) for r in reversed(rows)]
        except Exception as e:
            logger.error(f"get_cotacoes falhou | ticker={ticker} | erro={e}")
            raise

    def insert_relatorio(self, ticker: str, caminho: str, score_geral: float) -> str:
        """Insert a report record; returns the new UUID."""
        stmt = text("""
            INSERT INTO relatorios (id, ticker, data, caminho, score_geral)
            VALUES (gen_random_uuid(), :ticker, now(), :caminho, :score_geral)
            RETURNING id
        """)
        try:
            with self._engine.begin() as conn:
                result = conn.execute(stmt, {
                    "ticker": ticker,
                    "caminho": caminho,
                    "score_geral": score_geral,
                })
                row_id = str(result.scalar_one())
                logger.debug(
                    f"insert_relatorio ok | ticker={ticker} | score_geral={score_geral} | id={row_id}"
                )
                return row_id
        except Exception as e:
            logger.error(f"insert_relatorio falhou | ticker={ticker} | erro={e}")
            raise
