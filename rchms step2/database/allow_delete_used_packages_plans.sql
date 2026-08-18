-- ------------------------------------------------------------
-- Allows a gaming/internet package or Starlink plan to be deleted
-- even after past sessions/subscriptions have used it.
--
-- Previously, sessions.service_id and starlink_subscriptions.plan_id
-- were required (NOT NULL) with a plain foreign key, so MySQL
-- refused to delete a package/plan that any session or subscription
-- - even a finished one - still pointed to.
--
-- After this migration: those columns allow NULL, and the foreign
-- keys are set to ON DELETE SET NULL. Deleting a package/plan now
-- just clears the link on old historical rows (they'll show as
-- "Deleted package"/"Deleted plan") instead of being blocked.
--
-- Run this once against your existing rchms_db database, e.g.:
--   mysql -u <user> -p rchms_db < allow_delete_used_packages_plans.sql
-- ------------------------------------------------------------

-- 1) sessions.service_id -> services.service_id
SET @fk_sessions := (
    SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'sessions'
      AND COLUMN_NAME = 'service_id'
      AND REFERENCED_TABLE_NAME = 'services'
    LIMIT 1
);
SET @drop_sql := CONCAT('ALTER TABLE sessions DROP FOREIGN KEY ', @fk_sessions);
PREPARE stmt FROM @drop_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

ALTER TABLE sessions MODIFY COLUMN service_id INT NULL;

ALTER TABLE sessions
    ADD CONSTRAINT fk_sessions_service
    FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE SET NULL;

-- 2) starlink_subscriptions.plan_id -> starlink_plans.plan_id
SET @fk_subs := (
    SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'starlink_subscriptions'
      AND COLUMN_NAME = 'plan_id'
      AND REFERENCED_TABLE_NAME = 'starlink_plans'
    LIMIT 1
);
SET @drop_sql2 := CONCAT('ALTER TABLE starlink_subscriptions DROP FOREIGN KEY ', @fk_subs);
PREPARE stmt2 FROM @drop_sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

ALTER TABLE starlink_subscriptions MODIFY COLUMN plan_id INT NULL;

ALTER TABLE starlink_subscriptions
    ADD CONSTRAINT fk_subscriptions_plan
    FOREIGN KEY (plan_id) REFERENCES starlink_plans(plan_id) ON DELETE SET NULL;
