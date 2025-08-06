"""rename pnl to realized_pnl in strategy_trades

Revision ID: 1a48d99bcb71
Revises: db533d7c9dfa
Create Date: 2025-08-04 12:00:33.146836

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1a48d99bcb71"
down_revision: Union[str, Sequence[str], None] = "db533d7c9dfa"
branch_labels: None  # Union[str, Sequence[str], None] = None
depends_on: None  # Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "strategy_trades",
        "pnl",
        new_column_name="realized_pnl",
        existing_type=sa.Numeric(18, 8),
    )


def downgrade() -> None:
    op.alter_column(
        "strategy_trades",
        "realized_pnl",
        new_column_name="pnl",
        existing_type=sa.Numeric(18, 8),
    )
