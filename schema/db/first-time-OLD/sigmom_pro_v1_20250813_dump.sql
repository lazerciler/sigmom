-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Anamakine: 127.0.0.1
-- Üretim Zamanı: 14 Ağu 2025, 00:27:44
-- Sunucu sürümü: 10.4.28-MariaDB
-- PHP Sürümü: 8.2.4

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Veritabanı: `sigmom_pro_v1`
--

-- --------------------------------------------------------

--
-- Tablo için tablo yapısı `alembic_version`
--

CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Tablo döküm verisi `alembic_version`
--

INSERT INTO `alembic_version` (`version_num`) VALUES
('20250810_add_available_to_referr');

-- --------------------------------------------------------

--
-- Tablo için tablo yapısı `raw_signals`
--

CREATE TABLE `raw_signals` (
  `id` bigint(20) NOT NULL,
  `payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`payload`)),
  `fund_manager_id` varchar(64) NOT NULL,
  `received_at` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Tablo döküm verisi `raw_signals`
--

INSERT INTO `raw_signals` (`id`, `payload`, `fund_manager_id`, `received_at`) VALUES
(214, '{\"mode\": \"open\", \"symbol\": \"BTCUSDT\", \"side\": \"long\", \"position_size\": 0.001, \"order_type\": \"market\", \"exchange\": \"binance_futures_testnet\", \"timestamp\": \"2025-08-13T23:46:00+00:00\", \"fund_manager_id\": \"fxmgr_tj2025_rQz91\", \"reduce_only\": false, \"entry_price\": 58000.0, \"leverage\": 5, \"order_id\": null, \"exit_price\": null, \"public_id\": null}', 'fxmgr_tj2025_rQz91', '2025-08-13 23:47:08'),
(215, '{\"mode\": \"close\", \"symbol\": \"BTCUSDT\", \"side\": \"long\", \"position_size\": 0.001, \"order_type\": \"market\", \"exchange\": \"binance_futures_testnet\", \"timestamp\": \"2025-08-13T23:48:00+00:00\", \"fund_manager_id\": \"fxmgr_tj2025_rQz91\", \"reduce_only\": false, \"entry_price\": null, \"leverage\": null, \"order_id\": null, \"exit_price\": 60100.0, \"public_id\": null}', 'fxmgr_tj2025_rQz91', '2025-08-13 23:48:14'),
(216, '{\"mode\": \"close\", \"symbol\": \"BTCUSDT\", \"side\": \"long\", \"position_size\": 0.001, \"order_type\": \"market\", \"exchange\": \"binance_futures_testnet\", \"timestamp\": \"2025-08-13T23:48:00+00:00\", \"fund_manager_id\": \"fxmgr_tj2025_rQz91\", \"reduce_only\": false, \"entry_price\": null, \"leverage\": null, \"order_id\": null, \"exit_price\": 60100.0, \"public_id\": null}', 'fxmgr_tj2025_rQz91', '2025-08-13 23:49:17');

-- --------------------------------------------------------

--
-- Tablo için tablo yapısı `referral_codes`
--

CREATE TABLE `referral_codes` (
  `id` bigint(20) UNSIGNED NOT NULL,
  `code_hash` varchar(255) NOT NULL,
  `email_reserved` varchar(255) DEFAULT NULL,
  `status` enum('AVAILABLE','RESERVED','CLAIMED','REVOKED') NOT NULL DEFAULT 'AVAILABLE',
  `tier` varchar(32) NOT NULL DEFAULT 'default',
  `invited_by_admin_id` bigint(20) UNSIGNED DEFAULT NULL,
  `used_by_user_id` bigint(20) UNSIGNED DEFAULT NULL,
  `used_at` datetime DEFAULT NULL,
  `expires_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Tablo döküm verisi `referral_codes`
--

INSERT INTO `referral_codes` (`id`, `code_hash`, `email_reserved`, `status`, `tier`, `invited_by_admin_id`, `used_by_user_id`, `used_at`, `expires_at`) VALUES
(242, '$2b$12$6.v/K8HU6yz3KjUEwqWZnuZtX8dBuPcv04W8l9MQq1BUOiXdb8VmG', 'tanju.ergan@gmail.com', 'CLAIMED', 'default', 22, 22, '2025-08-11 13:43:07', NULL),
(243, '$2b$12$3mcZ8CMxWgQIm3WrxFVhFum5u43Az9y8djMxPM20m/U11m/k.JO.e', NULL, 'AVAILABLE', 'default', 22, NULL, NULL, NULL),
(244, '$2b$12$kyzKuCTZeZiwHywibz28h.xhJeB59tfvKQMpBa46bCYRWLBPjWvw2', NULL, 'AVAILABLE', 'default', 22, NULL, NULL, NULL);

-- --------------------------------------------------------

--
-- Tablo için tablo yapısı `strategy_open_trades`
--

CREATE TABLE `strategy_open_trades` (
  `id` bigint(20) NOT NULL,
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
  `verification_attempts` int(11) NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Tablo döküm verisi `strategy_open_trades`
--

INSERT INTO `strategy_open_trades` (`id`, `raw_signal_id`, `symbol`, `side`, `entry_price`, `position_size`, `leverage`, `order_type`, `timestamp`, `unrealized_pnl`, `public_id`, `exchange`, `fund_manager_id`, `response_data`, `exchange_order_id`, `status`, `exchange_verified`, `confirmed_at`, `last_checked_at`, `verification_attempts`) VALUES
(105, 214, 'BTCUSDT', 'long', 121145.25000000, 0.00100000, 5, 'market', '2025-08-13 23:46:00', 0.00000000, '811cb74c-65f2-4279-a622-b68442d64fde', 'binance_futures_testnet', 'fxmgr_tj2025_rQz91', NULL, '5581098463', 'closed', 1, '2025-08-13 20:47:12', '2025-08-13 20:47:12', 0);

-- --------------------------------------------------------

--
-- Tablo için tablo yapısı `strategy_trades`
--

CREATE TABLE `strategy_trades` (
  `id` bigint(20) NOT NULL,
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
  `open_trade_public_id` varchar(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Tablo döküm verisi `strategy_trades`
--

INSERT INTO `strategy_trades` (`id`, `raw_signal_id`, `symbol`, `side`, `entry_price`, `exit_price`, `position_size`, `realized_pnl`, `order_type`, `timestamp`, `public_id`, `exchange`, `fund_manager_id`, `response_data`, `leverage`, `open_trade_public_id`) VALUES
(42, 214, 'BTCUSDT', 'long', 121145.25000000, 122911.95775362, 0.00100000, 1.76670775, 'market', '2025-08-13 20:49:19', '01982f82-2e6f-4ec6-a490-01d3bb3ddb18', 'binance_futures_testnet', 'fxmgr_tj2025_rQz91', '{}', 5, '811cb74c-65f2-4279-a622-b68442d64fde'),
(43, 214, 'BTCUSDT', 'long', 121145.25000000, 122912.63166667, 0.00100000, 1.76738167, 'market', '2025-08-13 20:49:19', 'ab186896-1aa9-4649-ad98-ce79c7d9a2d4', 'binance_futures_testnet', 'fxmgr_tj2025_rQz91', '{}', 5, '811cb74c-65f2-4279-a622-b68442d64fde');

-- --------------------------------------------------------

--
-- Tablo için tablo yapısı `users`
--

CREATE TABLE `users` (
  `id` bigint(20) UNSIGNED NOT NULL,
  `email` varchar(255) NOT NULL,
  `google_sub` varchar(64) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  `avatar_url` varchar(512) DEFAULT NULL,
  `role` varchar(32) NOT NULL DEFAULT 'user',
  `referral_verified_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Tablo döküm verisi `users`
--

INSERT INTO `users` (`id`, `email`, `google_sub`, `name`, `avatar_url`, `role`, `referral_verified_at`, `created_at`, `updated_at`) VALUES
(12, 'demo1@asiluye.com', NULL, 'Demo Kullanıcı 1', NULL, 'user', NULL, '2025-08-09 02:49:15', NULL),
(13, 'demo2@asiluye.com', NULL, 'Demo Kullanıcı 2', NULL, 'user', NULL, '2025-08-09 02:49:16', NULL),
(14, 'demo3@asiluye.com', NULL, 'Demo Kullanıcı 3', NULL, 'user', NULL, '2025-08-09 02:49:16', NULL),
(15, 'demo4@asiluye.com', NULL, 'Demo Kullanıcı 4', NULL, 'user', NULL, '2025-08-09 02:49:16', NULL),
(16, 'demo5@asiluye.com', NULL, 'Demo Kullanıcı 5', NULL, 'user', NULL, '2025-08-09 02:49:16', NULL),
(17, 'demo6@asiluye.com', NULL, 'Demo Kullanıcı 6', NULL, 'user', NULL, '2025-08-09 02:49:16', NULL),
(18, 'demo7@asiluye.com', NULL, 'Demo Kullanıcı 7', NULL, 'user', NULL, '2025-08-09 02:49:17', NULL),
(19, 'demo8@asiluye.com', NULL, 'Demo Kullanıcı 8', NULL, 'user', NULL, '2025-08-09 02:49:17', NULL),
(20, 'demo9@asiluye.com', NULL, 'Demo Kullanıcı 9', NULL, 'user', NULL, '2025-08-09 02:49:17', NULL),
(21, 'demo10@asiluye.com', NULL, 'Demo Kullanıcı 10', NULL, 'user', NULL, '2025-08-09 02:49:17', NULL),
(22, 'tanju.ergan@gmail.com', '102982210295348542271', 'Tanju Ergan', 'https://lh3.googleusercontent.com/a/ACg8ocLviT7P7ZKtTR7QpvDyYAplcEYSdZS6RIL8FYb40uW7jx7sQA=s96-c', 'user', '2025-08-11 13:43:07', '2025-08-09 06:59:29', '2025-08-13 05:16:34');

--
-- Dökümü yapılmış tablolar için indeksler
--

--
-- Tablo için indeksler `alembic_version`
--
ALTER TABLE `alembic_version`
  ADD PRIMARY KEY (`version_num`);

--
-- Tablo için indeksler `raw_signals`
--
ALTER TABLE `raw_signals`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_raw_signals_fund_manager_id` (`fund_manager_id`);

--
-- Tablo için indeksler `referral_codes`
--
ALTER TABLE `referral_codes`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `code_hash` (`code_hash`),
  ADD KEY `invited_by_admin_id` (`invited_by_admin_id`),
  ADD KEY `used_by_user_id` (`used_by_user_id`),
  ADD KEY `ix_referral_codes_email_reserved` (`email_reserved`);

--
-- Tablo için indeksler `strategy_open_trades`
--
ALTER TABLE `strategy_open_trades`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `ix_strategy_open_trades_public_id` (`public_id`),
  ADD KEY `ix_strategy_open_trades_raw_signal_id` (`raw_signal_id`),
  ADD KEY `ix_strategy_open_trades_exchange_order_id` (`exchange_order_id`),
  ADD KEY `ix_strategy_open_trades_status` (`status`);

--
-- Tablo için indeksler `strategy_trades`
--
ALTER TABLE `strategy_trades`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `ix_strategy_trades_public_id` (`public_id`),
  ADD KEY `ix_strategy_trades_raw_signal_id` (`raw_signal_id`),
  ADD KEY `ix_strategy_trades_open_trade_public_id` (`open_trade_public_id`);

--
-- Tablo için indeksler `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `ix_users_email` (`email`),
  ADD UNIQUE KEY `ix_users_google_sub` (`google_sub`);

--
-- Dökümü yapılmış tablolar için AUTO_INCREMENT değeri
--

--
-- Tablo için AUTO_INCREMENT değeri `raw_signals`
--
ALTER TABLE `raw_signals`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=217;

--
-- Tablo için AUTO_INCREMENT değeri `referral_codes`
--
ALTER TABLE `referral_codes`
  MODIFY `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=245;

--
-- Tablo için AUTO_INCREMENT değeri `strategy_open_trades`
--
ALTER TABLE `strategy_open_trades`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=106;

--
-- Tablo için AUTO_INCREMENT değeri `strategy_trades`
--
ALTER TABLE `strategy_trades`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=44;

--
-- Tablo için AUTO_INCREMENT değeri `users`
--
ALTER TABLE `users`
  MODIFY `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=23;

--
-- Dökümü yapılmış tablolar için kısıtlamalar
--

--
-- Tablo kısıtlamaları `referral_codes`
--
ALTER TABLE `referral_codes`
  ADD CONSTRAINT `referral_codes_ibfk_1` FOREIGN KEY (`invited_by_admin_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  ADD CONSTRAINT `referral_codes_ibfk_2` FOREIGN KEY (`used_by_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL;

--
-- Tablo kısıtlamaları `strategy_open_trades`
--
ALTER TABLE `strategy_open_trades`
  ADD CONSTRAINT `strategy_open_trades_ibfk_1` FOREIGN KEY (`raw_signal_id`) REFERENCES `raw_signals` (`id`) ON DELETE CASCADE;

--
-- Tablo kısıtlamaları `strategy_trades`
--
ALTER TABLE `strategy_trades`
  ADD CONSTRAINT `strategy_trades_ibfk_1` FOREIGN KEY (`raw_signal_id`) REFERENCES `raw_signals` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `strategy_trades_ibfk_2` FOREIGN KEY (`open_trade_public_id`) REFERENCES `strategy_open_trades` (`public_id`) ON DELETE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
