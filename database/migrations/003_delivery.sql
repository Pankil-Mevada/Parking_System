-- Publication is serialized separately from parking commits: outbox sequence IDs
-- alone cannot be used as commit-order replay cursors.
CREATE TABLE delivery_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  outbox_id bigint NOT NULL UNIQUE REFERENCES outbox_events(id),
  location_id uuid NOT NULL REFERENCES locations(id),
  aggregate_id uuid NOT NULL REFERENCES spaces(id),
  aggregate_version bigint NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX delivery_location_cursor ON delivery_events(location_id,id);
CREATE INDEX audit_location_search ON audit_events(target_id,occurred_at DESC);
