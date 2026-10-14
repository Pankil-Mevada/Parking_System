CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identity_provider_reference text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'enabled' CHECK (status IN ('enabled','disabled')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE vehicles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  registration_jurisdiction text NOT NULL CHECK (length(btrim(registration_jurisdiction)) BETWEEN 1 AND 64),
  normalized_registration text NOT NULL CHECK (length(btrim(normalized_registration)) BETWEEN 1 AND 64),
  vehicle_type text NOT NULL CHECK (vehicle_type IN ('car','motorcycle','van')),
  make text, model text, color text,
  disabled_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id,user_id)
);
CREATE UNIQUE INDEX one_enabled_vehicle_per_user ON vehicles(user_id) WHERE disabled_at IS NULL;
CREATE UNIQUE INDEX unique_enabled_registration ON vehicles(registration_jurisdiction,normalized_registration) WHERE disabled_at IS NULL;
CREATE TABLE locations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
  timezone text NOT NULL DEFAULT 'UTC',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE zones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id uuid NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  label text NOT NULL,
  UNIQUE(location_id,label), UNIQUE(id,location_id)
);
CREATE TABLE spaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id uuid NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  zone_id uuid,
  label text NOT NULL CHECK (length(btrim(label)) BETWEEN 1 AND 64),
  supported_vehicle_type text NOT NULL CHECK (supported_vehicle_type IN ('car','motorcycle','van')),
  operational_status text NOT NULL DEFAULT 'enabled' CHECK (operational_status IN ('enabled','out_of_service')),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(zone_id,location_id) REFERENCES zones(id,location_id) ON DELETE RESTRICT,
  UNIQUE(location_id,label)
);
CREATE TABLE staff_assignments (
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  location_id uuid NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  role text NOT NULL CHECK (role IN ('attendant','operator_admin')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(user_id,location_id)
);
CREATE TABLE parking_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  vehicle_id uuid NOT NULL,
  space_id uuid NOT NULL REFERENCES spaces(id) ON DELETE RESTRICT,
  checked_in_at timestamptz NOT NULL DEFAULT now(),
  checked_out_at timestamptz,
  checked_in_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  checked_out_by uuid REFERENCES users(id) ON DELETE RESTRICT,
  registration_jurisdiction_snapshot text NOT NULL,
  registration_snapshot text NOT NULL,
  FOREIGN KEY(vehicle_id,user_id) REFERENCES vehicles(id,user_id) ON DELETE RESTRICT,
  CHECK (checked_out_at IS NULL OR checked_out_at >= checked_in_at),
  CHECK ((checked_out_at IS NULL) = (checked_out_by IS NULL))
);
CREATE UNIQUE INDEX one_active_session_per_user ON parking_sessions(user_id) WHERE checked_out_at IS NULL;
CREATE UNIQUE INDEX one_active_session_per_vehicle ON parking_sessions(vehicle_id) WHERE checked_out_at IS NULL;
CREATE UNIQUE INDEX one_active_session_per_space ON parking_sessions(space_id) WHERE checked_out_at IS NULL;
CREATE INDEX session_history ON parking_sessions(user_id,checked_in_at DESC);
CREATE TABLE audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  action text NOT NULL,
  target_type text NOT NULL,
  target_id uuid NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  request_id uuid NOT NULL,
  sanitized_changes jsonb NOT NULL DEFAULT '{}'
);
-- audit_events.target_id is polymorphic; outbox_events.aggregate_id references spaces.
CREATE TABLE outbox_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  location_id uuid NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  aggregate_id uuid NOT NULL REFERENCES spaces(id) ON DELETE RESTRICT,
  aggregate_version bigint NOT NULL CHECK (aggregate_version > 0),
  event_type text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  UNIQUE(aggregate_id,aggregate_version)
);
CREATE INDEX unpublished_outbox ON outbox_events(id) WHERE published_at IS NULL;
CREATE TABLE idempotency_records (
  actor_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  operation text NOT NULL,
  key text NOT NULL CHECK (length(key) BETWEEN 1 AND 200),
  request_hash text NOT NULL,
  result jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  PRIMARY KEY(actor_id,operation,key),
  CHECK (expires_at > created_at)
);
CREATE FUNCTION protect_session_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Parking history cannot be deleted';
  END IF;
  IF ROW(NEW.user_id,NEW.vehicle_id,NEW.space_id,NEW.checked_in_at,NEW.checked_in_by,NEW.registration_jurisdiction_snapshot,NEW.registration_snapshot)
     IS DISTINCT FROM ROW(OLD.user_id,OLD.vehicle_id,OLD.space_id,OLD.checked_in_at,OLD.checked_in_by,OLD.registration_jurisdiction_snapshot,OLD.registration_snapshot) THEN
    RAISE EXCEPTION 'Parking identity and arrival snapshot are immutable';
  END IF;
  IF OLD.checked_out_at IS NOT NULL AND ROW(NEW.checked_out_at,NEW.checked_out_by) IS DISTINCT FROM ROW(OLD.checked_out_at,OLD.checked_out_by) THEN
    RAISE EXCEPTION 'Checkout is immutable';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER immutable_session BEFORE UPDATE OR DELETE ON parking_sessions FOR EACH ROW EXECUTE FUNCTION protect_session_history();
