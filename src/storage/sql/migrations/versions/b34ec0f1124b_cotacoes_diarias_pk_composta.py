"""cotacoes_diarias pk composta

Revision ID: b34ec0f1124b
Revises: e847d762b36a
Create Date: 2026-05-02 17:08:14.078815

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b34ec0f1124b'
down_revision: Union[str, None] = 'e847d762b36a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('uq_cotacao_diaria', 'cotacoes_diarias', type_='unique')
    op.drop_constraint('cotacoes_diarias_pkey', 'cotacoes_diarias', type_='primary')
    op.drop_column('cotacoes_diarias', 'id')
    op.create_primary_key('cotacoes_diarias_pkey', 'cotacoes_diarias', ['ticker', 'data'])


def downgrade() -> None:
    op.drop_constraint('cotacoes_diarias_pkey', 'cotacoes_diarias', type_='primary')
    op.add_column('cotacoes_diarias', sa.Column('id', sa.UUID(), autoincrement=False, nullable=False))
    op.create_primary_key('cotacoes_diarias_pkey', 'cotacoes_diarias', ['ticker'])
    op.create_unique_constraint('uq_cotacao_diaria', 'cotacoes_diarias', ['ticker', 'data'])
