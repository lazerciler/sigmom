"""users + referral_codes (FK'li, MySQL 5.7 uyumlu)

Revision ID: 20250809_users_and_referrals
Revises: 0d7470062267
Create Date: 2025-08-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# Alembic IDs
revision: str = "20250809_users_and_referrals"
down_revision: Union[str, Sequence[str], None] = "0d7470062267"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) USERS
    op.create_table(
        "users",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("google_sub", sa.String(64), nullable=True, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="user"),
        sa.Column("referral_verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    # 2) REFERRAL_CODES (users'a FK'li)
    op.create_table(
        "referral_codes",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("code_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("email_reserved", sa.String(255), nullable=True, index=True),
        sa.Column(
            "status",
            sa.Enum("RESERVED", "CLAIMED", "REVOKED", name="referral_status"),
            nullable=False,
            server_default="RESERVED",
        ),
        sa.Column("tier", sa.String(32), nullable=False, server_default="default"),
        sa.Column("invited_by_admin_id", mysql.BIGINT(unsigned=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("used_by_user_id",    mysql.BIGINT(unsigned=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("referral_codes")
    op.drop_table("users")
    # ENUM'u da temizle
    try:
        sa.Enum(name="referral_status").drop(op.get_bind(), checkfirst=True)
    except Exception:
        pass
