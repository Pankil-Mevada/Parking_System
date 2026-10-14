-- Keycloak owns passwords, verification, recovery and MFA. No local passwords.
ALTER TABLE users ADD COLUMN display_name text NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN email text NOT NULL DEFAULT '';
CREATE TABLE revoked_auth_sessions (
  provider_session_id text PRIMARY KEY,
  expires_at timestamptz NOT NULL
);
CREATE FUNCTION normalize_registration(value text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT upper(regexp_replace(btrim(value), '[[:space:]-]+', '', 'g'))
$$;
ALTER TABLE vehicles ADD CONSTRAINT canonical_registration
  CHECK (normalized_registration = normalize_registration(normalized_registration));
ALTER TABLE vehicles ADD CONSTRAINT canonical_jurisdiction
  CHECK (registration_jurisdiction = upper(btrim(registration_jurisdiction)));
