"""Run phase 3-4 integration tests against disposable PostgreSQL and a test realm."""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from parking_tools import ROOT, cli, docker
from identity_admin import IDENTITY, admin_token, environment, request

COMPOSE = ['compose', '-f', 'compose.yaml', '-f', 'compose.test.yaml', '--profile', 'phase34']


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


def main():
    import os
    if not (ROOT / '.tools/test-python/psycopg').is_dir():
        raise RuntimeError('Install test prerequisites: py -m pip install --target .tools/test-python -r requirements-test.txt')
    docker(['compose', 'up', '-d', 'identity-gateway', 'mail'])
    # Reset only the local gateway's in-memory quotas for repeatable limiter tests.
    # Provider sessions and development parking records are preserved.
    docker(['compose', 'restart', 'identity-gateway'])
    wait(IDENTITY + '/realms/parking/.well-known/openid-configuration')
    token = admin_token()
    try:
        request(IDENTITY + '/admin/realms/parking-tests', token=token, method='DELETE')
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    realm = json.loads((ROOT / 'identity/parking-realm.json').read_text())
    realm['realm'] = 'parking-tests'
    realm['registrationAllowed'] = False
    realm['authenticationFlows'].append({
        'alias': 'test-password-only', 'providerId': 'basic-flow', 'topLevel': True, 'builtIn': False,
        'authenticationExecutions': [{'authenticator': 'auth-username-password-form',
                                     'requirement': 'REQUIRED', 'priority': 10, 'authenticatorFlow': False}],
    })
    realm['clients'][1]['secret'] = environment()['OIDC_CLIENT_SECRET']
    request(IDENTITY + '/admin/realms', realm, token)
    try:
        docker(COMPOSE + ['up', '-d', '--wait', '--wait-timeout', '60', 'test-db'])
        docker(COMPOSE + ['exec', '-T', 'test-db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'parking_test', '-d', 'parking_test', '-f', '/workspace/database/migrate.sql'])
        run_id = str(uuid.uuid4())
        docker(COMPOSE + ['exec', '-T', 'test-db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'parking_test', '-d', 'parking_test', '-c',
                          "CREATE TABLE test_run_guard(run_id uuid PRIMARY KEY); INSERT INTO test_run_guard VALUES ('" + run_id + "')"])
        docker(COMPOSE + ['up', '-d', '--force-recreate', 'test-api'])
        wait('http://127.0.0.1:18080/api/ready')
        env = os.environ.copy()
        env['PYTHONPATH'] = str(ROOT / '.tools/test-python') + os.pathsep + str(ROOT / 'scripts')
        env['PARKING_TEST_RUN_ID'] = run_id
        subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_phase34.py', '-v'], cwd=ROOT, env=env, check=True)
    except Exception:
        docker(COMPOSE + ['logs', '--tail', '30', 'test-api'])
        raise
    finally:
        # Remove only the explicitly named ephemeral test containers, never parking_data.
        docker(COMPOSE + ['rm', '-sf', 'test-api', 'test-db'])
        request(IDENTITY + '/admin/realms/parking-tests', token=admin_token(), method='DELETE')
        docker(['compose', 'restart', 'identity-gateway'])


if __name__ == '__main__':
    cli(main)
