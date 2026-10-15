\set ON_ERROR_STOP on
BEGIN;
SELECT pg_advisory_xact_lock(726193001);
CREATE TABLE IF NOT EXISTS schema_migrations (
  version text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);
SELECT NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version='001') AS apply_001 \gset
\if :apply_001
\ir migrations/001_initial.sql
INSERT INTO schema_migrations(version) VALUES ('001');
\endif
SELECT NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version='002') AS apply_002 \gset
\if :apply_002
\ir migrations/002_identity.sql
INSERT INTO schema_migrations(version) VALUES ('002');
\endif
SELECT NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version='003') AS apply_003 \gset
\if :apply_003
\ir migrations/003_delivery.sql
INSERT INTO schema_migrations(version) VALUES ('003');
\endif
SELECT NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version='004') AS apply_004 \gset
\if :apply_004
\ir migrations/004_client_health.sql
INSERT INTO schema_migrations(version) VALUES ('004');
\endif
SELECT NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version='005') AS apply_005 \gset
\if :apply_005
\ir migrations/005_staff_accounts.sql
INSERT INTO schema_migrations(version) VALUES ('005');
\endif
SELECT NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version='006') AS apply_006 \gset
\if :apply_006
\ir migrations/006_account_approval.sql
INSERT INTO schema_migrations(version) VALUES ('006');
\endif
COMMIT;
