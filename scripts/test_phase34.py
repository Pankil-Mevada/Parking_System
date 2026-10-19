"""Run integration tests while retaining each run, case schema and identity realm."""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import argparse
from parking_tools import ROOT, cli, docker
from identity_admin import IDENTITY, admin_token, environment, request
from retained_test_lock import retained_test_lock

def wait(url):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    raise RuntimeError('Service did not become ready: ' + url)


def run():
    import os
    parser = argparse.ArgumentParser(description='Run tests and retain all committed records for inspection.')
    parser.add_argument('--test-name',action='append',help='Optional unittest name substring; repeat to select several groups.')
    parser.add_argument('--password-only',action='store_true',help='Use local email/password mode for matching dedicated tests.')
    parser.add_argument('--simulator',action='store_true',help='Start the loopback hardware simulator with retained synthetic fixtures; holds the suite lock until stopped.')
    parser.add_argument('--load-concurrency',type=int,choices=range(1,501),metavar='1..500',help='Opt in to retained authenticated read load with concurrent parking writes (test_50).')
    args = parser.parse_args()
    if args.simulator:
        args.password_only = True
    if not (ROOT / '.tools/test-python/psycopg').is_dir():
        raise RuntimeError('Install test prerequisites: py -m pip install --target .tools/test-python -r requirements-test.txt')
    run_id = str(uuid.uuid4())
    realm_name = 'parking-tests-' + run_id.replace('-', '')[:12]
    folder = ROOT / '.tools/test-runs'
    folder.mkdir(parents=True, exist_ok=True)
    env_file = folder / (run_id + '.env')
    env_file.write_text('PARKING_TEST_REALM=' + realm_name + '\nPARKING_TEST_REQUIRE_MFA='+('false' if args.password_only else 'true')+'\n', encoding='utf-8')
    relative_env = env_file.relative_to(ROOT).as_posix()
    compose = ['compose', '--env-file', '.env', '--env-file', relative_env,
               '-f', 'compose.yaml', '-f', 'compose.test.yaml', '--profile', 'phase34']
    manifest = folder / (run_id + '.json')
    record = {'runId': run_id, 'realm': realm_name, 'database': 'parking_test',
              'status': 'preparing', 'retained': True}
    manifest.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print('Retained test run:', run_id, '\nIdentity realm:', realm_name, flush=True)
    try:
        docker(['compose', 'up', '-d', 'identity-gateway', 'mail'])
        # Reset gateway quotas, preserving provider sessions and parking records.
        docker(['compose', 'restart', 'identity-gateway'])
        wait(IDENTITY + '/realms/parking/.well-known/openid-configuration')
        token = admin_token()
        realm = json.loads((ROOT / 'identity/parking-realm.json').read_text())
        realm['realm'] = realm_name
        realm['registrationAllowed'] = False
        # Only synthetic test realms receive the longer browser token lifetime.
        realm['accessTokenLifespan'] = 1800
        realm['browserFlow']='parking-password' if args.password_only else 'parking-mfa'
        realm['authenticationFlows'].append({
            'alias': 'test-password-only', 'providerId': 'basic-flow', 'topLevel': True, 'builtIn': False,
            'authenticationExecutions': [{'authenticator': 'auth-username-password-form',
                                         'requirement': 'REQUIRED', 'priority': 10, 'authenticatorFlow': False}],
        })
        realm['clients'][1]['secret'] = environment()['OIDC_CLIENT_SECRET']
        request(IDENTITY + '/admin/realms', realm, token)
        from driver_identity_service import configure_driver_service
        configure_driver_service(realm_name)
    except Exception:
        record['status'] = 'preparation_failed'
        manifest.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        raise
    try:
        docker(compose + ['up', '-d', '--wait', '--wait-timeout', '60', 'test-db'])
        docker(compose + ['exec', '-T', 'test-db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'parking_test', '-d', 'parking_test', '-c',
                          'SET search_path TO public; ALTER ROLE parking_test SET search_path TO public;'])
        docker(compose + ['exec', '-T', 'test-db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'parking_test', '-d', 'parking_test', '-f', '/workspace/database/migrate.sql'])
        docker(compose + ['exec', '-T', 'test-db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'parking_test', '-d', 'parking_test', '-c',
                          "CREATE TABLE IF NOT EXISTS public.test_run_guard(run_id uuid PRIMARY KEY); INSERT INTO public.test_run_guard VALUES ('" + run_id + "')"])
        docker(compose + ['up', '-d', '--force-recreate', 'test-api', 'test-api-peer'])
        wait('http://127.0.0.1:18080/api/ready')
        env = os.environ.copy()
        env['PYTHONPATH'] = str(ROOT / '.tools/test-python') + os.pathsep + str(ROOT / 'scripts')
        env['PARKING_TEST_RUN_ID'] = run_id
        env['PARKING_TEST_REALM'] = realm_name
        env['PARKING_TEST_ENV_FILE'] = relative_env
        env['PARKING_TEST_PASSWORD_ONLY']='1' if args.password_only else '0'
        if args.load_concurrency:
            env['PARKING_TEST_LOAD_CONCURRENCY']=str(args.load_concurrency)
        else:
            env.pop('PARKING_TEST_LOAD_CONCURRENCY',None)
        command=[sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phase34.py', '-v']
        if args.simulator:
            command=[sys.executable, 'scripts/simulator_fixture.py']
        if args.test_name:
            for pattern in args.test_name:command.extend(['-k',pattern])
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        record['status'] = 'passed'
    except Exception:
        record['status'] = 'failed'
        docker(compose + ['logs', '--tail', '30', 'test-api'])
        raise
    finally:
        manifest.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print('Database, case schemas and identity realm retained. No automatic cleanup. Run: py scripts/view_database.py', flush=True)
        docker(['compose', 'restart', 'identity-gateway'])


def main():
    with retained_test_lock():
        run()


if __name__ == '__main__':
    cli(main)
