import Keycloak from 'keycloak-js';
import { startDashboard } from './dashboard';

const message = document.querySelector<HTMLParagraphElement>('#account-message')!;
const login = document.querySelector<HTMLButtonElement>('#account-login')!;
const logout = document.querySelector<HTMLButtonElement>('#account-logout')!;
const form = document.querySelector<HTMLFormElement>('#vehicle-form')!;
const vehicle = document.querySelector<HTMLDivElement>('#account-vehicle')!;
const dialog = document.querySelector<HTMLDialogElement>('#vehicle-dialog')!;
const open = document.querySelector<HTMLButtonElement>('#vehicle-open')!;
const feedback = document.querySelector<HTMLParagraphElement>('#vehicle-feedback')!;
document.querySelector('#overview')!.after(document.querySelector('#account-section')!);
open.addEventListener('click', () => { feedback.textContent = ''; dialog.showModal(); });
document.querySelector('#vehicle-close')!.addEventListener('click', () => dialog.close());
function showVehicle(result: Record<string, unknown>): void {
  const saved = result.vehicle as Record<string, unknown> | null;
  vehicle.textContent = saved
    ? `${saved.normalized_registration} · ${saved.registration_jurisdiction} · ${saved.vehicle_type} — ${[saved.make, saved.model, saved.color].filter(Boolean).join(' / ') || 'No optional details added'}`
    : 'No vehicle registered yet. Add your vehicle to prepare for staff check-in.';
  open.textContent = saved ? 'Manage vehicle' : 'Register your vehicle';
  const fields: Record<string, string> = {registrationJurisdiction:'registration_jurisdiction',registration:'normalized_registration',vehicleType:'vehicle_type',make:'make',model:'model',color:'color'};
  for (const [name, key] of Object.entries(fields)) {
    const input = form.elements.namedItem(name) as HTMLInputElement | HTMLSelectElement;
    input.value = saved ? String(saved[key] ?? '') : name === 'vehicleType' ? 'car' : '';
  }
}

async function initialize(): Promise<void> {
  try {
    const config = await fetch('/api/auth/config', { signal: AbortSignal.timeout(5000) });
    if (!config.ok) throw new Error('Authentication configuration unavailable');
    const identity = new Keycloak(await config.json());
    const authenticated = await identity.init({ onLoad: 'check-sso', pkceMethod: 'S256', checkLoginIframe: false });
    let stopDashboard = () => {};
    async function api(path: string, method = 'GET', body?: unknown, key?: string): Promise<Record<string, unknown>> {
      await identity.updateToken(30);
      const response = await fetch(path, {
        method, signal: AbortSignal.timeout(10000),
        headers: { Authorization: `Bearer ${identity.token}`, 'Content-Type': 'application/json', ...(key ? {'Idempotency-Key':key} : {}) },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const result = await response.json();
      if(response.status===401) identity.clearToken();
      if (!response.ok) throw new Error(`${String(result.error ?? 'Request failed').replaceAll('_',' ')} (${response.status})`);
      return result;
    }
    login.disabled = false;
    login.addEventListener('click', () => { void identity.login({ redirectUri: window.location.origin + '/' }); });
    logout.addEventListener('click', () => {
      stopDashboard();
      void api('/api/auth/logout', 'POST').then(() => {
        dialog.close(); open.hidden = true; vehicle.textContent = ''; logout.hidden = true;
        message.textContent = 'Signed out locally. Completing provider sign-out…';
        return identity.logout({ redirectUri: window.location.origin + '/' });
      })
        .catch(error => { message.textContent = String(error); });
    });
    if (!authenticated) { message.textContent = 'Sign in or register through the identity provider. Email verification and an authenticator app are required.'; return; }
    login.hidden = true; logout.hidden = false;
    const me = await api('/api/me');
    message.textContent = 'Signed in. Your vehicle details are saved securely to your account. Staff access is assigned by an administrator.';
    stopDashboard = startDashboard(api, me, async () => {await identity.updateToken(30);return identity.token!;});
    identity.onAuthLogout = () => {stopDashboard();dialog.close();open.hidden=true;vehicle.textContent='';message.textContent='Session ended. Sign in again.';login.hidden=false;};
    showVehicle(await api('/api/me/vehicle'));
    open.hidden = false;
    form.addEventListener('submit', event => {
      event.preventDefault();
      const submit = form.querySelector<HTMLButtonElement>('button')!;
      submit.disabled = true;
      const data = Object.fromEntries(new FormData(form));
      void api('/api/me/vehicle', 'PUT', data).then(result => {
        showVehicle(result);
        dialog.close();
        message.textContent = 'Vehicle saved. You are ready for authorized staff to check you in. No parking session has started.';
      }).catch(error => { feedback.textContent = String(error); }).finally(() => { submit.disabled = false; });
    });
  } catch { message.textContent = 'Account service unavailable. Start the identity service and refresh to retry.'; }
}
void initialize();
