-- ============================================================
-- RCHMS - Starlink Installation Module (Phase 2)
-- Adds 4 new tables for the field-operations side of Starlink:
-- site surveys, installation jobs, equipment assignments, and
-- installation reports. Completely separate from the Starlink
-- Membership tables (starlink_subscribers/plans/subscriptions/
-- payments) added earlier, but installations are linked to the
-- SAME subscriber record - a school, clinic, business or home is
-- one subscriber whether you're looking at their voucher/billing
-- side or their physical installation side.
--
-- How to run:
--   Open this in MySQL Workbench (File > Open SQL Script), then
--   run it with the lightning bolt icon, OR copy-paste into a SQL
--   tab and run. Requires add_starlink_tables.sql to already have
--   been run (this references starlink_subscribers and users).
-- ============================================================

USE rchms_db;

-- ------------------------------------------------------------
-- 1. SITE SURVEYS
-- One survey per subscriber, done before an installation is
-- approved. survey_id is the primary key (named to match this
-- project's existing convention of descriptive, table-specific
-- PK names rather than a generic "id").
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS site_surveys (
    survey_id INT AUTO_INCREMENT PRIMARY KEY,
    subscriber_id INT NOT NULL,
    surveyor_id INT NULL,                    -- staff member (users.user_id) who did the survey
    survey_date DATE NOT NULL,
    gps_location VARCHAR(100) NULL,          -- e.g. "5.6037,-0.1870" (lat,lng)
    roof_type VARCHAR(50) NULL,              -- free text: aluminium sheet, concrete slab, thatch, etc.
    mount_type VARCHAR(50) NULL,             -- e.g. roof mount, pole mount, wall mount, ground mount
    obstruction_level ENUM('none', 'low', 'medium', 'high') NOT NULL DEFAULT 'none',
    estimated_cable_length DECIMAL(6,2) NULL,   -- meters
    estimated_cost DECIMAL(10,2) NULL,
    remarks TEXT NULL,
    status ENUM('pending', 'completed', 'cancelled') NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subscriber_id) REFERENCES starlink_subscribers(subscriber_id),
    -- Losing track of *who* surveyed shouldn't block deleting a staff
    -- account later, so this is SET NULL rather than a hard block -
    -- same reasoning already used for service/plan FKs elsewhere in
    -- this project.
    FOREIGN KEY (surveyor_id) REFERENCES users(user_id) ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- 2. INSTALLATION JOBS
-- One row per install attempt for a subscriber. survey_id is
-- nullable + ON DELETE SET NULL so an old survey can be cleaned
-- up later without losing the installation's own history.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS installation_jobs (
    installation_id INT AUTO_INCREMENT PRIMARY KEY,
    subscriber_id INT NOT NULL,
    survey_id INT NULL,
    technician_id INT NULL,                  -- staff member (users.user_id) assigned to install
    installation_date DATE NULL,             -- planned/actual install date
    status ENUM('pending', 'approved', 'scheduled', 'in_progress', 'completed', 'activated', 'cancelled')
        NOT NULL DEFAULT 'pending',
    priority ENUM('low', 'normal', 'high', 'urgent') NOT NULL DEFAULT 'normal',
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subscriber_id) REFERENCES starlink_subscribers(subscriber_id),
    FOREIGN KEY (survey_id) REFERENCES site_surveys(survey_id) ON DELETE SET NULL,
    FOREIGN KEY (technician_id) REFERENCES users(user_id) ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- 3. EQUIPMENT ASSIGNMENTS
-- Dish/router serials and mounting details assigned to one
-- installation job. Only makes sense attached to a job, so this
-- one DOES cascade when the parent job is deleted.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS equipment_assignments (
    equipment_assignment_id INT AUTO_INCREMENT PRIMARY KEY,
    installation_id INT NOT NULL,
    dish_serial VARCHAR(50) NULL,
    router_serial VARCHAR(50) NULL,
    cable_length DECIMAL(6,2) NULL,          -- meters actually used
    mount_type VARCHAR(50) NULL,
    assigned_by INT NULL,                    -- staff member (users.user_id) who assigned the kit
    assigned_date DATE NOT NULL DEFAULT (CURRENT_DATE),
    FOREIGN KEY (installation_id) REFERENCES installation_jobs(installation_id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_by) REFERENCES users(user_id) ON DELETE SET NULL
);

-- ------------------------------------------------------------
-- 4. INSTALLATION REPORTS
-- Completion/handover report for one installation job. Also
-- cascades with its parent job for the same reason as above.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS installation_reports (
    report_id INT AUTO_INCREMENT PRIMARY KEY,
    installation_id INT NOT NULL,
    download_speed DECIMAL(6,2) NULL,        -- Mbps
    upload_speed DECIMAL(6,2) NULL,           -- Mbps
    latency INT NULL,                        -- ms
    installer_notes TEXT NULL,
    completion_date DATE NULL,
    customer_name VARCHAR(100) NULL,         -- on-site contact who signed off (e.g. headteacher, shop owner)
    FOREIGN KEY (installation_id) REFERENCES installation_jobs(installation_id) ON DELETE CASCADE
);
