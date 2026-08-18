-- ============================================================
-- RCHMS - Fault Management / ISP Helpdesk Module
-- Replaces the old placeholder "Maintenance" section with a real
-- ticketing system for fault reports against Starlink installations.
--
-- Design notes:
--   - Reuses starlink_subscribers, installation_jobs and users
--     rather than creating parallel customer/technician tables.
--     No new role is added yet (technician assignment just points
--     at an existing users row, same pattern as
--     installation_jobs.technician_id already uses).
--   - fault_ticket_activity mirrors the existing installation_activity
--     table exactly (append-only audit trail powering a timeline).
--   - fault_ticket_equipment reuses inventory_items, the same way
--     job_equipment_lines does for installations, so parts used
--     during a repair also flow through automatic deduction.
--
-- How to run:
--   Open in MySQL Workbench (File > Open SQL Script) and run with
--   the lightning bolt icon, OR copy-paste into a SQL tab and run.
--   Requires add_starlink_tables.sql, add_installation_tables.sql
--   and add_inventory_tables.sql to already have been run.
-- ============================================================

USE rchms_db;

-- ------------------------------------------------------------
-- 1. FAULT TICKETS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fault_tickets (
    ticket_id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_number VARCHAR(20) NOT NULL,
    subscriber_id INT NOT NULL,
    installation_id INT NULL,                  -- the installation this fault relates to, if known
    assigned_technician_id INT NULL,
    category ENUM(
        'no_internet', 'slow_internet', 'router_offline', 'starlink_offline',
        'dish_misalignment', 'cable_damage', 'power_failure', 'high_latency',
        'packet_loss', 'wifi_coverage', 'hardware_failure', 'billing_issue',
        'configuration_issue', 'installation_problem', 'other'
    ) NOT NULL DEFAULT 'other',
    priority ENUM('low', 'medium', 'high', 'critical') NOT NULL DEFAULT 'medium',
    status ENUM(
        'open', 'assigned', 'in_progress', 'waiting_customer',
        'waiting_parts', 'resolved', 'closed', 'cancelled'
    ) NOT NULL DEFAULT 'open',
    subject VARCHAR(200) NULL,
    description TEXT NULL,
    gps_location VARCHAR(100) NULL,
    expected_resolution DATETIME NULL,
    actual_resolution DATETIME NULL,
    resolution_notes TEXT NULL,
    equipment_used_notes TEXT NULL,
    signature_path VARCHAR(255) NULL,          -- digital sign-off image, if captured
    created_by INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_ticket_number (ticket_number),
    FOREIGN KEY (subscriber_id) REFERENCES starlink_subscribers(subscriber_id),
    FOREIGN KEY (installation_id) REFERENCES installation_jobs(installation_id) ON DELETE SET NULL,
    FOREIGN KEY (assigned_technician_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- 2. FAULT TICKET ACTIVITY (audit trail / timeline)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fault_ticket_activity (
    activity_id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT NOT NULL,
    user_id INT NULL,
    event_type VARCHAR(50) NOT NULL,
    description VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES fault_tickets(ticket_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- 3. FAULT TICKET ATTACHMENTS (photos, before/after, signature)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fault_ticket_attachments (
    attachment_id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    attachment_type ENUM('photo_before', 'photo_after', 'photo_general', 'signature', 'other')
        NOT NULL DEFAULT 'photo_general',
    caption VARCHAR(255) NULL,
    uploaded_by INT NULL,
    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES fault_tickets(ticket_id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users(user_id) ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- 4. FAULT TICKET EQUIPMENT (replacement parts used on a repair)
-- Same deduct/restore pattern as job_equipment_lines.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fault_ticket_equipment (
    ticket_equipment_id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT NOT NULL,
    item_id INT NOT NULL,
    quantity_used DECIMAL(10,2) NOT NULL,
    deducted BOOLEAN NOT NULL DEFAULT FALSE,
    restored BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_by INT NULL,
    assigned_date DATE NOT NULL DEFAULT (CURRENT_DATE),
    FOREIGN KEY (ticket_id) REFERENCES fault_tickets(ticket_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES inventory_items(item_id),
    FOREIGN KEY (assigned_by) REFERENCES users(user_id) ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- 5. Wire up inventory_transactions.ticket_id now that
-- fault_tickets exists (add_inventory_tables.sql runs before this
-- file and couldn't reference a table that didn't exist yet).
-- ------------------------------------------------------------
ALTER TABLE inventory_transactions
    ADD CONSTRAINT fk_inventory_transactions_ticket
    FOREIGN KEY (ticket_id) REFERENCES fault_tickets(ticket_id) ON DELETE SET NULL;

