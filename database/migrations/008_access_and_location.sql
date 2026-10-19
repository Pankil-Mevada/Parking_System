-- Additive account routing and building address; preserve accounts and history.
ALTER TABLE locations ADD COLUMN address text NOT NULL DEFAULT '' CHECK(length(address)<=500);
ALTER TABLE locations ADD COLUMN latitude double precision CHECK(latitude BETWEEN -90 AND 90);
ALTER TABLE locations ADD COLUMN longitude double precision CHECK(longitude BETWEEN -180 AND 180);
ALTER TABLE locations ADD CONSTRAINT location_coordinates_pair CHECK((latitude IS NULL)=(longitude IS NULL));
ALTER TABLE users ADD COLUMN registration_location_id uuid REFERENCES locations(id) ON DELETE RESTRICT;
CREATE INDEX registration_queue ON users(registration_location_id,approval_status,created_at,id);
