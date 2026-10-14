"""Configure local identity clients and password recovery without deleting users."""
import json
import urllib.parse
from identity_admin import IDENTITY, admin_token, environment, request, wait_identity
from parking_tools import ROOT, cli


def main():
    wait_identity()
    token = admin_token()
    realm = json.loads((ROOT / 'identity/parking-realm.json').read_text())
    base = IDENTITY + '/admin/realms/parking'
    flows = request(base + '/authentication/flows', token=token)
    if not any(flow['alias'] == 'parking-reset' for flow in flows):
        request(base + '/authentication/flows', {
            'alias': 'parking-reset', 'providerId': 'basic-flow', 'topLevel': True, 'builtIn': False,
        }, token)
        for provider in ('reset-credentials-choose-user', 'reset-credential-email', 'reset-password'):
            request(base + '/authentication/flows/parking-reset/executions/execution', {'provider': provider}, token)
            executions = request(base + '/authentication/flows/parking-reset/executions', token=token)
            execution = next(item for item in executions if item.get('providerId') == provider)
            request(base + '/authentication/flows/parking-reset/executions', {'id': execution['id'], 'requirement': 'REQUIRED'}, token, method='PUT')
    request(base, {'resetCredentialsFlow': 'parking-reset'}, token, method='PUT')
    for client in realm['clients']:
        if 'secret' in client:
            client['secret'] = environment()['OIDC_CLIENT_SECRET']
        matches = request(IDENTITY + '/admin/realms/parking/clients?clientId=' + urllib.parse.quote(client['clientId']), token=token)
        if len(matches) != 1:
            raise RuntimeError('Expected imported client: ' + client['clientId'])
        request(IDENTITY + '/admin/realms/parking/clients/' + matches[0]['id'], client, token, method='PUT')
    print('Local identity clients and password recovery configured; users and credentials preserved.')


if __name__ == '__main__':
    cli(main)
