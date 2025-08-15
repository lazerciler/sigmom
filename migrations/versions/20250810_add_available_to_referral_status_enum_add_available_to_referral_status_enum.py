"""add AVAILABLE to referral_status enum

Revision ID: 20250810_add_available_to_referral_status_enum
Revises: 20250809_users_and_referrals
Create Date: 2025-08-10 08:43:47.178439

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250810_add_available_to_referral_status_enum"
down_revision: Union[str, Sequence[str], None] = "20250809_users_and_referrals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE referral_codes
        MODIFY status ENUM('AVAILABLE','RESERVED','CLAIMED','REVOKED')
        NOT NULL DEFAULT 'AVAILABLE';
    """
    )
    op.execute(
        """
        UPDATE referral_codes
        SET status='AVAILABLE'
        WHERE status='' OR status IS NULL;
    """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE referral_codes
        SET status='RESERVED'
        WHERE status='AVAILABLE';
    """
    )
    op.execute(
        """
        ALTER TABLE referral_codes
        MODIFY status ENUM('RESERVED','CLAIMED','REVOKED')
        NOT NULL DEFAULT 'RESERVED';
    """
    )
