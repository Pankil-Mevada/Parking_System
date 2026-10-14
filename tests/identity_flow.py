"""Exercise real Keycloak authorization-code + PKCE + OTP, not a mock issuer."""
import base64
import hashlib
import hmac
from html.parser import HTMLParser
import http.cookiejar
import json
import secrets
import struct
import time
import urllib.parse
import urllib.request
import urllib.error
from identity_admin import IDENTITY, admin_token, request

REALM = 'parking-tests'


class Form(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms = []
        self.current = None
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if tag == 'form':
            self.current = {'action': attrs.get('action', ''), 'fields': {}}
            self.forms.append(self.current)
        elif tag in ('input', 'button') and self.current is not None and 'name' in attrs:
            self.current['fields'][attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.current = None


def otp(secret):
    # Test fixture only. Keycloak performs actual OTP verification.
    digest = hmac.new(secret.encode(), struct.pack('>Q', int(time.time()) // 30), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f'{(struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000:06d}'


def create_user(name, verified=True):
    password = secrets.token_urlsafe(24)
    secret = secrets.token_urlsafe(20)
    value = {'username': name, 'email': name + '@example.test', 'firstName': 'Synthetic',
             'lastName': 'Test', 'enabled': True, 'emailVerified': verified,
             'credentials': [
                 {'type': 'password', 'value': password, 'temporary': False},
                 {'type': 'otp', 'secretData': json.dumps({'value': secret}),
                  'credentialData': json.dumps({'subType': 'totp', 'digits': 6, 'period': 30, 'algorithm': 'HmacSHA1', 'counter': 0})},
             ]}
    token = admin_token()
    request(IDENTITY + '/admin/realms/' + REALM + '/users', value, token)
    users = request(IDENTITY + '/admin/realms/' + REALM + '/users?email=' + urllib.parse.quote(name + '@example.test') + '&exact=true', token=token)
    return {'id': users[0]['id'], 'username': users[0]['username'], 'password': password, 'secret': secret}


def login(user, invalid_otp=False):
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    redirect = 'http://127.0.0.1:5173/'
    url = IDENTITY + '/realms/' + REALM + '/protocol/openid-connect/auth?' + urllib.parse.urlencode({
        'client_id': 'parking-web', 'response_type': 'code', 'scope': 'openid email profile',
        'redirect_uri': redirect, 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
    })
    # Capture the callback without depending on the frontend development server.
    class StopCallback(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if newurl.startswith(redirect):
                return None
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    class LoopbackCookiePolicy(http.cookiejar.DefaultCookiePolicy):
        def return_ok_secure(self, cookie, req):
            # Match browsers' secure-context treatment of loopback HTTP. This
            # exception is only for this isolated local provider test client.
            if req.full_url.startswith(IDENTITY + '/'):
                return True
            return super().return_ok_secure(cookie, req)
    browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar(LoopbackCookiePolicy())), StopCallback())
    response = browser.open(url, timeout=15)
    html = response.read().decode()
    for _ in range(4):
        forms = Form(html).forms
        form = next((item for item in forms if any(key in item['fields'] for key in ('username', 'otp'))), None)
        if form is None:
            raise AssertionError('Expected login/OTP form; authentication did not complete')
        values = form['fields']
        if 'username' in values:
            values.update(username=user['username'], password=user['password'])
            values.pop('rememberMe', None)
        else:
            values['otp'] = 'invalid' if invalid_otp else otp(user['secret'])
        try:
            response = browser.open(urllib.request.Request(form['action'], urllib.parse.urlencode(values).encode()), timeout=15)
            html = response.read().decode()
        except urllib.error.HTTPError as error:
            if error.code not in (302, 303):
                import re
                content = error.read().decode()
                feedback = re.findall(r'<span[^>]*class="kc-feedback-text"[^>]*>(.*?)</span>', content, re.S)
                error.close()
                raise AssertionError('Provider login rejected: ' + str(feedback)) from None
            callback = urllib.parse.parse_qs(urllib.parse.urlparse(error.headers['Location']).query)
            error.close()
            if callback.get('state') != [state] or 'code' not in callback:
                raise AssertionError('Invalid authorization callback') from None
            return request(IDENTITY + '/realms/' + REALM + '/protocol/openid-connect/token', {
                'grant_type': 'authorization_code', 'client_id': 'parking-web',
                'redirect_uri': redirect, 'code': callback['code'][0], 'code_verifier': verifier,
            }, form=True)
        if invalid_otp and 'otp' in values:
            raise AssertionError('OTP rejected as expected')
    raise AssertionError('Login did not produce an authorization code')


def captured_action_link(user):
    messages = request('http://127.0.0.1:8025/api/v1/messages')['messages']
    message = next(item for item in messages if any(address['Address'] == user['username'] for address in item['To']))
    content = request('http://127.0.0.1:8025/api/v1/message/' + message['ID'])
    return next(link for link in Form(content['HTML']).links if '/login-actions/action-token?' in link)


def safe_page_text(html):
    import re
    body=html.split('<body',1)[-1]
    body=re.sub(r'<script.*?</script>', '', body, flags=re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>',' ',body))[:500]


def recovery(user):
    class Policy(http.cookiejar.DefaultCookiePolicy):
        def return_ok_secure(self, cookie, req):
            return req.full_url.startswith(IDENTITY + '/') or super().return_ok_secure(cookie, req)
    browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar(Policy())))
    url = IDENTITY + '/realms/parking-tests/protocol/openid-connect/auth?' + urllib.parse.urlencode({
        'client_id':'parking-web','response_type':'code','scope':'openid email profile',
        'redirect_uri':'http://127.0.0.1:5173/','state':secrets.token_urlsafe(24),
        'code_challenge':secrets.token_urlsafe(32),'code_challenge_method':'S256'})
    with browser.open(url,timeout=10) as response:
        page=Form(response.read().decode())
    reset=next(link for link in page.links if '/login-actions/reset-credentials?' in link)
    with browser.open(urllib.parse.urljoin(IDENTITY,reset),timeout=10) as response:
        form=next(item for item in Form(response.read().decode()).forms if 'username' in item['fields'])
    form['fields']['username']=user['username']
    with browser.open(urllib.request.Request(form['action'],urllib.parse.urlencode(form['fields']).encode()),timeout=10) as response:
        response.read()
    link=captured_action_link(user)
    with browser.open(link,timeout=10) as response:
        html=response.read().decode()
        matches=[item for item in Form(html).forms if 'password-new' in item['fields']]
        if not matches:
            raise AssertionError('Recovery page: '+safe_page_text(html)+'; forms='+str([sorted(item['fields']) for item in Form(html).forms]))
        form=matches[0]
    new_password=secrets.token_urlsafe(24)
    form['fields'].update({'password-new':new_password,'password-confirm':new_password})
    with browser.open(urllib.request.Request(form['action'],urllib.parse.urlencode(form['fields']).encode()),timeout=10) as response:
        response.read()
    changed=dict(user,password=new_password)
    return changed,link


def verify_email(user):
    class Policy(http.cookiejar.DefaultCookiePolicy):
        def return_ok_secure(self, cookie, req):
            return req.full_url.startswith(IDENTITY + '/') or super().return_ok_secure(cookie, req)
    browser=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar(Policy())))
    link=captured_action_link(user)
    with browser.open(link,timeout=10) as response:
        html=response.read().decode()
    # A fresh browser must confirm that it intends to verify this account.
    for _ in range(2):
        forms=Form(html).forms
        links=Form(html).links
        confirmation=next((item for item in forms if 'username' not in item['fields'] and item['action']),None)
        if confirmation:
            with browser.open(urllib.request.Request(urllib.parse.urljoin(IDENTITY,confirmation['action']),urllib.parse.urlencode(confirmation['fields']).encode()),timeout=10) as response:
                html=response.read().decode()
        else:
            action=next((value for value in links if '/login-actions/' in value),None)
            if action is None:
                break
            with browser.open(urllib.parse.urljoin(IDENTITY,action),timeout=10) as response:
                html=response.read().decode()
    return safe_page_text(html)
