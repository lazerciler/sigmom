"""Add leverage to strategy_trades

Revision ID: ef846562f771
Revises: 024d7df44a14
Create Date: 2025-07-28 18:32:52.525185

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ef846562f771"
down_revision: Union[str, Sequence[str], None] = "024d7df44a14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("strategy_trades", sa.Column("leverage", sa.Integer(), nullable=True))
    pass


def downgrade() -> None:
    op.drop_column("strategy_trades", "leverage")
    pass
