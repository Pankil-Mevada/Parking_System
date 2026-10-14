\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE
  u uuid := gen_random_uuid(); u2 uuid := gen_random_uuid();
  v uuid := gen_random_uuid(); v2 uuid := gen_random_uuid();
  l uuid := gen_random_uuid(); s uuid := gen_random_uuid(); s2 uuid := gen_random_uuid();
  session_id uuid := gen_random_uuid();
BEGIN
  INSERT INTO users(id,identity_provider_reference) VALUES (u,u::text),(u2,u2::text);
  INSERT INTO vehicles(id,user_id,registration_jurisdiction,normalized_registration,vehicle_type)
    VALUES(v,u,'TEST','ONE','car'),(v2,u2,'TEST','TWO','car');
  BEGIN
    INSERT INTO vehicles(user_id,registration_jurisdiction,normalized_registration,vehicle_type) VALUES(u,'TEST','THREE','car');
    RAISE EXCEPTION 'Expected one enabled vehicle violation';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  BEGIN
    UPDATE vehicles SET normalized_registration='ONE' WHERE id=v2;
    RAISE EXCEPTION 'Expected unique registration violation';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  INSERT INTO locations(id,name) VALUES(l,'Constraint test');
  INSERT INTO spaces(id,location_id,label,supported_vehicle_type) VALUES(s,l,'1','car'),(s2,l,'2','car');
  INSERT INTO parking_sessions(id,user_id,vehicle_id,space_id,checked_in_by,registration_jurisdiction_snapshot,registration_snapshot)
    VALUES(session_id,u,v,s,u,'TEST','ONE');
  BEGIN
    INSERT INTO parking_sessions(user_id,vehicle_id,space_id,checked_in_by,registration_jurisdiction_snapshot,registration_snapshot)
      VALUES(u2,v2,s,u,'TEST','TWO');
    RAISE EXCEPTION 'Expected active space violation';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  BEGIN
    INSERT INTO parking_sessions(user_id,vehicle_id,space_id,checked_in_by,registration_jurisdiction_snapshot,registration_snapshot)
      VALUES(u,v,s2,u,'TEST','ONE');
    RAISE EXCEPTION 'Expected active user/vehicle violation';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  BEGIN
    UPDATE parking_sessions SET registration_snapshot='CHANGED' WHERE id=session_id;
    RAISE EXCEPTION 'Expected immutable snapshot violation';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'Parking identity and arrival snapshot are immutable' THEN RAISE; END IF;
  END;
  UPDATE parking_sessions SET checked_out_at=now(),checked_out_by=u WHERE id=session_id;
  INSERT INTO parking_sessions(user_id,vehicle_id,space_id,checked_in_by,registration_jurisdiction_snapshot,registration_snapshot)
    VALUES(u2,v2,s,u,'TEST','TWO');
  IF (SELECT count(*) FROM parking_sessions WHERE id=session_id AND checked_out_at IS NOT NULL) <> 1 THEN
    RAISE EXCEPTION 'History missing';
  END IF;
  IF (SELECT count(*) FROM pg_indexes WHERE indexname IN ('one_enabled_vehicle_per_user','one_active_session_per_user','one_active_session_per_vehicle','one_active_session_per_space') AND indexdef LIKE '%UNIQUE%WHERE%') <> 4 THEN
    RAISE EXCEPTION 'Required partial unique indexes missing';
  END IF;
END $$;
ROLLBACK;
\echo 'Constraint tests passed; fixtures rolled back.'
