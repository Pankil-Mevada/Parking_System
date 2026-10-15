"""Explicit owner-operated development bootstrap; no default staff password.
py scripts/grant_local_admin.py --email owner@example.com --location LOCATION_UUID
Requires a registered, email-verified account with an enrolled authenticator.
"""
import argparse
import json
import sys
import urllib.parse
import uuid
from parking_tools import ROOT, cli
from identity_admin import IDENTITY, admin_token, environment, request

def main():
    parser=argparse.ArgumentParser(description='Grant an existing verified MFA account local location administration; audited.')
    parser.add_argument('--email',required=True)
    parser.add_argument('--location',default='10000000-0000-0000-0000-000000000001')
    args=parser.parse_args();uuid.UUID(args.location)
    token=admin_token()
    users=request(IDENTITY+'/admin/realms/parking/users?email='+urllib.parse.quote(args.email)+'&exact=true',token=token)
    if len(users)!=1 or not users[0].get('emailVerified') or not users[0].get('enabled'):
        raise RuntimeError('Expected exactly one enabled, verified registered account.')
    user=users[0]
    credentials=request(IDENTITY+'/admin/realms/parking/users/'+user['id']+'/credentials',token=token)
    if environment().get('REQUIRE_STAFF_MFA','false')!='false' and not any(item['type']=='otp' for item in credentials):raise RuntimeError('Enroll an authenticator in this account first.')
    sys.path.insert(0,str(ROOT/'.tools/test-python'))
    import psycopg
    env=environment()
    with psycopg.connect(host='127.0.0.1',port=5432,dbname=env['POSTGRES_DB'],user=env['POSTGRES_USER'],password=env['POSTGRES_PASSWORD']) as db:
        if not db.execute('SELECT 1 FROM locations WHERE id=%s',(args.location,)).fetchone():raise RuntimeError('Unknown local location.')
        row=db.execute('SELECT id,status FROM users WHERE identity_provider_reference=%s FOR UPDATE',(IDENTITY+'/realms/parking|'+user['id'],)).fetchone()
        if not row or row[1]!='enabled':raise RuntimeError('Sign into the parking application once before granting access.')
        if db.execute('SELECT 1 FROM vehicles WHERE user_id=%s AND disabled_at IS NULL',(row[0],)).fetchone():raise RuntimeError('Use a separate employee account with no enabled driver vehicle.')
        db.execute('INSERT INTO staff_accounts(email,user_id,location_id,created_by) VALUES(lower(btrim(%s)),%s,%s,%s) ON CONFLICT(email) DO NOTHING',(user['email'],row[0],args.location,row[0]))
        db.execute("INSERT INTO staff_assignments(user_id,location_id,role) VALUES(%s,%s,'operator_admin') ON CONFLICT(user_id,location_id) DO UPDATE SET role=excluded.role",(row[0],args.location))
        db.execute("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES(%s,'local_admin_bootstrap','location',%s,%s,%s::jsonb)",(row[0],args.location,str(uuid.uuid4()),json.dumps({'reason':'Explicit local owner bootstrap','userId':str(row[0])})))
    print('Location administration granted and audited. Refresh the parking page and select Administrator dashboard.')

if __name__=='__main__':cli(main)
