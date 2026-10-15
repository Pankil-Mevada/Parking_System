"""Explicit owner-operated development bootstrap; no default staff password.
py scripts/grant_local_admin.py --email owner@example.com --location LOCATION_UUID
Requires a registered, email-verified employee account. MFA follows local policy.
"""
import argparse
import json
import sys
import urllib.parse
import uuid
from parking_tools import ROOT, cli
from identity_admin import IDENTITY, admin_token, environment, request

def main():
    parser=argparse.ArgumentParser(description='Approve a verified local owner and grant location administration; audited.')
    parser.add_argument('--email',required=True)
    parser.add_argument('--create',action='store_true',help='Create the local owner if missing and send a Mailpit password/verification setup link; no approval queue.')
    parser.add_argument('--location',default='10000000-0000-0000-0000-000000000001')
    args=parser.parse_args();uuid.UUID(args.location)
    token=admin_token()
    env=environment()
    if env.get('APP_ENV','development')=='production':raise RuntimeError('This bootstrap is restricted to local development.')
    if args.create:
        smtp=request(IDENTITY+'/admin/realms/parking',token=token).get('smtpServer',{})
        if smtp.get('host')!='mail':raise RuntimeError('Local owner setup requires the local Mailpit SMTP server.')
    users=request(IDENTITY+'/admin/realms/parking/users?email='+urllib.parse.quote(args.email)+'&exact=true',token=token)
    if not users and args.create:
        request(IDENTITY+'/admin/realms/parking/users',{'username':args.email,'email':args.email,'firstName':'Parking','lastName':'Administrator','enabled':True,'emailVerified':False,'requiredActions':['VERIFY_EMAIL','UPDATE_PASSWORD']},token,method='POST')
        users=request(IDENTITY+'/admin/realms/parking/users?email='+urllib.parse.quote(args.email)+'&exact=true',token=token)
    if len(users)!=1 or (not users[0].get('emailVerified') and not args.create) or not users[0].get('enabled'):
        raise RuntimeError('Expected exactly one enabled, verified registered account.')
    user=users[0]
    credentials=request(IDENTITY+'/admin/realms/parking/users/'+user['id']+'/credentials',token=token)
    if env.get('REQUIRE_STAFF_MFA','false')!='false' and not any(item['type']=='otp' for item in credentials):raise RuntimeError('Enroll an authenticator in this account first.')
    sys.path.insert(0,str(ROOT/'.tools/test-python'))
    import psycopg
    with psycopg.connect(host='127.0.0.1',port=5432,dbname=env['POSTGRES_DB'],user=env['POSTGRES_USER'],password=env['POSTGRES_PASSWORD']) as db:
        if not db.execute('SELECT 1 FROM locations WHERE id=%s',(args.location,)).fetchone():raise RuntimeError('Unknown local location.')
        reference=IDENTITY+'/realms/parking|'+user['id']
        db.execute('INSERT INTO users(identity_provider_reference,display_name,email) VALUES(%s,%s,%s) ON CONFLICT(identity_provider_reference) DO NOTHING',(reference,((user.get('firstName','')+' '+user.get('lastName','')).strip()),user['email']))
        row=db.execute('SELECT id,status FROM users WHERE identity_provider_reference=%s FOR UPDATE',(reference,)).fetchone()
        if row[1]!='enabled':raise RuntimeError('The account is disabled.')
        if db.execute('SELECT 1 FROM vehicles WHERE user_id=%s UNION ALL SELECT 1 FROM parking_sessions WHERE user_id=%s LIMIT 1',(row[0],row[0])).fetchone():raise RuntimeError('Use a separate employee account with no driver vehicle or parking history.')
        db.execute("UPDATE users SET approval_status='approved',registration_kind='employee' WHERE id=%s",(row[0],))
        db.execute('INSERT INTO staff_accounts(email,user_id,location_id,created_by) VALUES(lower(btrim(%s)),%s,%s,%s) ON CONFLICT(email) DO NOTHING',(user['email'],row[0],args.location,row[0]))
        db.execute("INSERT INTO staff_assignments(user_id,location_id,role) VALUES(%s,%s,'operator_admin') ON CONFLICT(user_id,location_id) DO UPDATE SET role=excluded.role",(row[0],args.location))
        db.execute("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES(%s,'local_admin_bootstrap','location',%s,%s,%s::jsonb)",(row[0],args.location,str(uuid.uuid4()),json.dumps({'reason':'Explicit local owner bootstrap','userId':str(row[0])})))
    print('Location administration granted and audited. Refresh the parking page and select Administrator dashboard.')
    if args.create and not user.get('emailVerified'):
        query=urllib.parse.urlencode({'client_id':'parking-web','redirect_uri':'http://127.0.0.1:5173/','lifespan':900})
        request(IDENTITY+'/admin/realms/parking/users/'+user['id']+'/execute-actions-email?'+query,['VERIFY_EMAIL','UPDATE_PASSWORD'],token,method='PUT')
        print('Open http://127.0.0.1:8025/ to verify the administrator email and set its private password. No administrator approval is required.')

if __name__=='__main__':cli(main)
