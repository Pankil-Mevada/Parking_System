import Keycloak from 'keycloak-js';
import { startDashboard } from './dashboard';

const message = document.querySelector<HTMLParagraphElement>('#account-message')!;
const login = document.querySelector<HTMLButtonElement>('#header-login')!;
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
    if (!authenticated) { message.textContent = 'Use Sign in / register in the header for every account. On the sign-in page, choose Register if you are new, or sign in with your existing email and password.'; return; }
    login.hidden = true; logout.hidden = false;
    let me = await api('/api/me');
    document.querySelector<HTMLElement>('#product-intro')!.hidden=true;
    if(me.approvalStatus!=='approved') {
      const intent=sessionStorage.getItem('parking-registration-kind');
      if(!me.registrationKind && (intent==='driver' || intent==='employee')) {
        await api('/api/me/registration','POST',{kind:intent});sessionStorage.removeItem('parking-registration-kind');me=await api('/api/me');
      }
      for(const id of ['overview','location-section','preview-section'])document.getElementById(id)!.hidden=true;
      const account=document.querySelector<HTMLElement>('#account-section')!;account.hidden=false;
      function showPending(profile:Record<string,unknown>):void {
        const title=document.querySelector('#account-title')!;
        if(profile.approvalStatus==='rejected') {
          title.textContent='Account request rejected';message.textContent='Your request was rejected. Contact your building administrator before trying again.';
        } else if(!profile.registrationKind) {
          title.textContent='Complete your account setup';message.textContent='Your account is registered. Choose the access you need below. Parking information stays private until your access is activated.';
        } else if(profile.registrationKind==='driver') {
          title.textContent='Waiting for driver approval';message.textContent='Your driver account is registered and waiting for your building administrator to approve it. After approval, you can manage your vehicle and view your parking status and history.';
        } else if(sessionStorage.getItem('parking-owner-setup-user')===String(profile.id)) {
          title.textContent='Administrator access not activated yet';message.textContent='Your account is registered. The system owner must activate your administrator access before you can manage this building. You do not need to register again. Use Check approval status after the owner completes setup.';
        } else {
          title.textContent='Waiting for staff access';message.textContent='Your employee account is registered. Your building administrator must approve it and assign your building and staff role. If you are the building owner awaiting administrator access, ask the system owner to complete administrator setup. You do not need to register again.';
        }
      }
      showPending(me);
      open.hidden=true;vehicle.textContent='';document.querySelector('.sidebar nav')!.replaceChildren();
      document.querySelector('.topbar strong')!.textContent='Account setup';document.querySelector('.public-label')!.textContent='No parking access';
      let selection:HTMLFormElement|undefined;
      if(!me.registrationKind && me.approvalStatus==='pending') {
        selection=document.createElement('form');selection.className='workspace-form';const label=document.createElement('label');label.textContent='Requested access';
        const kind=document.createElement('select');kind.setAttribute('aria-label','Requested access');kind.required=true;kind.append(new Option('Select access',''),new Option('Driver / user','driver'),new Option('Employee','employee'),new Option('Building owner / administrator','owner'));label.append(kind);
        const help=document.createElement('p');help.textContent='Choosing administrator does not grant a role. Only the system owner can activate administrator access.';
        const submit=document.createElement('button');submit.className='primary-button';submit.textContent='Submit access request';selection.append(label,help,submit);account.append(selection);
        selection.addEventListener('submit',event=>{event.preventDefault();submit.disabled=true;
          // Owner intent changes waiting copy only. Server registration remains
          // unprivileged employee; only trusted setup or authorized assignment grants roles.
          const requested=kind.value;const registrationKind=requested==='driver'?'driver':'employee';
          void api('/api/me/registration','POST',{kind:registrationKind}).then(()=>{
            if(requested==='owner')sessionStorage.setItem('parking-owner-setup-user',String(me.id));
            else sessionStorage.removeItem('parking-owner-setup-user');
            me={...me,registrationKind};selection?.remove();showPending(me);
          }).catch(error=>{message.textContent=String(error);submit.disabled=false;});});
      }
      const refresh=document.createElement('button');refresh.textContent='Check approval status';refresh.addEventListener('click',()=>{refresh.disabled=true;void api('/api/me').then(async profile=>{me=profile;if(profile.registrationKind)selection?.remove();if(profile.approvalStatus==='approved'){refresh.remove();await activate(profile);}else{showPending(profile);refresh.disabled=false;}}).catch(error=>{message.textContent=String(error);refresh.disabled=false;});});account.append(refresh);
      refresh.className='secondary-button';
      return;
    }
    async function activate(profile:Record<string,unknown>):Promise<void> {
    me=profile;
    sessionStorage.removeItem('parking-owner-setup-user');
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
