"""add verification fields to strategy_open_trades

Revision ID: ba36e1f88c74
Revises: 1a48d99bcb71
Create Date: 2025-08-05 06:47:39.398068

"""

from typing import Sequence, Union

# from alembic import op
# import sqlalchemy as sa
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "ba36e1f88c74"
down_revision: Union[str, Sequence[str], None] = "1a48d99bcb71"
branch_labels: None
depends_on: None


def upgrade():
    op.add_column(
        "strategy_open_trades",
        sa.Column("exchange_order_id", sa.String(100), nullable=False),
    )
    op.add_column(
        "strategy_open_trades",
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "strategy_open_trades",
        sa.Column(
            "exchange_verified", sa.Boolean(), nullable=False, server_default=text("0")
        ),
    )
    op.add_column(
        "strategy_open_trades",
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "strategy_open_trades",
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "strategy_open_trades",
        sa.Column(
            "verification_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_index(
        op.f("ix_strategy_open_trades_exchange_order_id"),
        "strategy_open_trades",
        ["exchange_order_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_strategy_open_trades_exchange_order_id"),
        table_name="strategy_open_trades",
    )
    op.drop_column("strategy_open_trades", "verification_attempts")
    op.drop_column("strategy_open_trades", "last_checked_at")
    op.drop_column("strategy_open_trades", "confirmed_at")
    op.drop_column("strategy_open_trades", "exchange_verified")
    op.drop_column("strategy_open_trades", "status")
    op.drop_column("strategy_open_trades", "exchange_order_id")
