"""Provision a separate local runtime login; owner credentials remain for migrations.

Does not switch the running API automatically. Outputs only a secret-file path.
"""
import os
import secrets
import argparse
from parking_tools import ROOT, cli
from ops_tools import postgres
from identity_admin import environment

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--refresh-grants',action='store_true',help='Apply current table grants without rotating existing credentials.');args=parser.parse_args()
    env=environment();folder=ROOT/'.tools/secrets';folder.mkdir(parents=True,exist_ok=True)
    path=folder/'runtime-database-url'
    if path.exists() and not args.refresh_grants:raise RuntimeError('Runtime secret already exists. Use --refresh-grants for additive migrations; rotation needs a coordinated change.')
    password=secrets.token_hex(32)
    with postgres() as db:
        from psycopg import sql
        exists=bool(db.execute("SELECT 1 FROM pg_roles WHERE rolname='parking_runtime'").fetchone())
        if args.refresh_grants and (not exists or not path.exists()):raise RuntimeError('Provision the runtime login first; refresh never creates or rotates credentials.')
        if exists and not args.refresh_grants:raise RuntimeError('Runtime role already exists; do not overwrite its credential.')
        if not args.refresh_grants:db.execute(sql.SQL('CREATE ROLE parking_runtime LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION').format(sql.Literal(password)))
        db.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO parking_runtime').format(sql.Identifier(env['POSTGRES_DB'])))
        db.execute('GRANT USAGE ON SCHEMA public TO parking_runtime')
        db.execute('GRANT SELECT ON ALL TABLES IN SCHEMA public TO parking_runtime')
        for table in ('users','vehicles','locations','zones','spaces','parking_sessions','outbox_events','client_health','staff_accounts'):
            db.execute(sql.SQL('GRANT INSERT, UPDATE ON {} TO parking_runtime').format(sql.Identifier(table)))
        for table in ('audit_events','delivery_events','idempotency_records','revoked_auth_sessions'):
            if db.execute('SELECT to_regclass(%s)',(table,)).fetchone()[0]:db.execute(sql.SQL('GRANT INSERT ON {} TO parking_runtime').format(sql.Identifier(table)))
        db.execute('GRANT INSERT, UPDATE, DELETE ON staff_assignments TO parking_runtime')
        db.execute('GRANT UPDATE ON idempotency_records TO parking_runtime')
        db.execute('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO parking_runtime')
        # Write before commit so a filesystem failure rolls back role provisioning.
        if not args.refresh_grants:
            descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'w') as output:output.write('host=db port=5432 dbname='+env['POSTGRES_DB']+' user=parking_runtime password='+password+'\n')
    print('Runtime grants refreshed without credential changes.' if args.refresh_grants else 'Runtime login provisioned. Private DSN file: '+str(path))
    print('Apply grants for future migrations explicitly. Audit UPDATE/DELETE and schema changes are not granted.')

if __name__=='__main__':cli(main)
