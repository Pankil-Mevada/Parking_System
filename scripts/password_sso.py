"""Configure provider-managed local SSO; no token persistence in the web app."""
from identity_admin import IDENTITY, admin_token, request


def ensure_password_sso(realm='parking'):
    token = admin_token()
    base = IDENTITY + '/admin/realms/' + realm + '/authentication'
    alias, forms = 'parking-password-sso', 'parking-password-sso-forms'
    flows = request(base + '/flows', token=token)
    if not any(item['alias'] == alias for item in flows):
        request(base + '/flows', {'alias': alias, 'providerId': 'basic-flow', 'topLevel': True, 'builtIn': False}, token)
    executions = request(base + '/flows/' + alias + '/executions', token=token)
    if not any(item.get('providerId') == 'auth-cookie' for item in executions):
        request(base + '/flows/' + alias + '/executions/execution', {'provider': 'auth-cookie'}, token)
    if not any(item.get('displayName') == forms for item in executions):
        request(base + '/flows/' + alias + '/executions/flow',
                {'alias': forms, 'type': 'basic-flow', 'provider': 'basic-flow', 'description': 'Password form when no valid SSO session exists'}, token)
    executions = request(base + '/flows/' + forms + '/executions', token=token)
    if not any(item.get('providerId') == 'auth-username-password-form' for item in executions):
        request(base + '/flows/' + forms + '/executions/execution', {'provider': 'auth-username-password-form'}, token)
    for flow, requirement in ((alias, 'ALTERNATIVE'), (forms, 'REQUIRED')):
        for execution in request(base + '/flows/' + flow + '/executions', token=token):
            if flow == alias and execution.get('level', 0) != 0:
                continue
            request(base + '/flows/' + flow + '/executions', {'id': execution['id'], 'requirement': requirement}, token, method='PUT')
    return alias
