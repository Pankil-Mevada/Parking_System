"""Cold local recovery drill: retain encrypted data/config and isolated restores.

The source API and Keycloak are briefly stopped for a consistent maintenance
checkpoint. Original containers are restarted even if a backup fails. H2 recovery
uses the exact original image; this is not a production database migration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from urllib.parse import quote

from parking_tools import ROOT, cli, docker, wsl
from identity_admin import request, admin_token, IDENTITY
from ops_tools import tool
from backup_database import backup, restore, key
from retained_test_lock import retained_test_lock

RESTORE_PID = None

def inspect(container):
    return json.loads(docker(['inspect', container], capture_output=True, text=True).stdout)[0]


def service(name):
    value = docker(['compose', 'ps', '-q', name], capture_output=True, text=True).stdout.strip()
    if not value or '\n' in value:
        raise RuntimeError('Expected exactly one running local service: ' + name)
    return value


def checksum(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def recovery_request(url, body=None, token=None, form=False):
    # Docker's internal network is intentionally unreachable from Windows.
    # Query from its Linux host; credentials travel via stdin, not command args.
    code = '''import json,sys,urllib.request,urllib.parse
v=json.load(sys.stdin)
h={}
if v['token']: h['Authorization']='Bearer '+v['token']
data=None
if v['body'] is not None:
 data=(urllib.parse.urlencode(v['body']) if v['form'] else json.dumps(v['body'])).encode()
 h['Content-Type']='application/x-www-form-urlencoded' if v['form'] else 'application/json'
with urllib.request.urlopen(urllib.request.Request(v['url'],data,h),timeout=10) as r:
 print(r.read().decode())
'''
    try:
        command = ['nsenter', '--target', str(RESTORE_PID), '--net', '--', 'python3', '-c', code]
        if not RESTORE_PID:
            raise RuntimeError('Restore network namespace is not configured.')
        options = dict(input=json.dumps(dict(url=url, body=body, token=token, form=form)), capture_output=True, text=True)
        result = wsl(command, **options) if os.name == 'nt' else subprocess.run(command, check=True, **options)
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, ValueError):
        raise OSError('Isolated identity request failed; private diagnostics suppressed.') from None


def inventory(base, token, requester=request):
    """Return a digest of realm/user IDs without writing personal data to reports."""
    result = {}
    for realm in requester(base + '/admin/realms', token=token):
        name = realm['realm']
        users = []
        first = 0
        while True:
            batch = requester(base + '/admin/realms/' + quote(name, safe='') + f'/users?first={first}&max=100', token=token)
            users.extend(user['id'] for user in batch)
            if len(batch) < 100:
                break
            first += 100
        result[name] = sorted(users)
    digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return {'realmCount': len(result), 'userCount': sum(map(len, result.values())), 'identityDigest': digest}


def encrypt(target, producer):
    _, recipient = key()
    with subprocess.Popen([tool('age'), '-r', recipient, '-o', str(target)], stdin=subprocess.PIPE,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
        try:
            producer(process.stdin)
        finally:
            process.stdin.close()
        if process.wait(timeout=120):
            raise RuntimeError('Encryption failed; partial backup retained.')


def decrypt_to_docker(cipher, arguments):
    private, _ = key()
    with subprocess.Popen([tool('age'), '-d', '-i', str(private), str(cipher)], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as process:
        try:
            docker(arguments, stdin=process.stdout, stdout=subprocess.DEVNULL)
        finally:
            process.stdout.close()
        if process.wait(timeout=120):
            raise RuntimeError('Decryption failed; isolated restore retained.')


def wait(base):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            recovery_request(base + '/realms/master/.well-known/openid-configuration')
            return
        except (OSError, ValueError):
            time.sleep(1)
    raise RuntimeError('Restored identity did not become ready.')


def checkpoint():
    api, identity, db = (service(name) for name in ('api', 'identity', 'db'))
    source = inspect(identity)
    mounts = [item for item in source['Mounts'] if item['Destination'] == '/opt/keycloak/data' and item['Type'] == 'volume']
    if len(mounts) != 1:
        raise RuntimeError('Expected one named identity data volume.')
    expected = inventory(IDENTITY, admin_token())
    # Stop/start existing IDs: never recreate source services from another checkout.
    try:
        docker(['stop', '--time', '60', api], stdout=subprocess.DEVNULL)
        docker(['stop', '--time', '60', identity], stdout=subprocess.DEVNULL)
        if inspect(identity)['State']['Running'] or inspect(api)['State']['Running']:
            raise RuntimeError('Source services must be stopped before checkpoint.')
        folder = backup()
        helper_image = inspect(db)['Image']
        encrypt(folder / 'identity.tar.age', lambda pipe: docker([
            'run', '--rm', '--network', 'none', '--read-only', '--user', '0',
            '--mount', 'type=volume,src=' + mounts[0]['Name'] + ',dst=/source,readonly',
            '--entrypoint', 'tar', helper_image, '-C', '/source', '-cf', '-', '.'
        ], stdout=pipe))
        encrypt(folder / 'configuration.age', lambda pipe: pipe.write((ROOT / '.env').read_bytes()))
        record = {
            'format': 1, 'scope': 'local parking PostgreSQL, stopped Keycloak H2 and private configuration',
            'identityImage': source['Image'], 'helperImage': helper_image,
            'inventory': expected,
            'files': {name: checksum(folder / name) for name in ('parking.dump.age', 'identity.tar.age', 'configuration.age')},
        }
        (folder / 'recovery.json').write_text(json.dumps(record, indent=2) + '\n')
        return folder
    finally:
        # Try both restarts independently; failure of identity restart must not
        # prevent the API restart attempt.
        try:
            docker(['start', identity], stdout=subprocess.DEVNULL)
        finally:
            docker(['start', api], stdout=subprocess.DEVNULL)


def validate(folder):
    folder = Path(folder).resolve()
    if not folder.is_relative_to((ROOT / '.tools/backups').resolve()):
        raise RuntimeError('Recovery input must be a retained local backup.')
    record = json.loads((folder / 'recovery.json').read_text())
    if record.get('format') != 1:
        raise RuntimeError('Unsupported recovery format.')
    for name in ('parking.dump.age', 'identity.tar.age', 'configuration.age'):
        if checksum(folder / name) != record['files'][name]:
            raise RuntimeError('Recovery checksum mismatch: ' + name)
    return folder, record


def drill(folder):
    global RESTORE_PID
    folder, record = validate(folder)
    started = time.monotonic()
    run = uuid.uuid4().hex
    volume, network, container = ('parking-recovery-' + run + suffix for suffix in ('-data', '-network', '-identity'))
    report = {'status': 'preparing', 'retained': True, 'identityContainer': container, 'identityVolume': volume,
              'network': network, 'sourceModifiedByRestore': False, 'productionAcceptance': False}
    try:
        report['databaseRestore'] = restore(folder)
        docker(['volume', 'create', volume], stdout=subprocess.DEVNULL)
        # Internal network prevents restored SMTP settings from sending real mail.
        docker(['network', 'create', '--internal', network], stdout=subprocess.DEVNULL)
        decrypt_to_docker(folder / 'identity.tar.age', [
            'run', '--rm', '-i', '--network', 'none', '--user', '0',
            '--mount', 'type=volume,src=' + volume + ',dst=/restore', '--entrypoint', 'tar',
            record['helperImage'], '-C', '/restore', '-xf', '-'])
        docker(['run', '-d', '--name', container, '--network', network,
                '--mount', 'type=volume,src=' + volume + ',dst=/opt/keycloak/data',
                record['identityImage'], 'start-dev', '--hostname', 'http://127.0.0.1:18180'], stdout=subprocess.DEVNULL)
        RESTORE_PID = inspect(container)['State']['Pid']
        # Query loopback inside the isolated server's network namespace. Master
        # realm login can require HTTPS for non-loopback clients even in dev mode.
        base = 'http://127.0.0.1:8080'
        wait(base)
        private, _ = key()
        config = subprocess.run([tool('age'), '-d', '-i', str(private), str(folder / 'configuration.age')],
                                check=True, capture_output=True).stdout.decode('utf-8')
        env = dict(line.split('=', 1) for line in config.splitlines() if line and not line.startswith('#') and '=' in line)
        token = recovery_request(base + '/realms/master/protocol/openid-connect/token', {
            'client_id': 'admin-cli', 'grant_type': 'password',
            'username': env['OIDC_ADMIN_USER'], 'password': env['OIDC_ADMIN_PASSWORD']}, form=True)['access_token']
        actual = inventory(base, token, requester=recovery_request)
        if actual != record['inventory']:
            raise RuntimeError('Restored realm/user identity inventory differs.')
        # Client credentials prove restored application secrets still work. This
        # does not impersonate users or change their passwords.
        recovery_request(base + '/realms/parking/protocol/openid-connect/token', {
            'client_id': 'parking-driver-provisioner', 'client_secret': env['OIDC_DRIVER_ADMIN_SECRET'],
            'grant_type': 'client_credentials'}, form=True)
        report.update(status='passed', identityInventoryVerified=True, administratorLoginVerified=True,
                      applicationServiceLoginVerified=True, configurationDecrypted=True, inventory=actual)
    finally:
        report['elapsedSeconds'] = round(time.monotonic() - started, 3)
        if report['status'] != 'passed':
            report['status'] = 'failed'
        (folder / ('full-restore-' + run + '.json')).write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        # Retain all restored data, but stop the duplicate login service.
        result = docker(['ps', '-aq', '--filter', 'name=^/' + container + '$'], capture_output=True, text=True)
        if result.stdout.strip():
            docker(['stop', '--time', '60', container], stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', help='Repeat a drill from a retained checkpoint; source is not stopped.')
    args = parser.parse_args()
    with retained_test_lock():
        drill(args.restore or checkpoint())


if __name__ == '__main__':
    cli(main)
