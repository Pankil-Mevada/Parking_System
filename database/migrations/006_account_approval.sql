ALTER TABLE users ADD COLUMN registration_kind text CHECK(registration_kind IN ('driver','employee'));
ALTER TABLE users ADD COLUMN approval_status text NOT NULL DEFAULT 'pending' CHECK(approval_status IN ('pending','approved','rejected'));
-- Preserve established assigned employees/admins. Other existing accounts need
-- approval too; accounts without a vehicle select their registration type.
UPDATE users SET approval_status=CASE WHEN EXISTS(SELECT 1 FROM staff_assignments a WHERE a.user_id=users.id) THEN 'approved' ELSE 'pending' END,
registration_kind=CASE WHEN EXISTS(SELECT 1 FROM staff_accounts s WHERE s.user_id=users.id) THEN 'employee' WHEN EXISTS(SELECT 1 FROM vehicles v WHERE v.user_id=users.id) THEN 'driver' ELSE NULL END;
