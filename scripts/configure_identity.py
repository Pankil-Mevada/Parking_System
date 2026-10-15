"""Configure local identity clients and password recovery without deleting users."""
import json
import urllib.parse
from identity_admin import IDENTITY, admin_token, environment, request, wait_identity
from parking_tools import ROOT, cli
from driver_identity_service import configure_driver_service


def main():
    wait_identity()
    token = admin_token()
    realm = json.loads((ROOT / 'identity/parking-realm.json').read_text())
    base = IDENTITY + '/admin/realms/parking'
    flows = request(base + '/authentication/flows', token=token)
    if not any(flow['alias']=='parking-password' for flow in flows):
        request(base+'/authentication/flows',{'alias':'parking-password','providerId':'basic-flow','topLevel':True,'builtIn':False},token)
        request(base+'/authentication/flows/parking-password/executions/execution',{'provider':'auth-username-password-form'},token)
        execution=request(base+'/authentication/flows/parking-password/executions',token=token)[0]
        request(base+'/authentication/flows/parking-password/executions',{'id':execution['id'],'requirement':'REQUIRED'},token,method='PUT')
    if not any(flow['alias'] == 'parking-reset' for flow in flows):
        request(base + '/authentication/flows', {
            'alias': 'parking-reset', 'providerId': 'basic-flow', 'topLevel': True, 'builtIn': False,
        }, token)
        for provider in ('reset-credentials-choose-user', 'reset-credential-email', 'reset-password'):
            request(base + '/authentication/flows/parking-reset/executions/execution', {'provider': provider}, token)
            executions = request(base + '/authentication/flows/parking-reset/executions', token=token)
            execution = next(item for item in executions if item.get('providerId') == provider)
            request(base + '/authentication/flows/parking-reset/executions', {'id': execution['id'], 'requirement': 'REQUIRED'}, token, method='PUT')
    require_mfa=environment().get('REQUIRE_STAFF_MFA','false')!='false'
    request(base, {'resetCredentialsFlow': 'parking-reset','browserFlow':'parking-mfa' if require_mfa else 'parking-password'}, token, method='PUT')
    for client in realm['clients']:
        if 'secret' in client:
            client['secret'] = environment()['OIDC_DRIVER_ADMIN_SECRET' if client['clientId']=='parking-driver-provisioner' else 'OIDC_CLIENT_SECRET']
        matches = request(IDENTITY + '/admin/realms/parking/clients?clientId=' + urllib.parse.quote(client['clientId']), token=token)
        if not matches and client['clientId']=='parking-driver-provisioner':
            request(base+'/clients',client,token)
            continue
        if len(matches) != 1:
            raise RuntimeError('Expected imported client: ' + client['clientId'])
        request(IDENTITY + '/admin/realms/parking/clients/' + matches[0]['id'], client, token, method='PUT')
    configure_driver_service('parking')
    if not require_mfa:
        offset=0
        while True:
            users=request(base+f'/users?first={offset}&max=100',token=token)
            for user in users:
                actions=user.get('requiredActions',[])
                if 'CONFIGURE_TOTP' in actions:request(base+'/users/'+user['id'],{'requiredActions':[action for action in actions if action!='CONFIGURE_TOTP']},token,method='PUT')
            if len(users)<100:break
            offset+=100
    print('Email/password login configured. Accounts, passwords and enrolled credentials preserved; local OTP requirement:',require_mfa)


if __name__ == '__main__':
    cli(main)
