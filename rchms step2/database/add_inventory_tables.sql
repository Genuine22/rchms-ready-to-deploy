-- ============================================================
-- RCHMS - Inventory Management Module
-- Replaces the old "Available Kits" display with a real warehouse
-- inventory: stocked items, categories, movement history, and the
-- per-job equipment lines pulled from that stock.
--
-- Design notes:
--   - inventory_items.quantity_in_stock is the ONLY source of truth
--     for how many units physically exist. It must never be edited
--     directly from a form - it only ever changes via a row written
--     to inventory_transactions (stock in, issued, damaged, lost,
--     restored, adjustment). This keeps a full audit trail and gives
--     the "Inventory Movement History" report for free.
--   - job_equipment_lines is a NEW table, separate from the existing
--     equipment_assignments table. equipment_assignments already
--     covers the single dish/router serial + mount type recorded for
--     a job; job_equipment_lines is the multi-line "pick items from
--     inventory with a quantity" list (kit, router, 2x AP, 30m cable,
--     etc.) that this module needs, and is what automatic deduction
--     on job completion actually reads from. Nothing existing is
--     replaced or duplicated - this is additive.
--   - The same item/quantity pattern is reused for fault-ticket
--     equipment usage in add_fault_ticket_tables.sql (run this file
--     first).
--
-- How to run:
--   Open in MySQL Workbench (File > Open SQL Script) and run with
--   the lightning bolt icon, OR copy-paste into a SQL tab and run.
--   Requires schema.sql and add_installation_tables.sql to already
--   have been run (this references installation_jobs and users).
-- ============================================================

USE rchms_db;

-- ------------------------------------------------------------
-- 1. INVENTORY CATEGORIES
-- Admin-manageable list. Seeded below with the standard ISP/
-- Starlink-installer categories; more can be added from the UI.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory_categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_category_name (name)
);

INSERT IGNORE INTO inventory_categories (name) VALUES
    ('Starlink Standard Kit'), ('Starlink Mini'), ('Starlink Business Kit'),
    ('Router'), ('Access Point'), ('MikroTik Router'), ('MikroTik Switch'),
    ('PoE Injector'), ('Ethernet Adapter'), ('Outdoor Ethernet Cable'),
    ('Indoor Ethernet Cable'), ('Pole Mount'), ('Roof Mount'), ('Wall Mount'),
    ('J-Mount'), ('Pipe Adapter'), ('Cable Clips'), ('RJ45 Connector'),
    ('Grounding Kit'), ('Surge Protector'), ('UPS'), ('Power Extension'),
    ('Network Cabinet'), ('Conduit Pipe'), ('Junction Box'), ('WiFi Extender'),
    ('Fiber Media Converter'), ('Patch Panel');

-- ------------------------------------------------------------
-- 2. INVENTORY ITEMS
-- One row per stocked item/SKU (e.g. "TP-Link AP", "30m outdoor
-- cable spool"). quantity_in_stock is a running total kept in sync
-- by inventory_transactions - never edited directly by a form.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory_items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    item_name VARCHAR(150) NOT NULL,
    brand VARCHAR(100) NULL,
    model VARCHAR(100) NULL,
    serial_number VARCHAR(100) NULL,
    asset_tag VARCHAR(100) NULL,
    qr_code VARCHAR(150) NULL,
    unit VARCHAR(20) NOT NULL DEFAULT 'pcs',   -- e.g. pcs, meters, box
    quantity_in_stock DECIMAL(10,2) NOT NULL DEFAULT 0,
    minimum_stock_level DECIMAL(10,2) NOT NULL DEFAULT 0,
    unit_cost DECIMAL(10,2) NULL,
    supplier VARCHAR(150) NULL,
    purchase_date DATE NULL,
    warranty_expiry DATE NULL,
    warehouse_location VARCHAR(150) NULL,
    status ENUM('available', 'assigned', 'installed', 'damaged', 'returned', 'lost')
        NOT NULL DEFAULT 'available',
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES inventory_categories(category_id),
    UNIQUE KEY unique_serial_number (serial_number),
    UNIQUE KEY unique_asset_tag (asset_tag)
);

-- ------------------------------------------------------------
-- 3. INVENTORY TRANSACTIONS
-- The append-only movement log. Every change to quantity_in_stock
-- is driven by inserting a row here first - this IS the audit
-- trail and the source for every inventory report (stock,
-- valuation, issued, returned, damaged, monthly usage, most/least
-- used, movement history).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory_transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    item_id INT NOT NULL,
    transaction_type ENUM(
        'stock_in',        -- new stock received from a supplier
        'deducted',        -- used on a completed installation/fault job
        'restored',        -- installation/fault job cancelled or reversed
        'damaged',         -- marked damaged, removed from usable stock
        'lost',            -- marked lost, removed from usable stock
        'returned',        -- returned to warehouse in usable condition
        'adjustment'       -- manual admin correction (with a note explaining why)
    ) NOT NULL,
    quantity DECIMAL(10,2) NOT NULL,           -- always a positive amount; transaction_type gives direction
    installation_id INT NULL,                  -- set when tied to an installation job
    ticket_id INT NULL,                        -- set when tied to a fault ticket
    performed_by INT NULL,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES inventory_items(item_id),
    FOREIGN KEY (installation_id) REFERENCES installation_jobs(installation_id) ON DELETE SET NULL,
    FOREIGN KEY (performed_by) REFERENCES users(user_id) ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- 4. JOB EQUIPMENT LINES
-- The Equipment Assignment page's content: which inventory items,
-- and how much of each, are earmarked for one installation job.
-- Stock is only actually deducted (via inventory_transactions)
-- once the job is marked completed - see the "deducted" flag.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_equipment_lines (
    job_equipment_id INT AUTO_INCREMENT PRIMARY KEY,
    installation_id INT NOT NULL,
    item_id INT NOT NULL,
    quantity_assigned DECIMAL(10,2) NOT NULL,
    deducted BOOLEAN NOT NULL DEFAULT FALSE,
    restored BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_by INT NULL,
    assigned_date DATE NOT NULL DEFAULT (CURRENT_DATE),
    FOREIGN KEY (installation_id) REFERENCES installation_jobs(installation_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES inventory_items(item_id),
    FOREIGN KEY (assigned_by) REFERENCES users(user_id) ON DELETE SET NULL
);
