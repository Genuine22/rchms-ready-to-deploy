-- ============================================================
-- RCHMS - Add Starlink voucher username column
-- Run this in MySQL Workbench (same way as previous migrations)
-- to add username+password style voucher credentials, matching
-- how real WiFi/captive-portal voucher systems issue logins.
-- ============================================================

USE rchms_db;

ALTER TABLE starlink_subscriptions
ADD COLUMN voucher_username VARCHAR(20) NULL UNIQUE AFTER plan_id;

-- Backfill existing subscriptions with a generated username, so any
-- vouchers already issued before this upgrade also get a username
-- (format: SL0001, SL0002... based on subscription_id).
UPDATE starlink_subscriptions
SET voucher_username = CONCAT('SL', LPAD(subscription_id, 4, '0'))
WHERE voucher_username IS NULL;
