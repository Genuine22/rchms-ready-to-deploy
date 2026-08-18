-- ------------------------------------------------------------
-- Business Centre expansion
-- Adds 'cv_writing' and 'document_typing' to the print_jobs
-- job_type ENUM, alongside the existing printing, photocopying,
-- scanning, and lamination types.
--
-- Run this once against your existing database:
--   mysql -u <user> -p <database_name> < add_business_centre_types.sql
-- ------------------------------------------------------------

ALTER TABLE print_jobs
    MODIFY COLUMN job_type ENUM(
        'printing',
        'photocopying',
        'scanning',
        'lamination',
        'cv_writing',
        'document_typing'
    ) NOT NULL;
