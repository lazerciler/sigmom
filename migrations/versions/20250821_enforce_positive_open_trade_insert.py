# alembic/versions/20250821_enforce_positive_open_trade_insert.py
from alembic import op

revision = "20250821_enforce_positive_open_trade_insert"
down_revision = "20250810_add_available_to_referral_status_enum"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
    DROP TRIGGER IF EXISTS trg_open_trades_bi_enforce_pos;
    """
    )
    op.execute(
        """
    CREATE TRIGGER trg_open_trades_bi_enforce_pos
    BEFORE INSERT ON strategy_open_trades
    FOR EACH ROW
    BEGIN
      IF NEW.entry_price <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'entry_price must be > 0';
      END IF;
      IF NEW.position_size <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'position_size must be > 0';
      END IF;
      IF NEW.leverage IS NULL OR NEW.leverage <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'leverage must be > 0';
      END IF;
    END;
    """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_open_trades_bi_enforce_pos;")
