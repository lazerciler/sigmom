-- File: deploy_all.sql
-- 1) Raw sinyal tablosunu oluştur
DROP TABLE IF EXISTS raw_signals;
CREATE TABLE raw_signals (
  id              BIGINT       AUTO_INCREMENT PRIMARY KEY,
  payload         JSON         NOT NULL,
  fund_manager_id VARCHAR(64)  NOT NULL,
  received_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2) Strategy open tablosu
DROP TABLE IF EXISTS strategy_open_trades;
CREATE TABLE strategy_open_trades (
  id             BIGINT       AUTO_INCREMENT PRIMARY KEY,
  raw_signal_id  BIGINT       NOT NULL,
  symbol         VARCHAR(32)  NOT NULL,
  side           ENUM('long','short') NOT NULL,
  entry_price    DECIMAL(18,8) NOT NULL,
  position_size  DECIMAL(18,8) NOT NULL,
  leverage       INT          NOT NULL,
  order_type     VARCHAR(16)  NOT NULL,
  timestamp      DATETIME     NOT NULL,
  unrealized_pnl DECIMAL(18,8) DEFAULT 0.0,
  INDEX idx_signal_open (raw_signal_id),
  INDEX idx_sym_side      (symbol, side),
  FOREIGN KEY (raw_signal_id)
    REFERENCES raw_signals(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3) Strategy close tablosu
DROP TABLE IF EXISTS strategy_trades;
CREATE TABLE strategy_trades (
  id             BIGINT       AUTO_INCREMENT PRIMARY KEY,
  raw_signal_id  BIGINT       NOT NULL,
  symbol         VARCHAR(32)  NOT NULL,
  side           ENUM('long','short') NOT NULL,
  entry_price    DECIMAL(18,8) NOT NULL,
  exit_price     DECIMAL(18,8) NOT NULL,
  position_size  DECIMAL(18,8) NOT NULL,
  pnl            DECIMAL(18,8) NOT NULL,
  order_type     VARCHAR(16)  NOT NULL,
  timestamp      DATETIME     NOT NULL,
  INDEX idx_signal_close (raw_signal_id),
  INDEX idx_sym_time        (symbol, timestamp),
  FOREIGN KEY (raw_signal_id)
    REFERENCES raw_signals(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
