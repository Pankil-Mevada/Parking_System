"""Real HTTP and PostgreSQL multi-connection integration/concurrency tests."""
from concurrent.futures import ThreadPoolExecutor
import json
import secrets
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
import psycopg
from identity_admin import IDENTITY, admin_token, environment, request
from identity_flow import create_user, login, recovery, verify_email, REALM
from parking_tools import ROOT, docker

API = 'http://127.0.0.1:18080'
CONTRACT = json.loads((Path(__file__).resolve().parents[1] / 'openapi.yaml').read_text())


def validate(value, schema):
    if value is None and schema.get('nullable'):
        return
    if '$ref' in schema:
        schema = CONTRACT['components']['schemas'][schema['$ref'].rsplit('/',1)[1]]
    for part in schema.get('allOf',[]):
        validate(value,part)
    kind = schema.get('type')
    if kind == 'object':
        assert isinstance(value,dict), 'Contract expected object'
        assert set(schema.get('required',[])) <= set(value), 'Contract missing response keys'
        if schema.get('additionalProperties') is False:
            assert set(value) <= set(schema.get('properties',{})), 'Contract unexpected response keys'
        for key,item in value.items():
            if key in schema.get('properties',{}):
                validate(item,schema['properties'][key])
    elif kind == 'array':
        assert isinstance(value,list), 'Contract expected array'
        for item in value:
            validate(item,schema['items'])
    elif kind == 'string':
        assert isinstance(value,str), 'Contract expected string'
        if schema.get('format') == 'uuid':
            uuid.UUID(value)
    elif kind == 'boolean':
        assert isinstance(value,bool), 'Contract expected boolean'
    elif kind == 'integer':
        assert type(value) is int and value >= schema.get('minimum',value), 'Contract expected bounded integer'
    if 'enum' in schema:
        assert value in schema['enum'], 'Contract unexpected enum'


