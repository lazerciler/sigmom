-- SIGMOM schema guard patch (MariaDB 10.4+)
-- 1) Widen alembic_version.version_num to avoid truncation
ALTER TABLE `alembic_version` MODIFY `version_num` VARCHAR(128) NOT NULL;

-- 2) Stamp the current HEAD revision (edit if your head differs)
UPDATE `alembic_version` SET `version_num` = '20250821_enforce_positive_open_trade_insert';

-- 3) Recreate safety triggers
DROP TRIGGER IF EXISTS `trg_strategy_trades_bi_enforce_pos`;
CREATE TRIGGER `trg_strategy_trades_bi_enforce_pos`
BEFORE INSERT ON `strategy_trades`
FOR EACH ROW
BEGIN
  IF NEW.`exit_price` <= 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'exit_price must be > 0';
  END IF;
  IF NEW.`position_size` <= 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'position_size must be > 0';
  END IF;
END;

DROP TRIGGER IF EXISTS `trg_open_trades_bi_enforce_pos`;
CREATE TRIGGER `trg_open_trades_bi_enforce_pos`
BEFORE INSERT ON `strategy_open_trades`
FOR EACH ROW
BEGIN
  IF NEW.`entry_price` <= 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'entry_price must be > 0';
  END IF;
  IF NEW.`position_size` <= 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'position_size must be > 0';
  END IF;
  IF NEW.`leverage` IS NULL OR NEW.`leverage` <= 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'leverage must be > 0';
  END IF;
END;
