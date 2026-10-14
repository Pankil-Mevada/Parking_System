import Keycloak from 'keycloak-js';

const message = document.querySelector<HTMLParagraphElement>('#account-message')!;
const login = document.querySelector<HTMLButtonElement>('#account-login')!;
const logout = document.querySelector<HTMLButtonElement>('#account-logout')!;
const form = document.querySelector<HTMLFormElement>('#vehicle-form')!;
const vehicle = document.querySelector<HTMLPreElement>('#account-vehicle')!;

async function initialize(): Promise<void> {
  try {
    const config = await fetch('/api/auth/config', { signal: AbortSignal.timeout(5000) });
    if (!config.ok) throw new Error('Authentication configuration unavailable');
    const identity = new Keycloak(await config.json());
    const authenticated = await identity.init({ onLoad: 'check-sso', pkceMethod: 'S256', checkLoginIframe: false });
    async function api(path: string, method = 'GET', body?: unknown): Promise<Record<string, unknown>> {
      await identity.updateToken(30);
      const response = await fetch(path, {
        method, signal: AbortSignal.timeout(10000),
        headers: { Authorization: `Bearer ${identity.token}`, 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(`${result.error ?? 'Request failed'} (${response.status})`);
      return result;
    }
    login.disabled = false;
    login.addEventListener('click', () => { void identity.login({ redirectUri: window.location.origin + '/' }); });
    logout.addEventListener('click', () => {
      void api('/api/auth/logout', 'POST').then(() => {
        form.hidden = true; vehicle.textContent = ''; logout.hidden = true;
        message.textContent = 'Signed out locally. Completing provider sign-out…';
        return identity.logout({ redirectUri: window.location.origin + '/' });
      })
        .catch(error => { message.textContent = String(error); });
    });
    if (!authenticated) { message.textContent = 'Sign in or register through the identity provider. Email verification and an authenticator app are required.'; return; }
    login.hidden = true; logout.hidden = false; form.hidden = false;
    const me = await api('/api/me');
    message.textContent = `Signed in. User ${me.id}. Staff permissions are assigned per location by an administrator.`;
    vehicle.textContent = JSON.stringify(await api('/api/me/vehicle'), null, 2);
    form.addEventListener('submit', event => {
      event.preventDefault();
      const submit = form.querySelector<HTMLButtonElement>('button')!;
      submit.disabled = true;
      const data = Object.fromEntries(new FormData(form));
      void api('/api/me/vehicle', 'PUT', data).then(result => {
        vehicle.textContent = JSON.stringify(result, null, 2);
        message.textContent = 'Vehicle saved by the server. An active parking session must end before changing it.';
      }).catch(error => { message.textContent = String(error); }).finally(() => { submit.disabled = false; });
    });
  } catch { message.textContent = 'Account service unavailable. Start the identity service and refresh to retry.'; }
}
void initialize();
