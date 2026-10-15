-- Public accounts remain drivers. Staff onboarding is a separate administrator action.
CREATE TABLE staff_accounts (
  email text PRIMARY KEY CHECK (email=lower(btrim(email))),
  user_id uuid UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
  location_id uuid NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Preserve existing assigned staff/admin accounts and their audit/history.
INSERT INTO staff_accounts(email,user_id,location_id,created_by)
SELECT lower(btrim(u.email)),u.id,min(a.location_id::text)::uuid,u.id
FROM users u JOIN staff_assignments a ON a.user_id=u.id
WHERE u.email<>'' GROUP BY u.id,u.email;
ALTER TABLE staff_assignments ADD CONSTRAINT assignment_requires_staff_account
FOREIGN KEY(user_id) REFERENCES staff_accounts(user_id) ON DELETE RESTRICT;
