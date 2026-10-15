import Keycloak from 'keycloak-js';
import { startDashboard } from './dashboard';

const message = document.querySelector<HTMLParagraphElement>('#account-message')!;
const login = document.querySelector<HTMLButtonElement>('#account-login')!;
const headerLogin=document.querySelector<HTMLButtonElement>('#header-login')!;
headerLogin.addEventListener('click',()=>login.click());
const logout = document.querySelector<HTMLButtonElement>('#account-logout')!;
const staffSignup=document.querySelector<HTMLButtonElement>('#staff-signup')!;
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
      if (!response.ok) {
        const messages:Record<string,string>={
          vehicle_registration_already_in_use:'This registration and jurisdiction are already in use. Check both fields. If this is your vehicle, sign in to the account where it was registered or ask your administrator for help.',
          end_session_before_vehicle_change:'Your vehicle is currently parked. Ask staff to confirm checkout before replacing or disabling it.',
          staff_account_cannot_register_driver_vehicle:'This is an employee account. Use a separate driver account to register your vehicle.'
        };
        throw new Error(`${messages[String(result.error)] ?? String(result.error ?? 'Request failed').replaceAll('_',' ')} (${response.status})`);
      }
      return result;
    }
    login.disabled = false;
    staffSignup.disabled=false;
    staffSignup.addEventListener('click',()=>{void identity.register({redirectUri:window.location.origin+'/#staff-signup'});});
    headerLogin.disabled=false;
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
    if (!authenticated) { message.textContent = 'Sign in with email and password. New accounts verify email through local Mailpit. Staff registration requires administrator approval.'; return; }
    login.hidden = true; logout.hidden = false;
    headerLogin.hidden=true;
    const me = await api('/api/me');
    staffSignup.hidden=true;
    if(me.accountType==='driver') {
      const apply=document.createElement('button');apply.type='button';apply.className='secondary-button';apply.textContent='Request staff access (employees only)';
      apply.addEventListener('click',()=>{void (async()=>{
        const data=await api('/api/locations');
        const panel=document.createElement('form');panel.className='workspace-form';
        const heading=document.createElement('h3');heading.textContent='Request staff access';
        const label=document.createElement('label');label.textContent='Work location';const select=document.createElement('select');select.setAttribute('aria-label','Work location');
        for(const location of data.locations as Record<string,string>[])select.append(new Option(location.name,location.id));label.append(select);
        const reasonLabel=document.createElement('label');reasonLabel.textContent='Reason / employee details';const reason=document.createElement('input');reason.required=true;reason.maxLength=500;reasonLabel.append(reason);
        const submit=document.createElement('button');submit.type='submit';submit.textContent='Send staff access request';
        const warning=document.createElement('p');warning.textContent='For employees only. Existing parking customers with vehicle history must use a separate employee email. This request grants no permissions until administrator approval.';
        const feedback=document.createElement('p');feedback.setAttribute('role','status');panel.append(heading,warning,label,reasonLabel,submit,feedback);
        panel.addEventListener('submit',event=>{event.preventDefault();submit.disabled=true;void api('/api/me/staff-application','POST',{locationId:select.value,reason:reason.value}).then(()=>{
          feedback.textContent='Staff request saved. Ask your administrator to assign your location role, then sign out and sign in again.';apply.hidden=true;open.hidden=true;
        }).catch(error=>{feedback.textContent=String(error);submit.disabled=false;});});
        const application=document.createElement('dialog');application.setAttribute('aria-label','Request staff access');
        const close=document.createElement('button');close.type='button';close.textContent='Close';close.addEventListener('click',()=>application.close());
        application.append(panel,close);application.addEventListener('close',()=>application.remove());document.body.append(application);application.showModal();
      })().catch(error=>{message.textContent=String(error);});});
      document.querySelector('#account-section')!.append(apply);
      if(window.location.hash==='#staff-signup')setTimeout(()=>apply.click(),0);
    }
    message.textContent = `Signed in as ${identity.tokenParsed?.email ?? 'your parking account'}.`;
    stopDashboard = startDashboard(api, me, async () => {await identity.updateToken(30);return identity.token!;});
    identity.onAuthLogout = () => {stopDashboard();dialog.close();open.hidden=true;vehicle.textContent='';message.textContent='Session ended. Sign in again.';login.hidden=false;headerLogin.hidden=false;};
    showVehicle(await api('/api/me/vehicle'));
    open.hidden = me.accountType === 'staff';
    if(me.accountType==='staff')vehicle.textContent='Employee account. Driver vehicle registration uses a separate driver account.';
    form.addEventListener('submit', event => {
      event.preventDefault();
      const submit = form.querySelector<HTMLButtonElement>('button')!;
      submit.disabled = true;
      const data = Object.fromEntries(new FormData(form));
      void api('/api/me/vehicle', 'PUT', data).then(result => {
        showVehicle(result);
        dialog.close();
        message.textContent = `Signed in as ${identity.tokenParsed?.email ?? 'your parking account'}. Vehicle saved.`;
      }).catch(error => { feedback.textContent = String(error); }).finally(() => { submit.disabled = false; });
    });
  } catch { message.textContent = 'Account service unavailable. Start the identity service and refresh to retry.'; }
}
void initialize();
