import Keycloak from 'keycloak-js';
import { startDashboard } from './dashboard';

const message = document.querySelector<HTMLParagraphElement>('#account-message')!;
const login = document.querySelector<HTMLButtonElement>('#header-login')!;
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
    document.querySelector('#registration-cancel')!.addEventListener('click',()=>document.querySelector<HTMLDialogElement>('#registration-choice')!.close());
    staffSignup.addEventListener('click',()=>{
      const choice=document.querySelector<HTMLDialogElement>('#registration-choice')!;choice.showModal();
    });
    document.querySelector<HTMLFormElement>('#registration-choice-form')!.addEventListener('submit',event=>{
      event.preventDefault();const kind=document.querySelector<HTMLSelectElement>('#registration-kind')!.value;
      if(!kind)return;sessionStorage.setItem('parking-registration-kind',kind);
      void identity.register({redirectUri:window.location.origin+'/'});
    });
    login.addEventListener('click', () => { void identity.login({ redirectUri: window.location.origin + '/' + (window.location.hash==='#staff-signup'?'#staff-signup':'') }); });
    logout.addEventListener('click', () => {
      stopDashboard();
      void api('/api/auth/logout', 'POST').then(() => {
        dialog.close(); open.hidden = true; vehicle.textContent = ''; logout.hidden = true;
        message.textContent = 'Signed out locally. Completing provider sign-out…';
        return identity.logout({ redirectUri: window.location.origin + '/' });
      })
        .catch(error => { message.textContent = String(error); });
    });
    if (!authenticated) { message.textContent = 'Drivers and employees: create an account and wait for approval. Administrators: sign in directly with your owner-provisioned account; no approval is needed. Email verification and password setup use local Mailpit.'; return; }
    login.hidden = true; logout.hidden = false;
    let me = await api('/api/me');
    staffSignup.hidden=true;
    document.querySelector<HTMLElement>('#product-intro')!.hidden=true;
    if(me.approvalStatus!=='approved') {
      const intent=sessionStorage.getItem('parking-registration-kind');
      if(!me.registrationKind && (intent==='driver' || intent==='employee')) {
        await api('/api/me/registration','POST',{kind:intent});sessionStorage.removeItem('parking-registration-kind');me=await api('/api/me');
      }
      for(const id of ['overview','location-section','preview-section'])document.getElementById(id)!.hidden=true;
      const account=document.querySelector<HTMLElement>('#account-section')!;account.hidden=false;
      document.querySelector('#account-title')!.textContent=me.approvalStatus==='rejected'?'Account request rejected':'Your approval is pending';
      message.textContent=me.approvalStatus==='rejected'?'Contact your administrator about this decision.':'Your account cannot access parking information until an administrator approves it.';
      open.hidden=true;vehicle.textContent='';document.querySelector('.sidebar nav')!.replaceChildren();
      document.querySelector('.topbar strong')!.textContent='Account approval';document.querySelector('.public-label')!.textContent='No parking access';
      if(!me.registrationKind) {
        const selection=document.createElement('form');selection.className='workspace-form';const label=document.createElement('label');label.textContent='Account type';
        const kind=document.createElement('select');kind.setAttribute('aria-label','Account type');kind.required=true;kind.append(new Option('Select account type',''),new Option('Driver / user','driver'),new Option('Employee','employee'));label.append(kind);
        const submit=document.createElement('button');submit.className='primary-button';submit.textContent='Submit for approval';selection.append(label,submit);account.append(selection);
        selection.addEventListener('submit',event=>{event.preventDefault();submit.disabled=true;void api('/api/me/registration','POST',{kind:kind.value}).then(()=>{selection.remove();message.textContent='Your registration has been submitted. Your approval is pending.';}).catch(error=>{message.textContent=String(error);submit.disabled=false;});});
      }
      const refresh=document.createElement('button');refresh.textContent='Check approval status';refresh.addEventListener('click',()=>{refresh.disabled=true;void api('/api/me').then(async profile=>{if(profile.approvalStatus==='approved'){refresh.remove();await activate(profile);}else{message.textContent=profile.approvalStatus==='rejected'?'Your request was rejected. Contact your administrator.':'Your approval is still pending.';refresh.disabled=false;}}).catch(error=>{message.textContent=String(error);refresh.disabled=false;});});account.append(refresh);
      refresh.className='secondary-button';
      return;
    }
    async function activate(profile:Record<string,unknown>):Promise<void> {
    me=profile;
    message.textContent = `Signed in as ${identity.tokenParsed?.email ?? 'your parking account'}.`;
    document.querySelector<HTMLElement>('.sidebar nav')!.hidden=false;
    document.querySelector('#account-title')!.textContent='Your account and vehicle';
    stopDashboard = startDashboard(api, me, async () => {await identity.updateToken(30);return identity.token!;});
    identity.onAuthLogout = () => {stopDashboard();dialog.close();open.hidden=true;vehicle.textContent='';message.textContent='Session ended. Sign in again.';login.hidden=false;};
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
    }
    await activate(me);
  } catch { message.textContent = 'Account service unavailable. Start the identity service and refresh to retry.'; }
}
void initialize();
