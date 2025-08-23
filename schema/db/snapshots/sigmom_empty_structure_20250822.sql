-- SIGMOM empty-structure dump (with safety triggers)
-- MariaDB 10.4+ / MySQL 5.7+ compatible

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

-- Create and select database (edit name if needed)
CREATE DATABASE IF NOT EXISTS `sigmom_pro_v1` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */;
USE `sigmom_pro_v1`;

-- ------------------------------------------------------------------
-- Alembic version (widened to avoid truncation of long revision IDs)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `alembic_version` (
  `version_num` varchar(128) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELETE FROM `alembic_version`;
INSERT INTO `alembic_version` (`version_num`) VALUES ('20250821_enforce_positive_open_trade_insert');

-- ---------------
-- Core tables
-- ---------------

CREATE TABLE IF NOT EXISTS `users` (
  `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT,
  `email` varchar(255) NOT NULL,
  `google_sub` varchar(64) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  `avatar_url` varchar(512) DEFAULT NULL,
  `role` varchar(32) NOT NULL DEFAULT 'user',
  `referral_verified_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_users_email` (`email`),
  UNIQUE KEY `ix_users_google_sub` (`google_sub`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `raw_signals` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`payload`)),
  `fund_manager_id` varchar(64) NOT NULL,
  `received_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `ix_raw_signals_fund_manager_id` (`fund_manager_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `referral_codes` (
  `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT,
  `code_hash` varchar(255) NOT NULL,
  `email_reserved` varchar(255) DEFAULT NULL,
  `status` enum('AVAILABLE','RESERVED','CLAIMED','REVOKED') NOT NULL DEFAULT 'AVAILABLE',
  `tier` varchar(32) NOT NULL DEFAULT 'default',
  `invited_by_admin_id` bigint(20) UNSIGNED DEFAULT NULL,
  `used_by_user_id` bigint(20) UNSIGNED DEFAULT NULL,
  `used_at` datetime DEFAULT NULL,
  `expires_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code_hash` (`code_hash`),
  KEY `invited_by_admin_id` (`invited_by_admin_id`),
  KEY `used_by_user_id` (`used_by_user_id`),
  KEY `ix_referral_codes_email_reserved` (`email_reserved`),
  CONSTRAINT `referral_codes_ibfk_1` FOREIGN KEY (`invited_by_admin_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `referral_codes_ibfk_2` FOREIGN KEY (`used_by_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `strategy_open_trades` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `raw_signal_id` bigint(20) NOT NULL,
  `symbol` varchar(32) NOT NULL,
  `side` enum('long','short') NOT NULL,
  `entry_price` decimal(18,8) NOT NULL,
  `position_size` decimal(18,8) NOT NULL,
  `leverage` int(11) NOT NULL,
  `order_type` varchar(16) NOT NULL,
  `timestamp` datetime NOT NULL,
  `unrealized_pnl` decimal(18,8) NOT NULL,
  `public_id` varchar(36) NOT NULL,
  `exchange` varchar(64) NOT NULL,
  `fund_manager_id` varchar(64) NOT NULL,
  `response_data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`response_data`)),
  `exchange_order_id` varchar(100) NOT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'pending',
  `exchange_verified` tinyint(1) NOT NULL DEFAULT 0,
  `confirmed_at` datetime DEFAULT NULL,
  `last_checked_at` datetime DEFAULT NULL,
  `verification_attempts` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_strategy_open_trades_public_id` (`public_id`),
  KEY `ix_strategy_open_trades_raw_signal_id` (`raw_signal_id`),
  KEY `ix_strategy_open_trades_exchange_order_id` (`exchange_order_id`),
  KEY `ix_strategy_open_trades_status` (`status`),
  CONSTRAINT `strategy_open_trades_ibfk_1` FOREIGN KEY (`raw_signal_id`) REFERENCES `raw_signals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `strategy_trades` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `raw_signal_id` bigint(20) NOT NULL,
  `symbol` varchar(32) NOT NULL,
  `side` enum('long','short') NOT NULL,
  `entry_price` decimal(18,8) NOT NULL,
  `exit_price` decimal(18,8) NOT NULL,
  `position_size` decimal(18,8) NOT NULL,
  `realized_pnl` decimal(18,8) NOT NULL,
  `order_type` varchar(16) NOT NULL,
  `timestamp` datetime NOT NULL,
  `public_id` varchar(36) NOT NULL,
  `exchange` varchar(64) NOT NULL,
  `fund_manager_id` varchar(64) NOT NULL,
  `response_data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`response_data`)),
  `leverage` int(11) NOT NULL,
  `open_trade_public_id` varchar(36) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_strategy_trades_public_id` (`public_id`),
  KEY `ix_strategy_trades_raw_signal_id` (`raw_signal_id`),
  KEY `ix_strategy_trades_open_trade_public_id` (`open_trade_public_id`),
  CONSTRAINT `strategy_trades_ibfk_1` FOREIGN KEY (`raw_signal_id`) REFERENCES `raw_signals` (`id`) ON DELETE CASCADE,
  CONSTRAINT `strategy_trades_ibfk_2` FOREIGN KEY (`open_trade_public_id`) REFERENCES `strategy_open_trades` (`public_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------
-- Safety triggers (guards)
-- ------------------------

DROP TRIGGER IF EXISTS `trg_strategy_trades_bi_enforce_pos`;
DROP TRIGGER IF EXISTS `trg_open_trades_bi_enforce_pos`;

DELIMITER $$
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
END$$

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
END$$
DELIMITER ;

COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
