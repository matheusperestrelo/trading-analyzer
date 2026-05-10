"""schema mvp alignment

Revision ID: a4f8b2c1d9e0
Revises: b34ec0f1124b
Create Date: 2026-05-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4f8b2c1d9e0"
down_revision: Union[str, None] = "b34ec0f1124b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # tickers: replace UUID PK with varchar ticker PK, rename exchange column
    # -------------------------------------------------------------------------
    op.drop_constraint("tickers_pkey", "tickers", type_="primary")
    op.drop_column("tickers", "id")
    op.drop_constraint("tickers_ticker_key", "tickers", type_="unique")
    op.create_primary_key("tickers_pkey", "tickers", ["ticker"])
    op.drop_column("tickers", "exchange")
    op.add_column("tickers", sa.Column("segmento_listagem", sa.String(), nullable=True))
    op.execute(
        "ALTER TABLE tickers ALTER COLUMN criado_em TYPE TIMESTAMP WITH TIME ZONE "
        "USING criado_em AT TIME ZONE 'UTC'"
    )
    op.execute("ALTER TABLE tickers ALTER COLUMN criado_em SET DEFAULT now()")

    # -------------------------------------------------------------------------
    # fundamentos_snapshot: rename coletado_em, drop ev_ebitda/margem_ebitda,
    # add market_cap, float→numeric, json→jsonb, server_default on id
    # -------------------------------------------------------------------------
    op.drop_constraint("uq_snapshot", "fundamentos_snapshot", type_="unique")
    op.alter_column(
        "fundamentos_snapshot",
        "coletado_em",
        new_column_name="data_coleta",
    )
    op.execute(
        "ALTER TABLE fundamentos_snapshot ALTER COLUMN data_coleta "
        "TYPE TIMESTAMP WITH TIME ZONE USING data_coleta AT TIME ZONE 'UTC'"
    )
    op.drop_column("fundamentos_snapshot", "ev_ebitda")
    op.drop_column("fundamentos_snapshot", "margem_ebitda")
    op.add_column(
        "fundamentos_snapshot",
        sa.Column("market_cap", sa.BigInteger(), nullable=True),
    )
    for col in ("pl", "pvp", "dy", "roe", "roic", "margem_liquida",
                "divida_liquida_ebitda", "liquidez_corrente", "cagr_receita_5a", "payout"):
        op.execute(
            f"ALTER TABLE fundamentos_snapshot ALTER COLUMN {col} "
            f"TYPE NUMERIC USING {col}::numeric"
        )
    op.execute(
        "ALTER TABLE fundamentos_snapshot ALTER COLUMN raw_json "
        "TYPE JSONB USING raw_json::jsonb"
    )
    op.execute(
        "ALTER TABLE fundamentos_snapshot ALTER COLUMN id "
        "SET DEFAULT gen_random_uuid()"
    )

    # -------------------------------------------------------------------------
    # cotacoes_diarias: float→numeric, integer volume→bigint, create hypertable
    # -------------------------------------------------------------------------
    for col in ("abertura", "maxima", "minima", "fechamento"):
        op.execute(
            f"ALTER TABLE cotacoes_diarias ALTER COLUMN {col} "
            f"TYPE NUMERIC USING {col}::numeric"
        )
    op.execute(
        "ALTER TABLE cotacoes_diarias ALTER COLUMN volume "
        "TYPE BIGINT USING volume::bigint"
    )
    op.execute(
        "SELECT create_hypertable('cotacoes_diarias', 'data', if_not_exists => TRUE)"
    )

    # -------------------------------------------------------------------------
    # relatorios: rename gerado_em→data, drop extra scores, add criado_em,
    # server_default on id
    # -------------------------------------------------------------------------
    op.alter_column("relatorios", "gerado_em", new_column_name="data")
    op.execute(
        "ALTER TABLE relatorios ALTER COLUMN data "
        "TYPE TIMESTAMP WITH TIME ZONE USING data AT TIME ZONE 'UTC'"
    )
    op.drop_column("relatorios", "score_qualidade")
    op.drop_column("relatorios", "score_valuation")
    op.drop_column("relatorios", "score_momento")
    op.execute(
        "ALTER TABLE relatorios ALTER COLUMN score_geral "
        "TYPE NUMERIC USING score_geral::numeric"
    )
    op.add_column(
        "relatorios",
        sa.Column(
            "criado_em",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.execute(
        "ALTER TABLE relatorios ALTER COLUMN id SET DEFAULT gen_random_uuid()"
    )


def downgrade() -> None:
    # relatorios
    op.drop_column("relatorios", "criado_em")
    op.execute("ALTER TABLE relatorios ALTER COLUMN id DROP DEFAULT")
    op.add_column("relatorios", sa.Column("score_momento", sa.Float(), nullable=True))
    op.add_column("relatorios", sa.Column("score_valuation", sa.Float(), nullable=True))
    op.add_column("relatorios", sa.Column("score_qualidade", sa.Float(), nullable=True))
    op.alter_column("relatorios", "data", new_column_name="gerado_em")

    # cotacoes_diarias (cannot undo hypertable, skip)
    op.execute(
        "ALTER TABLE cotacoes_diarias ALTER COLUMN volume TYPE INTEGER USING volume::integer"
    )
    for col in ("abertura", "maxima", "minima", "fechamento"):
        op.execute(
            f"ALTER TABLE cotacoes_diarias ALTER COLUMN {col} TYPE FLOAT USING {col}::float"
        )

    # fundamentos_snapshot
    op.execute("ALTER TABLE fundamentos_snapshot ALTER COLUMN id DROP DEFAULT")
    op.execute(
        "ALTER TABLE fundamentos_snapshot ALTER COLUMN raw_json TYPE JSON USING raw_json::json"
    )
    for col in ("pl", "pvp", "dy", "roe", "roic", "margem_liquida",
                "divida_liquida_ebitda", "liquidez_corrente", "cagr_receita_5a", "payout"):
        op.execute(
            f"ALTER TABLE fundamentos_snapshot ALTER COLUMN {col} TYPE FLOAT USING {col}::float"
        )
    op.drop_column("fundamentos_snapshot", "market_cap")
    op.add_column("fundamentos_snapshot", sa.Column("margem_ebitda", sa.Float(), nullable=True))
    op.add_column("fundamentos_snapshot", sa.Column("ev_ebitda", sa.Float(), nullable=True))
    op.alter_column("fundamentos_snapshot", "data_coleta", new_column_name="coletado_em")
    op.create_unique_constraint(
        "uq_snapshot", "fundamentos_snapshot", ["ticker", "coletado_em", "fonte"]
    )

    # tickers
    op.drop_column("tickers", "segmento_listagem")
    op.add_column("tickers", sa.Column("exchange", sa.String(50), nullable=True))
    op.drop_constraint("tickers_pkey", "tickers", type_="primary")
    op.add_column("tickers", sa.Column("id", sa.UUID(), nullable=False))
    op.create_primary_key("tickers_pkey", "tickers", ["id"])
    op.create_unique_constraint("tickers_ticker_key", "tickers", ["ticker"])
