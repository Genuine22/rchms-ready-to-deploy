-- ============================================================
-- RuralConnect Hub Management System (RCHMS)
-- Database Schema
-- ============================================================
-- Run this once on your MySQL server (on the Admin PC) to create
-- the database and all tables.
--
-- How to run:
--   mysql -u root -p < schema.sql
-- or paste into MySQL Workbench / phpMyAdmin SQL tab.
-- ============================================================

CREATE DATABASE IF NOT EXISTS rchms_db;
USE rchms_db;

-- ------------------------------------------------------------
-- 1. USERS (administrators / staff who log in to the system)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'attendant') NOT NULL DEFAULT 'attendant',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login DATETIME NULL
);

-- ------------------------------------------------------------
-- 2. CUSTOMERS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    membership_code VARCHAR(20) NOT NULL UNIQUE,   -- e.g. RC-0001
    full_name VARCHAR(100) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    date_registered DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- ------------------------------------------------------------
-- 3. COMPUTERS (every PC in the hub, admin + client machines)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS computers (
    computer_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,              -- e.g. "PC 1"
    computer_type ENUM('browsing', 'gaming') NOT NULL DEFAULT 'browsing',
    ip_address VARCHAR(45) NULL,                   -- local network IP of that client PC
    status ENUM('available', 'in_use', 'offline', 'reserved') NOT NULL DEFAULT 'available',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 4. SERVICES (the time/price packages offered)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS services (
    service_id INT AUTO_INCREMENT PRIMARY KEY,
    service_name VARCHAR(50) NOT NULL,             -- e.g. "Browsing - 1 Hour"
    service_category ENUM('internet', 'gaming', 'printing', 'other') NOT NULL,
    duration_minutes INT NULL,                     -- NULL for non-timed services like printing
    price DECIMAL(10,2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- ------------------------------------------------------------
-- 5. SESSIONS (every timed session: browsing or gaming)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    computer_id INT NOT NULL,
    service_id INT NULL,                           -- NULL if the package was later deleted
    started_at DATETIME NOT NULL,
    ends_at DATETIME NOT NULL,
    actual_end_at DATETIME NULL,                   -- when it really ended (could be early)
    status ENUM('active', 'completed', 'cancelled', 'expired') NOT NULL DEFAULT 'active',
    created_by INT NOT NULL,                       -- user_id of the admin/attendant who started it
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (computer_id) REFERENCES computers(computer_id),
    FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(user_id)
);

-- ------------------------------------------------------------
-- 6. PAYMENTS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NULL,                           -- can be NULL for non-session payments e.g. printing
    customer_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    payment_method ENUM('cash', 'mobile_money', 'membership') NOT NULL,
    receipt_number VARCHAR(30) NULL,
    paid_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recorded_by INT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (recorded_by) REFERENCES users(user_id)
);

-- ------------------------------------------------------------
-- 7. PRINT JOBS (for the printing/photocopy/scanning stats)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS print_jobs (
    print_job_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NULL,
    job_type ENUM('printing', 'photocopying', 'scanning', 'lamination', 'cv_writing', 'document_typing') NOT NULL,
    pages INT NOT NULL DEFAULT 1,
    amount DECIMAL(10,2) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recorded_by INT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (recorded_by) REFERENCES users(user_id)
);

-- ------------------------------------------------------------
-- Seed data: a default admin user and starter service packages
-- (Password for 'admin' is set later via the app's setup script —
--  we never store plain text passwords, so this is just the row;
--  password_hash gets filled in by Step 2.)
-- ------------------------------------------------------------
INSERT INTO services (service_name, service_category, duration_minutes, price) VALUES
('Browsing - 30 Minutes', 'internet', 30, 5.00),
('Browsing - 1 Hour', 'internet', 60, 8.00),
('Browsing - 2 Hours', 'internet', 120, 15.00),
('Browsing - 5 Hours', 'internet', 300, 30.00),
('Gaming - 30 Minutes', 'gaming', 30, 6.00),
('Gaming - 1 Hour', 'gaming', 60, 10.00),
('Gaming - 2 Hours', 'gaming', 120, 18.00)
ON DUPLICATE KEY UPDATE service_name = service_name;

INSERT INTO computers (name, computer_type, status) VALUES
('PC 1', 'browsing', 'available'),
('PC 2', 'browsing', 'available'),
('PC 3', 'browsing', 'available'),
('PC 4', 'gaming', 'available'),
('PC 5', 'gaming', 'available')
ON DUPLICATE KEY UPDATE name = name;
