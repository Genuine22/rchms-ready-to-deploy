-- ============================================================
-- RCHMS - Starlink Membership Module
-- Adds 4 new tables, completely separate from the cyber cafe
-- tables (customers, sessions, payments, computers, services).
--
-- How to run:
--   Same as before: open this in MySQL Workbench (File > Open SQL
--   Script), then run it with the lightning bolt icon, OR copy-paste
--   into a SQL tab and run.
-- ============================================================

USE rchms_db;

-- ------------------------------------------------------------
-- 1. STARLINK SUBSCRIBERS (separate from cafe 'customers' table)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS starlink_subscribers (
    subscriber_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    location VARCHAR(150) NULL,             -- community/area name, useful for a rural deployment
    date_registered DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE KEY unique_phone (phone_number)
);

-- ------------------------------------------------------------
-- 2. STARLINK PLANS (Weekly / Monthly / Occasion, admin-configurable)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS starlink_plans (
    plan_id INT AUTO_INCREMENT PRIMARY KEY,
    plan_name VARCHAR(50) NOT NULL,          -- e.g. "Monthly - 50GB"
    plan_type ENUM('weekly', 'monthly', 'occasion') NOT NULL,
    duration_days INT NOT NULL,              -- how many days the subscription lasts
    data_allocation_gb DECIMAL(6,2) NOT NULL, -- GB allowance for this plan/cycle
    price DECIMAL(10,2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- ------------------------------------------------------------
-- 3. STARLINK SUBSCRIPTIONS (one row per signup/renewal cycle)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS starlink_subscriptions (
    subscription_id INT AUTO_INCREMENT PRIMARY KEY,
    subscriber_id INT NOT NULL,
    plan_id INT NULL,                          -- NULL if the plan was later deleted
    voucher_code VARCHAR(20) NOT NULL UNIQUE,  -- e.g. SL-X7K2P9, used to log in/check status
    starts_at DATE NOT NULL,
    ends_at DATE NOT NULL,
    data_allocation_gb DECIMAL(6,2) NOT NULL,  -- copied from plan at signup time (in case plan changes later)
    status ENUM('pending_payment', 'active', 'expired', 'cancelled') NOT NULL DEFAULT 'pending_payment',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INT NOT NULL,
    FOREIGN KEY (subscriber_id) REFERENCES starlink_subscribers(subscriber_id),
    FOREIGN KEY (plan_id) REFERENCES starlink_plans(plan_id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(user_id)
);

-- ------------------------------------------------------------
-- 4. STARLINK PAYMENTS (separate from cafe 'payments' table)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS starlink_payments (
    starlink_payment_id INT AUTO_INCREMENT PRIMARY KEY,
    subscription_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    payment_method ENUM('cash', 'mobile_money') NOT NULL,
    receipt_number VARCHAR(30) NULL,
    paid_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recorded_by INT NOT NULL,
    FOREIGN KEY (subscription_id) REFERENCES starlink_subscriptions(subscription_id),
    FOREIGN KEY (recorded_by) REFERENCES users(user_id)
);

-- ------------------------------------------------------------
-- Seed data: starter Starlink plans (weekly, monthly, occasion)
-- ------------------------------------------------------------
INSERT INTO starlink_plans (plan_name, plan_type, duration_days, data_allocation_gb, price) VALUES
('Weekly - 15GB', 'weekly', 7, 15.00, 25.00),
('Monthly - 50GB', 'monthly', 30, 50.00, 80.00),
('Monthly - 100GB', 'monthly', 30, 100.00, 140.00),
('Occasion - 5GB (1 Day)', 'occasion', 1, 5.00, 10.00),
('Occasion - 10GB (3 Days)', 'occasion', 3, 10.00, 20.00)
ON DUPLICATE KEY UPDATE plan_name = plan_name;
