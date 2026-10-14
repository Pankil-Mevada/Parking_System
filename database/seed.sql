\set ON_ERROR_STOP on
BEGIN;
-- Synthetic location only: no accounts, credentials, vehicles or personal data.
INSERT INTO locations(id,name,timezone) VALUES ('10000000-0000-0000-0000-000000000001','Demo parking location','Asia/Kolkata') ON CONFLICT(id) DO NOTHING;
INSERT INTO zones(id,location_id,label) VALUES ('20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','Ground') ON CONFLICT(id) DO NOTHING;
INSERT INTO spaces(location_id,zone_id,label,supported_vehicle_type,operational_status)
SELECT '10000000-0000-0000-0000-000000000001'::uuid,'20000000-0000-0000-0000-000000000001'::uuid,
       'G-' || n, 'car', CASE WHEN n=6 THEN 'out_of_service' ELSE 'enabled' END
FROM generate_series(1,6) AS n ON CONFLICT(location_id,label) DO NOTHING;
COMMIT;
