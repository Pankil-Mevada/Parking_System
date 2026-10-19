ALTER TABLE locations ADD COLUMN area text NOT NULL DEFAULT '' CHECK(length(area)<=200);
ALTER TABLE locations ADD COLUMN city text NOT NULL DEFAULT '' CHECK(length(city)<=200);
ALTER TABLE locations ADD COLUMN country text NOT NULL DEFAULT '' CHECK(length(country)<=100);
