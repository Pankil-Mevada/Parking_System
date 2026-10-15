CREATE TABLE client_health (
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  provider_session_id text NOT NULL,
  location_id uuid NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
  last_seen timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(user_id,provider_session_id,location_id)
);
CREATE INDEX client_health_seen ON client_health(last_seen);
