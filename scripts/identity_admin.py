"""Local provisioning helpers. Credentials remain in memory; no external mail."""
import json
import urllib.request
import urllib.parse
import time
import urllib.error
from parking_tools import ROOT

IDENTITY = 'http://127.0.0.1:8180'


def environment():
    return dict(line.split('=', 1) for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines()
                if line and not line.startswith('#') and '=' in line)


def request(url, body=None, token=None, method=None, form=False):
    headers = {}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None
    if body is not None:
        data = (urllib.parse.urlencode(body) if form else json.dumps(body)).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    with urllib.request.urlopen(urllib.request.Request(url, data, headers, method=method), timeout=15) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def admin_token():
    env = environment()
    return request(IDENTITY + '/realms/master/protocol/openid-connect/token', {
        'client_id': 'admin-cli', 'grant_type': 'password',
        'username': env['OIDC_ADMIN_USER'], 'password': env['OIDC_ADMIN_PASSWORD'],
    }, form=True)['access_token']


def wait_identity():
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            request(IDENTITY + '/realms/parking/.well-known/openid-configuration')
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    raise RuntimeError('Identity provider did not become ready.')