def api(token, path, method='GET', body=None, key=None, timeout=10, origin=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if key:
        headers['Idempotency-Key'] = key
    if origin:
        headers['Origin'] = origin
    data = None if body is None else json.dumps(body).encode()
    try:
        response = urllib.request.urlopen(urllib.request.Request(API + path, data, headers, method=method), timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        result=json.load(response)
        import re
        route=next((key for key in CONTRACT['paths'] if re.fullmatch(re.sub(r'\{[^}]+\}',r'[^/]+',key),path.split('?')[0])),None)
        assert route is not None, 'Response has no OpenAPI route'
        operation=CONTRACT['paths'][route][method.lower()]
        definition=operation['responses'][str(response.status)]
        if '$ref' in definition:
            definition=CONTRACT['components']['responses'][definition['$ref'].rsplit('/',1)[1]]
        validate(result,definition['content']['application/json']['schema'])
        if operation.get('security') != []:
            uuid.UUID(response.headers['X-Request-ID'])
            assert response.headers['Cache-Control'] == 'no-store'
        return response.status, result


def parallel(*actions):
    barrier = threading.Barrier(len(actions))
    def run(action):
        barrier.wait(timeout=10)
        return action()
    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


class Phase34(unittest.TestCase):
    @classmethod
    def connect(cls, autocommit=True):
        return psycopg.connect(host='127.0.0.1', port=15432, dbname='parking_test', user='parking_test',
                               password=environment()['POSTGRES_PASSWORD'], autocommit=autocommit)

    @classmethod
    def setUpClass(cls):
        import os
        run_id=os.environ.get('PARKING_TEST_RUN_ID')
        if not run_id:
            raise RuntimeError('Use py scripts/test_phase34.py; refusing fixtures without a retained-test-database guard.')
        with cls.connect() as connection:
            if not connection.execute('SELECT 1 FROM public.test_run_guard WHERE run_id=%s',(run_id,)).fetchone():
                raise RuntimeError('Retained test database guard mismatch; no fixtures changed.')
        cls.run_id=run_id
        cls.identities = [create_user('p34-' + secrets.token_hex(6)) for _ in range(6)]
        cls.tokens = [login(user)['access_token'] for user in cls.identities]
        cls.users = []
        for token in cls.tokens:
            code, body = api(token, '/api/me')
            if code != 200:
                raise AssertionError('Real provider authentication failed: ' + str((code, body)))
            if not body['mfa'] and os.environ.get('PARKING_TEST_PASSWORD_ONLY')!='1':
                raise AssertionError('Actual OTP authentication was not represented in the token')
            cls.users.append(body['id'])
        cls.staff, cls.other_staff, cls.driver, cls.driver2, cls.admin, cls.outsider = cls.tokens

    def setUp(self):
        self.db = self.connect()
        self.addCleanup(self.db.close)
        # Isolate each case without deleting any previous case's data.
        from psycopg import sql
        import os
        schema=('run_'+self.run_id.replace('-','')[:12]+'_'+self._testMethodName)[:63]
        self.db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        self.db.execute(sql.SQL('SET search_path TO {},public').format(sql.Identifier(schema)))
        for migration in ('001_initial.sql','002_identity.sql','003_delivery.sql','004_client_health.sql','005_staff_accounts.sql','006_account_approval.sql','008_access_and_location.sql','009_location_names.sql'):
            self.db.execute((ROOT/'database/migrations'/migration).read_text(encoding='utf-8'))
        self.db.execute("CREATE TABLE schema_migrations(version text PRIMARY KEY); INSERT INTO schema_migrations VALUES('001'),('002'),('003'),('004'),('005'),('006'),('008'),('009')")
        for index,user in enumerate(self.identities):
            self.db.execute("INSERT INTO users(id,identity_provider_reference,display_name,email,approval_status,registration_kind) VALUES(%s,%s,%s,%s,'approved','driver')",
                            (self.users[index],IDENTITY+'/realms/'+REALM+'|'+user['id'],'Synthetic Test',user['username']))
        self.db.execute(sql.SQL('ALTER ROLE parking_test SET search_path TO {},public').format(sql.Identifier(schema)))
        compose=['compose','--env-file','.env','--env-file',os.environ['PARKING_TEST_ENV_FILE'],
                 '-f','compose.yaml','-f','compose.test.yaml','--profile','phase34']
        docker(compose+['restart','test-api','test-api-peer'],capture_output=True,text=True)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            try:
                with urllib.request.urlopen(API+'/api/ready',timeout=2) as response:
                    if response.status==200:
                        break
            except (urllib.error.URLError,OSError):
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError('Retained case API did not become ready')
        self.location, self.other_location = str(uuid.uuid4()), str(uuid.uuid4())
        self.spaces = [str(uuid.uuid4()) for _ in range(3)]
        self.db.execute('INSERT INTO locations(id,name) VALUES(%s,%s),(%s,%s)', (self.location,'Test A',self.other_location,'Test B'))
        for index, space in enumerate(self.spaces):
            self.db.execute("INSERT INTO spaces(id,location_id,label,supported_vehicle_type) VALUES(%s,%s,%s,'car')", (space,self.location if index < 2 else self.other_location,str(index)))
        for index, role in [(0,'attendant'),(1,'attendant'),(4,'operator_admin')]:
            self.db.execute('INSERT INTO staff_accounts(email,user_id,location_id,created_by) SELECT lower(email),id,%s,id FROM users WHERE id=%s',(self.location,self.users[index]))
            self.db.execute('INSERT INTO staff_assignments(user_id,location_id,role) VALUES(%s,%s,%s)', (self.users[index],self.location,role))
        self.v1 = self.register(self.driver, ' A-b 123 ')
        self.v2 = self.register(self.driver2, 'SECOND')

    def register(self, token, plate):
        code, body = api(token,'/api/me/vehicle','PUT',{'registrationJurisdiction':' test ', 'registration':plate,'vehicleType':'car','color':'Blue'})
        self.assertEqual(code,200,body)
        return body['vehicle']['id']

    def checkin(self, token=None, vehicle=None, space=None, key=None, **options):
        return api(token or self.staff,'/api/staff/check-ins','POST',{'vehicleId':vehicle or self.v1,'spaceId':space or self.spaces[0]},key or str(uuid.uuid4()),**options)

    def checkout(self, session, token=None, key=None):
        return api(token or self.staff,f'/api/staff/sessions/{session}/check-out','POST',{},key or str(uuid.uuid4()))

    def scalar(self, sql, values=()):
        return self.db.execute(sql,values).fetchone()[0]

    def test_01_authentication_validation_and_csrf_boundary(self):
        self.assertEqual(api(None,'/api/me')[0],401)
        self.assertEqual(api('forged.token.signature','/api/me')[0],401)
        self.assertEqual(api(self.driver,'/api/me',origin='https://attacker.example')[0],403)
        self.assertEqual(api(None,'/api/me/vehicle','PUT',{})[0],401)
        # Provider password grants are disabled for the browser client.
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            request(IDENTITY+'/realms/'+REALM+'/protocol/openid-connect/token',{'client_id':'parking-web','grant_type':'password','username':self.identities[2]['username'],'password':self.identities[2]['password']},form=True)
        self.assertEqual(rejected.exception.code,400)
        rejected.exception.close()

    def test_02_normalization_and_simultaneous_registration(self):
        self.assertEqual(self.scalar('SELECT normalized_registration FROM vehicles WHERE id=%s',(self.v1,)),'AB123')
        results=parallel(
            lambda: api(self.driver,'/api/me/vehicle','PUT',{'registrationJurisdiction':'test','registration':'SAME','vehicleType':'car'}),
            lambda: api(self.driver2,'/api/me/vehicle','PUT',{'registrationJurisdiction':'TEST','registration':'s-a m e','vehicleType':'car'}))
        self.assertEqual(sorted(code for code,_ in results),[200,409])
        self.assertEqual(self.scalar('SELECT count(*) FROM vehicles WHERE disabled_at IS NULL'),2)

    def test_03_two_vehicles_compete_for_one_space(self):
        for _ in range(3):
            results=parallel(lambda:self.checkin(),lambda:self.checkin(self.other_staff,self.v2))
            self.assertEqual(sorted(code for code,_ in results),[201,409],results)
            self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions WHERE checked_out_at IS NULL'),1)
            session=next(body['session']['id'] for code,body in results if code==201)
            self.assertEqual(self.checkout(session)[0],200)
        self.assertEqual(self.scalar('SELECT count(*) FROM outbox_events'),6)

    def test_04_one_vehicle_competes_for_two_spaces(self):
        results=parallel(lambda:self.checkin(),lambda:self.checkin(self.other_staff,self.v1,self.spaces[1]))
        self.assertEqual(sorted(code for code,_ in results),[201,409],results)
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions WHERE user_id=%s AND checked_out_at IS NULL',(self.users[2],)),1)

    def test_05_database_user_constraint_blocks_two_distinct_vehicles(self):
        historical=str(uuid.uuid4())
        self.db.execute("INSERT INTO vehicles(id,user_id,registration_jurisdiction,normalized_registration,vehicle_type,disabled_at) VALUES(%s,%s,'TEST','HISTORICAL','car',now())",(historical,self.users[2]))
        def insert(vehicle,space):
            with self.connect(False) as connection:
                try:
                    connection.execute("INSERT INTO parking_sessions(user_id,vehicle_id,space_id,checked_in_by,registration_jurisdiction_snapshot,registration_snapshot) VALUES(%s,%s,%s,%s,'TEST','SNAPSHOT')",(self.users[2],vehicle,space,self.users[0]))
                    time.sleep(0.15)  # overlapping open transactions on separate connections
                    connection.commit()
                    return 'committed'
                except psycopg.errors.UniqueViolation as error:
                    connection.rollback()
                    return error.diag.constraint_name
        results=parallel(lambda:insert(self.v1,self.spaces[0]),lambda:insert(historical,self.spaces[1]))
        self.assertEqual(sorted(results),['committed','one_active_session_per_user'])
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions WHERE checked_out_at IS NULL'),1)
        # API also rejects a disabled historical vehicle independently of this index.
        code,body=self.checkin(vehicle=historical,space=self.spaces[1])
        self.assertEqual((code,body['error']),(409,'vehicle_not_enabled'))

    def test_06_simultaneous_idempotent_requests_and_changed_body(self):
        key=str(uuid.uuid4())
        results=parallel(lambda:self.checkin(key=key),lambda:self.checkin(key=key))
        self.assertEqual([code for code,_ in results],[201,201])
        self.assertEqual(results[0][1],results[1][1])
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions'),1)
        self.assertEqual(self.scalar('SELECT count(*) FROM outbox_events'),1)
        self.assertEqual(self.scalar('SELECT count(*) FROM audit_events'),3) # two vehicle registrations + check-in
        self.assertEqual(self.checkin(space=self.spaces[1],key=key)[0],409)
        self.assertEqual(self.checkin(vehicle=str(uuid.uuid4()),key=key)[0],409)

    def test_07_duplicate_checkout_preserves_history(self):
        _,body=self.checkin()
        session=body['session']['id']; key=str(uuid.uuid4())
        results=parallel(lambda:self.checkout(session,key=key),lambda:self.checkout(session,key=key))
        self.assertEqual([code for code,_ in results],[200,200])
        self.assertEqual(results[0][1],results[1][1])
        self.assertEqual(self.checkout(session)[0],409)
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions'),1)
        self.assertEqual(api(self.driver,'/api/me/parking-history')[1]['sessions'][0]['id'],session)
        self.assertEqual(self.scalar('SELECT count(*) FROM outbox_events'),2)

    def test_08_location_and_role_authorization(self):
        self.assertEqual(self.checkin(self.driver)[0],403)
        self.assertEqual(self.checkin(space=self.spaces[2])[0],403)
        self.assertEqual(api(self.staff,f'/api/staff/locations/{self.other_location}/spaces')[0],403)
        self.assertEqual(api(self.driver,f'/api/staff/locations/{self.location}/spaces')[0],403)
        self.assertEqual(api(self.staff,f'/api/admin/spaces/{self.spaces[0]}/status','PUT',{'status':'out_of_service','reason':'Test'})[0],403)
        self.db.execute('INSERT INTO staff_accounts(email,user_id,location_id,created_by) SELECT lower(email),id,%s,id FROM users WHERE id=%s',(self.other_location,self.users[5]))
        self.db.execute('INSERT INTO staff_assignments(user_id,location_id,role) VALUES(%s,%s,\'attendant\')',(self.users[5],self.other_location))
        _,body=self.checkin()
        self.assertEqual(self.checkout(body['session']['id'],self.outsider)[0],403)
        self.assertIsNone(api(self.driver2,'/api/me/parking-session')[1]['session'])
        self.assertEqual(api(self.driver2,'/api/me/parking-history')[1]['sessions'],[])
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions'),1)
        self.assertEqual(api(self.staff,f'/api/staff/locations/{self.location}/spaces')[0],200)

    def test_09_rollback_after_session_insert_and_retry(self):
        self.db.execute("CREATE FUNCTION test_fail_outbox() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic failure after session insert'; END $$")
        self.db.execute('CREATE TRIGGER test_outbox_failure BEFORE INSERT ON outbox_events FOR EACH ROW EXECUTE FUNCTION test_fail_outbox()')
        key=str(uuid.uuid4())
        try:
            self.assertEqual(self.checkin(key=key)[0],503)
            for table in ('parking_sessions','outbox_events','idempotency_records'):
                self.assertEqual(self.scalar('SELECT count(*) FROM '+table),0)
            self.assertEqual(self.scalar("SELECT count(*) FROM audit_events WHERE action='check-in'"),0)
            self.assertEqual(self.scalar('SELECT version FROM spaces WHERE id=%s',(self.spaces[0],)),1)
        finally:
            self.db.execute('DROP TRIGGER test_outbox_failure ON outbox_events')
            self.db.execute('DROP FUNCTION test_fail_outbox()')
        self.assertEqual(self.checkin(key=key)[0],201)

    def test_10_active_vehicle_cannot_be_replaced_or_disabled(self):
        _,body=self.checkin()
        self.assertEqual(api(self.driver,'/api/me/vehicle','PUT',{'disabled':True})[0],409)
        self.assertEqual(api(self.driver,'/api/me/vehicle','PUT',{'registrationJurisdiction':'TEST','registration':'NEW','vehicleType':'car'})[0],409)
        self.assertEqual(self.checkout(body['session']['id'])[0],200)
        new=self.register(self.driver,'NEW')
        self.assertNotEqual(new,self.v1)
        self.assertEqual(self.scalar('SELECT registration_snapshot FROM parking_sessions'),'AB123')

    def test_11_checkin_vs_maintenance(self):
        results=parallel(lambda:self.checkin(),lambda:api(self.admin,f'/api/admin/spaces/{self.spaces[0]}/status','PUT',{'status':'out_of_service','reason':'Synthetic maintenance'}))
        self.assertEqual(sorted(code for code,_ in results),[200,409] if results[1][0]==200 else [201,409],results)
        occupied=self.scalar('SELECT count(*) FROM parking_sessions WHERE checked_out_at IS NULL')
        state=self.scalar('SELECT operational_status FROM spaces WHERE id=%s',(self.spaces[0],))
        self.assertTrue((occupied==1 and state=='enabled') or (occupied==0 and state=='out_of_service'))

    def test_12_checkin_vs_replacement(self):
        results=parallel(lambda:self.checkin(),lambda:api(self.driver,'/api/me/vehicle','PUT',{'registrationJurisdiction':'TEST','registration':'REPLACED','vehicleType':'car'}))
        self.assertEqual(sorted(code for code,_ in results),[200,409] if results[1][0]==200 else [201,409],results)
        self.assertEqual(self.scalar('SELECT count(*) FROM vehicles WHERE user_id=%s AND disabled_at IS NULL',(self.users[2],)),1)

    def test_13_retry_after_client_timeout(self):
        key=str(uuid.uuid4())
        lock=self.connect(False)
        lock.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(self.users[2],))
        try:
            with self.assertRaises((TimeoutError,OSError)):
                self.checkin(key=key,timeout=0.1)
        finally:
            lock.commit(); lock.close()
        code,body=self.checkin(key=key)
        self.assertEqual(code,201,body)
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions'),1)
        self.assertEqual(self.scalar('SELECT count(*) FROM idempotency_records'),1)

    def test_14_permissions_revoked_on_next_request(self):
        self.db.execute('DELETE FROM staff_assignments WHERE user_id=%s',(self.users[0],))
        self.assertEqual(self.checkin()[0],403)
        self.db.execute("UPDATE users SET status='disabled' WHERE id=%s",(self.users[5],))
        try:
            self.assertEqual(api(self.outsider,'/api/me')[0],403)
        finally:
            self.db.execute("UPDATE users SET status='enabled' WHERE id=%s",(self.users[5],))

    def test_15_validation_and_operational_compatibility(self):
        self.assertEqual(api(self.staff,'/api/staff/check-ins','POST',{'vehicleId':self.v1,'spaceId':self.spaces[0]})[0],400)
        self.assertEqual(api(self.driver,'/api/me/vehicle','PUT',{'userId':self.users[3]})[0],400)
        self.assertEqual(api(self.admin,f'/api/admin/spaces/{self.spaces[0]}/status','PUT',{'status':'out_of_service','reason':'   '})[0],400)
        self.db.execute("UPDATE spaces SET supported_vehicle_type='van' WHERE id=%s",(self.spaces[0],))
        self.assertEqual(self.checkin()[0],409)
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions'),0)

    def test_16_invalid_otp_is_rejected(self):
        with self.assertRaisesRegex(AssertionError,'OTP rejected'):
            login(self.identities[2],invalid_otp=True)

    def test_17_logout_revokes_existing_access(self):
        fresh=login(create_user('logout-'+secrets.token_hex(6)))['access_token']
        self.assertEqual(api(fresh,'/api/auth/logout','POST',{})[0],200)
        self.assertEqual(self.feed(fresh)[0],401)
        self.assertEqual(api(fresh,'/api/me')[0],401)

    def test_18_staff_requires_actual_mfa_claim(self):
        url=IDENTITY+'/admin/realms/'+REALM
        request(url,{'browserFlow':'test-password-only'},admin_token(),method='PUT')
        try:
            token=login(self.identities[0])['access_token']
        finally:
            request(url,{'browserFlow':'parking-mfa'},admin_token(),method='PUT')
        self.assertFalse(api(token,'/api/me')[1]['mfa'])
        code,body=self.checkin(token)
        self.assertEqual((code,body['error']),(403,'staff_mfa_required'))

    def test_19_staff_assignment_administration_is_scoped(self):
        self.db.execute('INSERT INTO staff_accounts(email,user_id,location_id,created_by) SELECT lower(email),id,%s,id FROM users WHERE id=%s',(self.location,self.users[5]))
        path=f'/api/admin/locations/{self.location}/staff'
        body={'userId':self.users[5],'role':'attendant','reason':'Synthetic assignment'}
        self.assertEqual(api(self.staff,path,'POST',body)[0],403)
        self.assertEqual(api(self.admin,f'/api/admin/locations/{self.other_location}/staff','POST',body)[0],403)
        self.assertEqual(api(self.admin,path,'POST',body)[0],200)
        self.assertEqual(api(self.outsider,f'/api/staff/locations/{self.location}/spaces')[0],200)
        body['role']='none'
        self.assertEqual(api(self.admin,path,'POST',body)[0],200)
        self.assertEqual(api(self.outsider,f'/api/staff/locations/{self.location}/spaces')[0],403)

    def test_20_simultaneous_replacement_keeps_one_enabled_vehicle(self):
        results=parallel(
            lambda:api(self.driver,'/api/me/vehicle','PUT',{'registrationJurisdiction':'TEST','registration':'REPLACE1','vehicleType':'car'}),
            lambda:api(self.driver,'/api/me/vehicle','PUT',{'registrationJurisdiction':'TEST','registration':'REPLACE2','vehicleType':'car'}))
        self.assertEqual([code for code,_ in results],[200,200],results)
        self.assertEqual(self.scalar('SELECT count(*) FROM vehicles WHERE user_id=%s AND disabled_at IS NULL',(self.users[2],)),1)
        self.assertEqual(self.scalar('SELECT count(*) FROM vehicles WHERE user_id=%s',(self.users[2],)),3)

    def test_21_concurrent_checkout_with_distinct_keys(self):
        _,body=self.checkin()
        session=body['session']['id']
        results=parallel(lambda:self.checkout(session),lambda:self.checkout(session,self.other_staff))
        self.assertEqual(sorted(code for code,_ in results),[200,409],results)
        self.assertEqual(self.scalar('SELECT count(*) FROM outbox_events'),2)

    def test_22_provider_session_revocation(self):
        user=create_user('revoke-'+secrets.token_hex(6))
        token=login(user)['access_token']
        self.assertEqual(api(token,'/api/me')[0],200)
        request(IDENTITY+'/admin/realms/'+REALM+'/users/'+user['id']+'/logout',{},admin_token(),method='POST')
        self.assertEqual(api(token,'/api/me')[0],401)

    def test_23_email_verification_required(self):
        user=create_user('verify-'+secrets.token_hex(6),verified=False)
        with self.assertRaisesRegex(AssertionError,'Expected login/OTP form'):
            login(user)
        details=request(IDENTITY+'/admin/realms/'+REALM+'/users/'+user['id'],token=admin_token())
        self.assertFalse(details['emailVerified'])
        page=verify_email(user)
        details=request(IDENTITY+'/admin/realms/'+REALM+'/users/'+user['id'],token=admin_token())
        self.assertTrue(details['emailVerified'],page)

    def test_24_password_recovery_through_local_mail(self):
        user=create_user('recover-'+secrets.token_hex(6))
        changed,link=recovery(user)
        self.assertNotEqual(changed['password'],user['password'])
        self.assertEqual(api(login(changed)['access_token'],'/api/me')[0],200)
        # Reusing a consumed action token cannot present another password form.
        from identity_flow import Form
        try:
            response=urllib.request.urlopen(link,timeout=10)
        except urllib.error.HTTPError as error:
            response=error
        with response:
            page=Form(response.read().decode())
            self.assertFalse(any('password-new' in item['fields'] for item in page.forms))

    def test_25_recovery_endpoint_rate_limit(self):
        codes=[]
        for _ in range(10):
            try:
                response=urllib.request.urlopen(IDENTITY+'/realms/'+REALM+'/login-actions/reset-credentials',timeout=5)
            except urllib.error.HTTPError as error:
                response=error
            with response:
                codes.append(response.status)
        self.assertIn(429,codes)

    def test_26_public_contract_stays_aggregate_only(self):
        for path in ('/api/health','/api/ready','/api/auth/config'):
            self.assertEqual(api(None,path)[0],200)
        self.assertEqual(api(None,'/api/locations')[0],401)
        body=api(self.driver,'/api/locations')[1]
        self.assertNotIn('registration',json.dumps(body))
        self.assertNotIn('email',json.dumps(body))

    def test_27_disabled_owner_can_still_be_checked_out_by_staff(self):
        _,body=self.checkin()
        self.db.execute("UPDATE users SET status='disabled' WHERE id=%s",(self.users[2],))
        try:
            self.assertEqual(self.checkout(body['session']['id'])[0],200)
        finally:
            self.db.execute("UPDATE users SET status='enabled' WHERE id=%s",(self.users[2],))

    def test_28_expired_provider_access_token(self):
        import base64
        base=IDENTITY+'/admin/realms/'+REALM+'/clients'
        token=admin_token()
        client=request(base+'?clientId=parking-web',token=token)[0]
        attributes=dict(client.get('attributes',{}))
        changed=dict(attributes,**{'access.token.lifespan':'1'})
        request(base+'/'+client['id'],{'attributes':changed},token,method='PUT')
        try:
            access=login(create_user('expire-'+secrets.token_hex(6)))['access_token']
        finally:
            # Keycloak merges client attributes; omitting a previously added key
            # does not reliably remove it. Restore an explicit test-realm lifetime
            # so subsequent real-browser accounts do not inherit one-second tokens.
            restored=dict(attributes,**{'access.token.lifespan':attributes.get('access.token.lifespan','1800')})
            request(base+'/'+client['id'],{'attributes':restored},token,method='PUT')
        encoded=access.split('.')[1]
        claims=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        self.assertLessEqual(claims['exp']-claims['iat'],2)
        time.sleep(2)
        self.assertEqual(api(access,'/api/me')[0],401)
        self.assertEqual(self.feed(access)[0],401)


    def feed(self, token, after='0', staff=False, location=None, peer=False):
        path=f'/api/{"staff/locations" if staff else "locations"}/{location or self.location}/events?after={after}'
        headers={'Authorization':'Bearer '+token} if token else {}
        try:
            response=urllib.request.urlopen(urllib.request.Request(('http://127.0.0.1:18081' if peer else API)+path,headers=headers),timeout=10)
        except urllib.error.HTTPError as error:
            response=error
        with response:
            text=response.read().decode()
            if response.status!=200:return response.status,json.loads(text)
            self.assertIn('text/event-stream',response.headers['Content-Type'])
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            payload=json.loads(next(line[6:] for line in text.splitlines() if line.startswith('data: ')))
            validate(payload,CONTRACT['paths']['/api/locations/{id}/events']['get']['x-event-data-schema'])
            return response.status,payload

    def test_29_floor_dashboard_privacy_and_own_history(self):
        zone=str(uuid.uuid4())
        self.db.execute('INSERT INTO zones(id,location_id,label) VALUES(%s,%s,%s)',(zone,self.location,'First floor'))
        self.db.execute('UPDATE spaces SET zone_id=%s WHERE id=%s',(zone,self.spaces[0]))
        self.assertEqual(self.checkin()[0],201)
        driver=api(self.driver,f'/api/locations/{self.location}/dashboard')[1]
        self.assertEqual(driver['floors'][0]['occupied'],'1')
        self.assertNotIn('spaces',driver)
        for sensitive in ('email','registration_snapshot','display_name'):
            self.assertNotIn(sensitive,json.dumps(driver))
        staff=api(self.staff,f'/api/staff/locations/{self.location}/dashboard')[1]
        self.assertEqual(sum(bool(row['session_id']) for row in staff['spaces']),1)
        own=api(self.driver,'/api/me/dashboard')[1]
        self.assertEqual(own['current']['floor'],'First floor')
        self.assertIsNone(api(self.driver2,'/api/me/dashboard')[1]['current'])
        self.assertEqual(api(self.driver,f'/api/staff/locations/{self.location}/dashboard')[0],403)
        self.assertEqual(api(self.staff,f'/api/staff/locations/{self.other_location}/dashboard')[0],403)

    def test_30_administration_and_scoped_lookup(self):
        base=f'/api/admin/locations/{self.location}'
        self.assertEqual(api(self.staff,base+'/zones','POST',{'label':'Floor 1','reason':'test'})[0],403)
        zone=api(self.admin,base+'/zones','POST',{'label':'Floor 1','reason':'test'})[1]['id']
        space=api(self.admin,base+'/spaces','POST',{'label':'F1-01','zoneId':zone,'vehicleType':'car','reason':'test'})[1]['id']
        self.assertEqual(api(self.admin,base+'/spaces','PUT',{'id':space,'label':'F1-02','zoneId':zone,'vehicleType':'van','reason':'test'})[0],200)
        self.assertEqual(api(self.admin,base+'/zones','PUT',{'id':zone,'label':'First floor','reason':'test'})[0],200)
        self.assertEqual(api(self.admin,f'/api/admin/locations/{self.other_location}/zones','POST',{'label':'Bad','reason':'test'})[0],403)
        code,_=api(self.admin,base+'/spaces','POST',{'label':'Bad','zoneId':str(uuid.uuid4()),'vehicleType':'car','reason':'test'})
        self.assertEqual(code,400)
        found=api(self.staff,f'/api/staff/locations/{self.location}/vehicles?registration=AB123&jurisdiction=TEST')[1]
        self.assertEqual(found['vehicles'][0]['id'],self.v1)
        self.assertEqual(api(self.driver,f'/api/staff/locations/{self.location}/vehicles?registration=AB123&jurisdiction=TEST')[0],403)
        self.assertTrue(api(self.admin,base+'/audit?action=space_created')[1]['events'])
        self.assertEqual(api(self.admin,base+'/configuration','PUT',{'name':'Renamed','timezone':'INVALID','reason':'test'})[0],400)
        self.assertEqual(api(self.admin,base+'/configuration','PUT',{'name':'Renamed','timezone':'Asia/Kolkata','reason':'test'})[0],200)

    def test_31_durable_replay_and_multi_instance(self):
        snapshot=api(self.driver,f'/api/locations/{self.location}/dashboard')[1]
        start=time.monotonic();code,arrival=self.checkin();self.assertEqual(code,201)
        batch=self.feed(self.driver,snapshot['cursor'],peer=True)[1]
        self.assertTrue(batch['events'])
        latency=time.monotonic()-start
        print(f'Commit request -> peer replay {latency:.3f}s (local two-instance PostgreSQL)')
        self.assertLess(latency,2.0)
        self.assertEqual(self.feed(self.driver,snapshot['cursor'])[1]['events'],batch['events'])
        self.assertFalse(self.feed(self.driver,batch['cursor'])[1]['events'])
        self.assertEqual(self.checkout(arrival['session']['id'])[0],200)
        next_batch=self.feed(self.driver,batch['cursor'],peer=True)[1]
        self.assertTrue(next_batch['events'])
        self.assertGreater(int(next_batch['cursor']),int(batch['cursor']))
        # Invalidation payloads never include anyone's identity, even on staff streams.
        for token,staff in [(self.driver,False),(self.staff,True)]:
            data=self.feed(token,'0',staff=staff)[1]
            self.assertNotIn('AB123',json.dumps(data));self.assertNotIn('email',json.dumps(data))
            if not staff:
                for space in self.spaces:self.assertNotIn(space,json.dumps(data))
        self.assertEqual(self.scalar('SELECT count(*) FROM delivery_events'),2)
        self.assertEqual(self.scalar('SELECT count(*) FROM outbox_events WHERE published_at IS NULL'),0)

    def test_32_feed_authorization_revocation_and_cursor_reset(self):
        self.assertEqual(self.feed(None)[0],401)
        self.assertEqual(self.feed(self.driver,staff=True)[0],403)
        self.assertEqual(self.feed(self.staff,staff=True,location=self.other_location)[0],403)
        self.assertEqual(self.feed(self.staff,staff=True)[0],200)
        self.db.execute('DELETE FROM staff_assignments WHERE user_id=%s AND location_id=%s',(self.users[0],self.location))
        self.assertEqual(self.feed(self.staff,staff=True)[0],403)
        self.assertTrue(self.feed(self.driver,'999999999999999999')[1]['reset'])
        self.assertEqual(self.feed(self.driver,'invalid')[0],400)

    def test_33_late_commit_and_publication_retry(self):
        # Allocate an earlier outbox ID but commit it after a later one. A cursor
        # based directly on outbox IDs would lose the late commit permanently.
        with self.connect(False) as delayed:
            delayed.execute("INSERT INTO outbox_events(location_id,aggregate_id,aggregate_version,event_type,payload) VALUES(%s,%s,100,'test','{}')",(self.location,self.spaces[0]))
            self.db.execute("INSERT INTO outbox_events(location_id,aggregate_id,aggregate_version,event_type,payload) VALUES(%s,%s,100,'test','{}')",(self.location,self.spaces[1]))
            first=self.feed(self.staff,staff=True)[1];self.assertEqual(len(first['events']),1)
            delayed.commit()
        second=self.feed(self.staff,first['cursor'],staff=True)[1]
        self.assertEqual(len(second['events']),1)
        self.assertEqual(second['events'][0]['aggregate_id'],self.spaces[0])
        self.db.execute("CREATE FUNCTION publication_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic relay outage'; END $$")
        self.db.execute('CREATE TRIGGER publication_failure BEFORE INSERT ON delivery_events FOR EACH ROW EXECUTE FUNCTION publication_failure()')
        try:
            self.assertEqual(self.checkin()[0],201)
            self.assertEqual(self.feed(self.driver,second['cursor'])[0],503)
            self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions WHERE checked_out_at IS NULL'),1)
            self.assertEqual(self.scalar('SELECT count(*) FROM outbox_events WHERE published_at IS NULL'),1)
        finally:
            self.db.execute('DROP TRIGGER publication_failure ON delivery_events')
            self.db.execute('DROP FUNCTION publication_failure()')
        self.assertTrue(self.feed(self.driver,second['cursor'])[1]['events'])

    def test_34_admin_user_active_guard_and_pagination(self):
        base=f'/api/admin/locations/{self.location}'
        self.assertEqual(api(self.admin,base+'/users?email='+self.identities[2]['username'])[1]['users'][0]['id'],self.users[2])
        self.assertEqual(self.checkin()[0],201)
        body={'userId':self.users[2],'status':'disabled','disableVehicle':True,'reason':'test'}
        self.assertEqual(api(self.admin,base+'/users','PUT',body)[0],409)
        self.assertEqual(api(self.staff,base+'/users','PUT',body)[0],403)
        self.assertEqual(api(self.admin,base+'/staff-list?offset=999999')[1]['staff'],[])
        self.assertEqual(api(self.admin,base+'/audit?offset=invalid')[0],400)
        self.assertEqual(api(self.driver,f'/api/locations/{self.location}/dashboard?offset=0')[0],200)

    def test_35_api_restart_retains_delivery(self):
        self.assertEqual(self.checkin()[0],201)
        first=self.feed(self.driver)[1]
        import os
        compose=['compose','--env-file','.env','--env-file',os.environ['PARKING_TEST_ENV_FILE'],'-f','compose.yaml','-f','compose.test.yaml','--profile','phase34']
        docker(compose+['restart','test-api'],capture_output=True,text=True)
        deadline=time.monotonic()+20
        while True:
            try:
                replay=self.feed(self.driver)[1]
                break
            except (urllib.error.URLError,OSError):
                if time.monotonic()>deadline:raise
                time.sleep(.2)
        self.assertEqual(replay['events'],first['events'])

    def test_36_browser_driver_staff_journey(self):
        from browser_journey import journey
        journey(self)

    def test_37_old_cursor_forces_snapshot_and_rollback_never_delivered(self):
        self.assertEqual(self.checkin()[0],201)
        first=self.feed(self.driver)[1]['cursor']
        self.db.execute("INSERT INTO outbox_events(location_id,aggregate_id,aggregate_version,event_type,payload) SELECT %s,%s,n,'test','{}' FROM generate_series(10000,11004) n",(self.location,self.spaces[1]))
        for _ in range(5):
            self.feed(self.driver)
            if self.scalar('SELECT count(*) FROM outbox_events WHERE published_at IS NULL')==0:break
        self.assertTrue(self.feed(self.driver,first)[1]['reset'])
        before=self.scalar('SELECT count(*) FROM delivery_events')
        with self.connect(False) as transaction:
            transaction.execute("INSERT INTO outbox_events(location_id,aggregate_id,aggregate_version,event_type,payload) VALUES(%s,%s,90000,'rolled_back','{}')",(self.location,self.spaces[0]))
            transaction.rollback()
        self.feed(self.driver)
        self.assertEqual(self.scalar('SELECT count(*) FROM delivery_events'),before)


    def test_38_driver_cannot_be_promoted_or_listed_as_staff(self):
        base=f'/api/admin/locations/{self.location}'
        email=self.db.execute('SELECT email FROM users WHERE id=%s',(self.users[2],)).fetchone()[0]
        self.assertEqual(api(self.driver,'/api/me')[1]['accountType'],'driver')
        rows=api(self.admin,base+'/staff-accounts')[1]['staffAccounts']
        self.assertNotIn(email,[row['email'] for row in rows])
        body={'userId':self.users[2],'role':'attendant','reason':'Must reject driver promotion'}
        code,result=api(self.admin,base+'/staff','POST',body)
        self.assertEqual((code,result['error']),(409,'driver_account_cannot_be_assigned_staff_role'))
        self.assertEqual(api(self.admin,base+'/staff-accounts','POST',{'email':email,'reason':'Must not convert driver'})[0],409)
        self.assertIsNone(self.db.execute('SELECT 1 FROM staff_assignments WHERE user_id=%s',(self.users[2],)).fetchone())
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.db.execute("INSERT INTO staff_assignments(user_id,location_id,role) VALUES(%s,%s,'attendant')",(self.users[2],self.location))

    def test_39_separate_staff_onboarding_and_authorization(self):
        base=f'/api/admin/locations/{self.location}'
        employee=create_user('employee-'+secrets.token_hex(6))
        email=employee['email']
        body={'email':email,'reason':'Dedicated employee onboarding'}
        self.assertEqual(api(self.driver,base+'/staff-accounts','POST',body)[0],403)
        self.assertEqual(api(self.staff,base+'/staff-accounts','POST',body)[0],403)
        self.assertEqual(api(self.admin,f'/api/admin/locations/{self.other_location}/staff-accounts','POST',body)[0],403)
        self.assertEqual(api(self.admin,base+'/staff-accounts','POST',body)[0],200)
        self.assertEqual(api(self.admin,base+'/staff-accounts','POST',body)[0],409)
        access=login(employee)['access_token']
        code,me=api(access,'/api/me');self.assertEqual(code,200)
        self.assertEqual(me['accountType'],'staff');self.assertEqual(me['assignments'],[])
        self.assertEqual(api(access,f'/api/staff/locations/{self.location}/spaces')[0],403)
        self.assertEqual(api(access,'/api/me/vehicle')[0],403)
        self.db.execute("UPDATE users SET approval_status='approved' WHERE id=%s",(me['id'],))
        code,result=api(access,'/api/me/vehicle','PUT',{'registrationJurisdiction':'TEST','registration':'STAFFCAR','vehicleType':'car'})
        self.assertEqual((code,result['error']),(409,'staff_account_cannot_register_driver_vehicle'))
        self.assertEqual(api(self.admin,base+'/users?email='+email)[1]['users'],[])
        self.assertEqual(api(self.admin,base+'/staff','POST',{'userId':me['id'],'role':'attendant','reason':'Employee assigned'})[0],200)
        self.db.execute("UPDATE users SET approval_status='approved' WHERE id=%s",(me['id'],))
        self.assertEqual(api(access,f'/api/staff/locations/{self.location}/spaces')[0],200)
        self.assertEqual(api(access,f'/api/staff/locations/{self.other_location}/spaces')[0],403)
        self.assertEqual(api(access,base+'/staff-accounts')[0],403)
        self.assertEqual(api(self.admin,base+'/staff','POST',{'userId':me['id'],'role':'none','reason':'Employee revoked'})[0],200)
        self.assertEqual(api(access,f'/api/staff/locations/{self.location}/spaces')[0],403)
        self.assertEqual(api(access,'/api/me')[1]['accountType'],'staff')

    def test_40_existing_driver_identity_cannot_claim_employee_email(self):
        base=f'/api/admin/locations/{self.location}'
        employee=create_user('existing-driver-'+secrets.token_hex(6))
        email=employee['email']
        self.assertEqual(api(self.admin,base+'/staff-accounts','POST',{'email':email,'reason':'Employee email reserved'})[0],200)
        # Represents an existing driver identity changing its email to a reserved one.
        self.db.execute('INSERT INTO users(identity_provider_reference,email) VALUES(%s,%s)',(IDENTITY+'/realms/'+REALM+'|'+employee['id'],'previous-'+email))
        access=login(employee)['access_token']
        me=api(access,'/api/me')[1]
        self.assertEqual(me['accountType'],'driver')
        self.assertIsNone(self.db.execute('SELECT user_id FROM staff_accounts WHERE email=%s',(email,)).fetchone()[0])
        self.assertEqual(api(self.admin,base+'/staff','POST',{'userId':me['id'],'role':'attendant','reason':'Must remain driver'})[0],409)

    def test_41_duplicate_registration_has_safe_specific_error(self):
        code,body=api(self.driver2,'/api/me/vehicle','PUT',{'registrationJurisdiction':'TEST','registration':'a-b 123','vehicleType':'car'})
        self.assertEqual((code,body['error']),(409,'vehicle_registration_already_in_use'))
        self.assertNotIn('email',body)
        self.assertEqual(api(self.driver2,'/api/me/vehicle')[1]['vehicle']['id'],self.v2)

    def test_43_staff_creates_driver_and_manages_driver_vehicle(self):
        base=f'/api/staff/locations/{self.location}/drivers'
        email='staff-created-'+secrets.token_hex(6)+'@example.test'
        body={'email':email,'firstName':'Synthetic','lastName':'Driver'}
        key=str(uuid.uuid4())
        self.assertEqual(api(self.driver,base,'POST',body,key)[0],403)
        self.assertEqual(api(self.staff,f'/api/staff/locations/{self.other_location}/drivers','POST',body,key)[0],403)
        code,created=api(self.staff,base,'POST',body,key)
        self.assertEqual(code,200,created);self.assertTrue(created['setupEmailSent'])
        self.assertEqual(api(self.staff,base,'POST',body,key)[1],created)
        self.assertEqual(api(self.staff,base,'POST',dict(body,lastName='Changed'),key)[0],409)
        self.assertEqual(api(self.staff,base,'POST',body,str(uuid.uuid4()))[0],409)
        owner=created['userId'];path=base+'/'+owner+'/vehicle'
        self.assertEqual(api(self.staff,path,'PUT',{'registrationJurisdiction':'TEST','registration':'PENDING','vehicleType':'car'})[0],409)
        self.assertEqual(api(self.admin,f'/api/admin/locations/{self.location}/approvals','POST',{'userId':owner,'decision':'approved','reason':'Driver approved after staff creation'})[0],200)
        vehicle={'registrationJurisdiction':'TEST','registration':'NEWDRIVER','vehicleType':'car','color':'White'}
        self.assertEqual(api(self.driver,path,'PUT',vehicle)[0],403)
        self.assertEqual(api(self.staff,f'/api/staff/locations/{self.other_location}/drivers/{owner}/vehicle','PUT',vehicle)[0],403)
        code,saved=api(self.staff,path,'PUT',vehicle);self.assertEqual(code,200,saved)
        self.assertEqual(saved['vehicle']['user_id'],owner)
        found=api(self.staff,base+'?email='+email)[1]['users'];self.assertEqual(found[0]['id'],owner)
        code,parked=self.checkin(vehicle=saved['vehicle']['id']);self.assertEqual(code,201,parked)
        self.assertEqual(api(self.staff,path,'PUT',dict(vehicle,registration='REPLACE'))[0],409)
        self.assertEqual(self.checkout(parked['session']['id'])[0],200)
        self.assertEqual(api(self.staff,path,'PUT',dict(vehicle,registration='REPLACE'))[0],200)
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions WHERE user_id=%s',(owner,)),1)

    def test_44_staff_request_after_registration_requires_admin_assignment(self):
        applicant=create_user('staff-applicant-'+secrets.token_hex(6))
        access=login(applicant)['access_token'];me=api(access,'/api/me')[1]
        self.assertEqual(me['accountType'],'driver')
        self.db.execute("UPDATE users SET approval_status='approved' WHERE id=%s",(me['id'],))
        self.assertEqual(api(access,'/api/me/staff-application','POST',{'locationId':self.location,'reason':'Employee application'})[0],200)
        self.assertEqual(api(access,'/api/me')[1]['accountType'],'staff')
        self.assertEqual(api(access,f'/api/staff/locations/{self.location}/spaces')[0],403)
        self.assertEqual(api(self.admin,f'/api/admin/locations/{self.location}/staff','POST',{'userId':me['id'],'role':'attendant','reason':'Employee approved after signup'})[0],200)
        self.assertEqual(api(access,f'/api/staff/locations/{self.location}/spaces')[0],200)
        self.assertEqual(api(self.driver,'/api/me/staff-application','POST',{'locationId':self.location,'reason':'Driver must not convert'})[0],409)

    def test_42_password_only_driver_login_and_parking_status(self):
        import os
        if os.environ.get('PARKING_TEST_PASSWORD_ONLY')!='1':self.skipTest('Dedicated --password-only run verifies local login mode')
        me=api(self.staff,'/api/me')[1]
        self.assertFalse(me['mfa']);self.assertFalse(me['staffMfaRequired'])
        self.assertEqual(self.checkin()[0],201)
        self.assertIsNotNone(api(self.driver,'/api/me/dashboard')[1]['current'])
        session=api(self.driver,'/api/me/parking-session')[1]['session']['id']
        self.assertEqual(self.checkout(session)[0],200)
        self.assertIsNone(api(self.driver,'/api/me/dashboard')[1]['current'])
        self.assertTrue(api(self.driver,'/api/me/parking-history')[1]['sessions'])
        self.assertEqual(api(self.driver,f'/api/staff/locations/{self.location}/spaces')[0],403)
        self.assertEqual(api(None,'/api/me')[0],401)

    def test_49_registration_pending_browser(self):
        from approval_browser import journey
        journey(self)

    def test_56_scoped_vehicle_register_and_location_names(self):
        self.db.execute('UPDATE users SET registration_location_id=%s WHERE id=%s',(self.location,self.users[2]))
        self.db.execute('UPDATE users SET registration_location_id=%s WHERE id=%s',(self.other_location,self.users[3]))
        self.db.execute("UPDATE vehicles SET make='TestMake',model='TestModel' WHERE id=%s",(self.v1,))
        base=f'/api/staff/locations/{self.location}/vehicle-register'
        self.assertEqual(api(self.driver,base)[0],403)
        self.assertEqual(api(self.staff,f'/api/staff/locations/{self.other_location}/vehicle-register')[0],403)
        for token in (self.staff,self.admin):
            code,data=api(token,base);self.assertEqual(code,200,data);self.assertEqual(data['counts']['total'],1);self.assertEqual([row['id'] for row in data['vehicles']],[self.v1]);self.assertEqual(data['vehicles'][0]['vehicle_name'],'TestMake TestModel');self.assertEqual(data['vehicles'][0]['owner_name'],'Synthetic Test')
        self.assertEqual(api(self.staff,base+'?search=missing')[1]['vehicles'],[])
        self.assertEqual(api(self.staff,base+'?status=invalid')[0],400)
        self.assertEqual(api(self.staff,base+'?offset=-1')[0],400)
        code,parked=self.checkin();self.assertEqual(code,201)
        self.assertEqual(api(self.staff,base+'?status=parked')[1]['counts']['parked'],1)
        self.assertEqual(api(self.staff,base+'?status=enabled')[1]['vehicles'],[])
        config=f'/api/admin/locations/{self.location}/configuration'
        body={'name':'Test Building','timezone':'Asia/Kolkata','area':'Test Area','city':'Test City','country':'India','address':'Main gate beside park','reason':'Reviewed readable building details'}
        self.assertEqual(api(self.staff,config,'PUT',body)[0],403)
        self.assertEqual(api(self.admin,config,'PUT',body)[0],200)
        self.assertEqual(api(self.driver,f'/api/locations/{self.location}/dashboard')[1]['location']['area'],'Test Area')
        self.assertEqual(api(self.admin,config,'PUT',dict(body,area='x'*201))[0],400)
        self.assertEqual(api(self.admin,config)[1]['location']['area'],'Test Area')
        self.assertEqual(self.checkout(parked['session']['id'])[0],200)
        self.assertEqual(api(self.driver,'/api/me/vehicle','PUT',{'disabled':True})[0],200)
        self.assertEqual(api(self.staff,base+'?status=disabled')[1]['counts']['disabled'],1)
        self.assertEqual(len(api(self.staff,base+'?status=disabled')[1]['vehicles']),1)

    def test_55_main_gate_verification_and_decisions(self):
        base=f'/api/staff/locations/{self.location}'
        query='/gate-check?jurisdiction=TEST&registration=AB123'
        self.assertEqual(api(self.driver,base+query)[0],403)
        self.assertEqual(api(self.staff,f'/api/staff/locations/{self.other_location}'+query)[0],403)
        for token in (self.staff,self.admin):
            code,gate=api(token,base+query);self.assertEqual(code,200,gate);self.assertEqual(gate['status'],'eligible');self.assertTrue(gate['canCheckIn']);self.assertEqual(gate['vehicle']['id'],self.v1)
            self.assertEqual({row['id'] for row in gate['spaces']},set(self.spaces[:2]))
        self.assertEqual(api(self.staff,base+'/gate-check?registration=AB123')[0],400)
        self.assertEqual(api(self.staff,base+'/gate-check?jurisdiction=TEST&registration=UNKNOWN')[1]['status'],'not_registered')
        for status in ('pending','rejected'):
            self.db.execute('UPDATE users SET approval_status=%s WHERE id=%s',(status,self.users[2]))
            gate=api(self.staff,base+query)[1];self.assertEqual(gate['status'],'approval_pending' if status=='pending' else 'registration_rejected');self.assertFalse(gate['canCheckIn']);self.assertEqual(gate['spaces'],[])
            self.assertEqual(self.checkin()[0],409)
        self.db.execute("UPDATE users SET approval_status='approved',status='disabled' WHERE id=%s",(self.users[2],))
        self.assertEqual(api(self.staff,base+query)[1]['status'],'account_disabled')
        self.db.execute("UPDATE users SET status='enabled' WHERE id=%s",(self.users[2],))
        self.db.execute('UPDATE vehicles SET disabled_at=now() WHERE id=%s',(self.v1,))
        self.assertEqual(api(self.staff,base+query)[1]['status'],'vehicle_disabled')
        self.db.execute('UPDATE vehicles SET disabled_at=NULL WHERE id=%s',(self.v1,))
        body={'registration':'UNKNOWN','jurisdiction':'TEST','decision':'rejected'};key=str(uuid.uuid4())
        self.assertEqual(api(self.staff,base+'/gate-decisions','POST',body)[0],400)
        self.assertEqual(api(self.driver,base+'/gate-decisions','POST',body,key)[0],403)
        self.assertEqual(api(self.staff,base+'/gate-decisions','POST',body,key)[0],200)
        self.assertEqual(api(self.staff,base+'/gate-decisions','POST',body,key)[0],200)
        self.assertEqual(api(self.staff,base+'/gate-decisions','POST',dict(body,comment='Different reason'),key)[0],409)
        self.assertEqual(self.scalar("SELECT count(*) FROM audit_events WHERE action='gate_entry_rejected'"),1)
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions'),0)
        self.assertEqual(api(self.admin,base+'/gate-decisions','POST',dict(body,comment='Not registered at gate'),str(uuid.uuid4()))[0],200)
        self.assertEqual(api(self.staff,base+'/gate-decisions','POST',dict(body,comment='x'*501),str(uuid.uuid4()))[0],400)
        check={'vehicleId':self.v1,'spaceId':self.spaces[0],'comment':'Visual plate verification at main gate'}
        code,parked=api(self.admin,'/api/staff/check-ins','POST',check,str(uuid.uuid4()));self.assertEqual(code,201,parked)
        self.assertEqual(api(self.staff,base+query)[1]['status'],'already_parked')
        self.assertEqual(self.scalar("SELECT sanitized_changes->>'comment' FROM audit_events WHERE action='gate_entry_approved'"),check['comment'])
        self.assertEqual(self.checkout(parked['session']['id'])[0],200)

    def test_53_staff_driver_approval_queues_and_scope(self):
        base=f'/api/staff/locations/{self.location}/approvals'
        applicants=[]
        for kind,location in [('driver',self.location),('employee',self.location),('driver',self.other_location)]:
            user=create_user('queue-'+kind+'-'+secrets.token_hex(5));access=login(user)['access_token'];profile=api(access,'/api/me')[1]
            code,places=api(access,'/api/me/registration-locations');self.assertEqual(code,200)
            self.assertTrue(all(set(row)=={'id','name'} for row in places['locations']))
            self.assertEqual(api(access,'/api/me/registration','POST',{'kind':kind,'locationId':location})[0],200)
            self.assertEqual(api(access,'/api/me')[1]['registrationLocationId'],location)
            applicants.append(profile['id'])
        driver,employee,other=applicants
        code,queue=api(self.staff,base);self.assertEqual(code,200,queue)
        self.assertIn(driver,[row['id'] for row in queue['requests']]);self.assertNotIn(employee,[row['id'] for row in queue['requests']]);self.assertNotIn(other,[row['id'] for row in queue['requests']])
        self.assertEqual(queue['counts']['pending'],1)
        body={'userId':driver,'decision':'approved','reason':'Verified driver identity and building access'}
        self.assertEqual(api(self.staff,base,'POST',body)[0],400)
        self.assertEqual(api(self.staff,base,'POST',dict(body,verificationConfirmed=True,role='operator_admin'))[0],403)
        self.assertEqual(api(self.staff,base,'POST',dict(body,userId=employee,verificationConfirmed=True))[0],403)
        self.assertEqual(api(self.staff,base,'POST',dict(body,userId=other,verificationConfirmed=True))[0],403)
        self.assertEqual(api(self.driver,base)[0],403)
        self.assertEqual(api(self.staff,f'/api/staff/locations/{self.other_location}/approvals')[0],403)
        self.assertEqual(api(self.staff,base,'POST',dict(body,verificationConfirmed=True))[0],200)
        queue=api(self.staff,base+'?status=approved')[1]
        self.assertIn(driver,[row['id'] for row in queue['requests']]);self.assertEqual(queue['counts']['pending'],0)
        self.assertEqual(api(self.staff,base+'?status=invalid')[0],400)
        self.assertEqual(self.scalar('SELECT count(*) FROM staff_assignments WHERE user_id=%s',(driver,)),0)
        rejected=create_user('queue-reject-'+secrets.token_hex(5));access=login(rejected)['access_token'];profile=api(access,'/api/me')[1]
        self.assertEqual(api(access,'/api/me/registration','POST',{'kind':'driver','locationId':self.location})[0],200)
        self.assertEqual(api(self.staff,base,'POST',dict(body,userId=profile['id'],decision='rejected'))[0],200)
        self.assertIn(profile['id'],[row['id'] for row in api(self.staff,base+'?status=rejected')[1]['requests']])

    def test_54_manual_building_coordinates_and_validation(self):
        base=f'/api/admin/locations/{self.location}/configuration'
        body={'name':'Test Building','timezone':'Asia/Kolkata','address':'Synthetic test address','latitude':'23.02','longitude':'72.57','reason':'Verified building position'}
        self.assertEqual(api(self.staff,base,'PUT',body)[0],403)
        self.assertEqual(api(self.admin,base,'PUT',body)[0],200)
        location=api(self.admin,base)[1]['location'];self.assertEqual(location['address'],body['address']);self.assertEqual(float(location['latitude']),23.02)
        for changes in ({'latitude':'91'},{'longitude':'181'},{'latitude':'NaN'},{'latitude':'12garbage'},{'longitude':''}):
            self.assertEqual(api(self.admin,base,'PUT',dict(body,**changes))[0],400)
        self.assertEqual(api(self.admin,base,'PUT',dict(body,latitude='',longitude=''))[0],200)
        self.assertIsNone(api(self.admin,base)[1]['location']['latitude'])

    def test_48_registration_approval_gate(self):
        self.assertEqual(api(None,'/api/locations')[0],401)
        for kind in ('driver','employee'):
            user=create_user('approval-'+kind+'-'+secrets.token_hex(5))
            access=login(user)['access_token'];profile=api(access,'/api/me')[1]
            self.assertEqual(profile['approvalStatus'],'pending')
            self.assertEqual(api(access,'/api/me/registration','POST',{'kind':kind})[0],200)
            self.assertEqual(api(access,'/api/me/registration','POST',{'kind':'employee'})[0],409)
            for path in ('/api/locations','/api/me/vehicle','/api/me/parking-history',f'/api/locations/{self.location}/events',f'/api/staff/locations/{self.location}/spaces'):
                self.assertEqual(api(access,path)[0],403,path)
            base=f'/api/admin/locations/{self.location}/approvals'
            decision={'userId':profile['id'],'decision':'approved','role':'attendant','reason':'Verified registration'}
            self.assertEqual(api(self.staff,base,'POST',decision)[0],403)
            self.assertEqual(api(self.admin,f'/api/admin/locations/{self.other_location}/approvals','POST',decision)[0],403)
            self.assertIn(profile['id'],[r['id'] for r in api(self.admin,base)[1]['requests']])
            self.assertEqual(api(self.admin,base+'?offset=-1')[0],400)
            import urllib.parse
            email=user['email']
            self.assertEqual([r['id'] for r in api(self.admin,base+'?search='+urllib.parse.quote(email))[1]['requests']],[profile['id']])
            self.assertEqual(api(self.admin,base,'POST',decision)[0],200)
            self.assertEqual(api(access,'/api/me')[1]['approvalStatus'],'approved')
            self.assertEqual(api(access,'/api/locations')[0],200)
            self.assertEqual(api(access,f'/api/staff/locations/{self.location}/spaces')[0],200 if kind=='employee' else 403)
            self.assertEqual(api(self.admin,base,'POST',decision)[0],409)
        rejected=create_user('approval-rejected-'+secrets.token_hex(5));access=login(rejected)['access_token'];profile=api(access,'/api/me')[1]
        self.assertEqual(api(access,'/api/me/registration','POST',{'kind':'driver'})[0],200)
        self.assertEqual(api(self.admin,base,'POST',{'userId':profile['id'],'decision':'rejected','reason':'Rejected request'})[0],200)
        self.assertEqual(api(access,'/api/locations')[0],403)
        self.assertEqual(api(access,'/api/me')[1]['approvalStatus'],'rejected')

    def test_47_admin_enrolls_registered_employee_without_granting_access(self):
        applicant=create_user('employee-enroll-'+secrets.token_hex(6))
        access=login(applicant)['access_token'];me=api(access,'/api/me')[1]
        base=f'/api/admin/locations/{self.location}'
        email=self.db.execute('SELECT email FROM users WHERE id=%s',(me['id'],)).fetchone()[0]
        body={'email':email,'reason':'Explicit employee enrollment'}
        self.assertEqual(api(self.staff,base+'/staff-accounts','POST',body)[0],403)
        self.assertEqual(api(self.admin,base+'/staff-accounts','POST',body)[0],200)
        self.assertEqual(api(access,'/api/me')[1]['accountType'],'staff')
        self.assertEqual(api(access,f'/api/staff/locations/{self.location}/spaces')[0],403)
        driver_email=self.db.execute('SELECT email FROM users WHERE id=%s',(self.users[2],)).fetchone()[0]
        self.assertEqual(api(self.admin,base+'/staff-accounts','POST',dict(body,email=driver_email))[0],409)
        self.assertEqual(api(self.admin,base+'/staff','POST',{'userId':me['id'],'role':'attendant','reason':'Admin approved location role'})[0],200)
        self.db.execute("UPDATE users SET approval_status='approved' WHERE id=%s",(me['id'],))
        self.assertEqual(api(access,f'/api/staff/locations/{self.location}/spaces')[0],200)

    def test_46_name_email_search_preserves_role_boundaries(self):
        name=self.db.execute('SELECT display_name FROM users WHERE id=%s',(self.users[2],)).fetchone()[0]
        base=f'/api/admin/locations/{self.location}'
        import urllib.parse
        query=urllib.parse.quote(name)
        code,result=api(self.admin,base+'/users?name='+query)
        self.assertEqual(code,200,result)
        self.assertIn(self.users[2],[row['id'] for row in result['users']])
        self.assertNotIn(self.users[0],[row['id'] for row in result['users']])
        self.assertEqual(api(self.driver,base+'/users?name='+query)[0],403)
        self.assertEqual(api(self.staff,f'/api/staff/locations/{self.other_location}/drivers?name='+query)[0],403)
        self.assertEqual(api(self.admin,base+'/users?name=x')[0],400)
        self.assertEqual(api(self.admin,base+'/users?name='+urllib.parse.quote("%' OR 1=1 --"))[1]['users'],[])
        email=self.db.execute('SELECT email FROM users WHERE id=%s',(self.users[0],)).fetchone()[0]
        code,result=api(self.admin,base+'/staff-accounts?search='+urllib.parse.quote(email))
        self.assertEqual(code,200,result)
        self.assertTrue(result['staffAccounts'])
        self.assertTrue(all(row['email']==email for row in result['staffAccounts']))

    def test_50_authenticated_load_with_parking_writes(self):
        import os
        from load_test import measure
        workers = os.environ.get('PARKING_TEST_LOAD_CONCURRENCY')
        if not workers:
            self.skipTest('Opt in with --load-concurrency 1..500')
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(measure, API, int(workers), 15, self.driver, self.location)
            time.sleep(2)
            code, body = self.checkin()
            self.assertEqual(code, 201, body)
            self.assertEqual(self.checkout(body['session']['id'])[0], 200)
            result = running.result()
        result.update(scope='isolated local synthetic test; shared driver identity across clients; no staging SLA',
                      runId=self.run_id, concurrentParkingWrites=2, businessWritesPerformed=True)
        folder = ROOT / '.tools/load-results'
        folder.mkdir(parents=True, exist_ok=True)
        report = folder / (self.run_id + '-authenticated.json')
        report.write_text(json.dumps(result, indent=2) + '\n')
        print('Retained authenticated load report:', report, flush=True)
        self.assertGreater(result['requests'], 0)
        self.assertEqual(result['errors'], 0, result)
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions WHERE checked_out_at IS NULL'), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM parking_sessions WHERE checked_out_at IS NOT NULL'), 1)

    def test_45_driver_setup_email_failure_is_retryable_without_deletion(self):
        base=f'/api/staff/locations/{self.location}/drivers'
        email='mail-retry-'+secrets.token_hex(6)+'@example.test'
        body={'email':email,'firstName':'Synthetic','lastName':'Mail retry'};key=str(uuid.uuid4())
        realm_url=IDENTITY+'/admin/realms/'+REALM;admin=admin_token()
        smtp=request(realm_url,token=admin)['smtpServer']
        request(realm_url,{'smtpServer':dict(smtp,port='1')},admin,method='PUT')
        try:
            code,created=api(self.staff,base,'POST',body,key,timeout=20)
            self.assertEqual(code,200,created);self.assertFalse(created['setupEmailSent'])
        finally:request(realm_url,{'smtpServer':smtp},admin,method='PUT')
        self.assertIsNotNone(self.db.execute('SELECT 1 FROM users WHERE id=%s',(created['userId'],)).fetchone())
        code,retried=api(self.staff,base,'POST',body,key)
        self.assertEqual(code,200,retried);self.assertTrue(retried['setupEmailSent'])
        self.assertEqual(created['userId'],retried['userId'])
        self.assertEqual(self.scalar('SELECT count(*) FROM users WHERE email=%s',(email,)),1)

if __name__ == '__main__':
    unittest.main()
