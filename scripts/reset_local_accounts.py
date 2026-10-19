"""Explicit owner-requested main-development account reset, with encrypted backup.

Building configuration, service identities, test realms/databases and backups stay.
No production operation and no automatic test cleanup.
"""
import argparse
from datetime import datetime, timezone
import json
import subprocess
import uuid

from identity_admin import IDENTITY, admin_token, environment, request, wait_identity
from ops_tools import postgres
from parking_tools import ROOT, cli, docker
from recover_local import checkpoint, service, validate
from retained_test_lock import retained_test_lock


TABLES = ('client_health', 'delivery_events', 'outbox_events', 'idempotency_records',
          'audit_events', 'parking_sessions', 'staff_assignments', 'staff_accounts',
          'vehicles', 'users', 'revoked_auth_sessions')


def reset_tables(connection):
    tables = list(TABLES)
    # Newer local hardware migrations reference users/vehicles. Device inventory
    # itself references the retained building and is deliberately preserved.
    for table in ('simulated_tags', 'simulated_device_events'):
        if connection.execute('SELECT to_regclass(%s)', ('public.' + table,)).fetchone()[0]:
            tables.append(table)
    qualified = ['public.' + table for table in tables]
    dependencies = connection.execute(
        "SELECT conrelid::regclass::text FROM pg_constraint WHERE contype='f' "
        'AND confrelid=ANY(%s::regclass[]) AND NOT(conrelid=ANY(%s::regclass[]))',
        (qualified, qualified)).fetchall()
    if dependencies:
        raise RuntimeError('Unexpected account dependencies; reset stopped before identity deletion.')
    return tables


def accounts(token):
    result = []
    first = 0
    while True:
        batch = request(IDENTITY + f'/admin/realms/parking/users?first={first}&max=100', token=token)
        result.extend(user for user in batch if not user.get('username', '').startswith('service-account-'))
        if len(batch) < 100:
            return result
        first += 100


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-main-account-reset', action='store_true', required=True)
    parser.add_argument('--checkpoint', help='Reuse a retained encrypted checkpoint when resuming an interrupted owner reset.')
    args = parser.parse_args()
    env = environment()
    if env.get('APP_ENV', 'development') != 'development' or env['POSTGRES_DB'] in ('parking_test', 'postgres'):
        raise RuntimeError('Reset is restricted to the configured main development database.')
    with retained_test_lock():
        wait_identity()
        # Validate the retained building before any destructive operation.
        with postgres() as connection:
            if connection.execute('SELECT current_database()').fetchone()[0] != env['POSTGRES_DB']:
                raise RuntimeError('Main database mismatch.')
            layout = connection.execute('SELECT (SELECT count(*) FROM public.locations), (SELECT count(*) FROM public.spaces)').fetchone()
            tables = reset_tables(connection)
        print('Using retained pre-reset checkpoint.' if args.checkpoint else
              'Creating encrypted pre-reset parking/identity/configuration checkpoint.', flush=True)
        folder = validate(args.checkpoint)[0] if args.checkpoint else checkpoint()
        print('Pre-reset checkpoint completed:', folder.name, flush=True)
        report = {'requestedAt': datetime.now(timezone.utc).isoformat(), 'scope': 'main development accounts and parking data',
                  'backup': folder.name, 'testDataRetained': True, 'buildingConfigurationRetained': True, 'status': 'started'}
        wait_identity()
        token = admin_token()
        realm_url = IDENTITY + '/admin/realms/parking'
        registration = request(realm_url, token=token)['registrationAllowed']
        api = service('api')
        try:
            docker(['stop', '--time', '60', api], stdout=subprocess.DEVNULL)
            request(realm_url, {'registrationAllowed': False}, token, method='PUT')
            request(realm_url + '/logout-all', token=token, method='POST')
            people = accounts(token)
            # DELETE scope is the normal parking realm only, never master or test realms.
            for user in people:
                request(realm_url + '/users/' + str(uuid.UUID(user['id'])), token=token, method='DELETE')
            with postgres() as connection:
                from psycopg import sql
                connection.execute("SET LOCAL lock_timeout = '10s'")
                report['removedRows'] = {table: connection.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(table))).fetchone()[0]
                                         for table in tables}
                # Explicit table set, no CASCADE: unexpected foreign-key dependencies fail closed.
                connection.execute(sql.SQL('TRUNCATE TABLE {} RESTRICT').format(
                    sql.SQL(',').join(sql.Identifier('public', table) for table in tables)))
                actual = connection.execute('SELECT (SELECT count(*) FROM public.locations), (SELECT count(*) FROM public.spaces)').fetchone()
                if actual != layout:
                    raise RuntimeError('Building layout changed; database transaction rolled back.')
            if accounts(token):
                raise RuntimeError('Main realm still contains user accounts; inspect retained reset report.')
            report.update(status='completed', removedLoginAccounts=len(people), remainingLoginAccounts=0,
                          remainingAppUsers=0, locations=layout[0], spaces=layout[1])
        finally:
            try:
                request(realm_url, {'registrationAllowed': registration}, token, method='PUT')
            finally:
                docker(['start', api], stdout=subprocess.DEVNULL)
                (folder / 'owner-reset.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2), flush=True)
        print('Register again at http://127.0.0.1:5173/. No administrator was recreated and no default password exists.', flush=True)


if __name__ == '__main__':
    cli(main)
