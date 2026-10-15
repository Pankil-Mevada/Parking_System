import {changedResources, type Change} from './realtime';
export type Api = (path: string, method?: string, body?: unknown, key?: string) => Promise<Record<string, unknown>>;
type Row = Record<string, string | null>;
type Assignment = {locationId: string; role: string};
type Snapshot = {cursor: string; timestamp: string; floors: Row[]; spaces?: Row[]; unassigned: {total: string}};
const section = document.createElement('section');
section.id = 'parking-workspace';section.className = 'parking-workspace'; section.hidden = true;
document.querySelector('#account-section')!.after(section);
function node<K extends keyof HTMLElementTagNameMap>(tag: K, text = '', className = ''): HTMLElementTagNameMap[K] {
  const value = document.createElement(tag); value.textContent = text; value.className = className; return value;
}
function button(text: string, action: () => void, kind = 'secondary-button'): HTMLButtonElement {
  const item = node('button', text, kind); item.type = 'button'; item.addEventListener('click', action); return item;
}
function table(rows: Row[], columns: [string, string][]): HTMLElement {
  const wrap = node('div', '', 'table-scroll'); const view = node('table');
  const head = node('thead'); const tr = node('tr');
  for (const [, title] of columns) { const th = node('th', title); th.scope = 'col'; tr.append(th); }
  head.append(tr); view.append(head); const body = node('tbody');
  for (const row of rows) { const line = node('tr'); for (const [key] of columns) line.append(node('td', row[key] ?? '—')); body.append(line); }
  view.append(body); wrap.append(view); if (!rows.length) wrap.append(node('p', 'No records found.')); return wrap;
}
function date(value: string | null): string {return value ? new Date(value).toLocaleString() : '—';}
export function startDashboard(api: Api, me: Record<string, unknown>, getToken: () => Promise<string>): () => void {
  document.querySelector('#account-section')!.after(section);
  let stopped = false, setupPending = false, epoch = 0, cursor = '0', offset = 0, historyOffset = 0, timer: ReturnType<typeof setTimeout>;
  let failures = 0, lastSuccess = 0, scope = 'locations', snapshot: Snapshot | undefined, subscription = 0;
  let streamController: AbortController | undefined;
  const assignments = me.assignments as Assignment[];
  const keys = new Map<string, string>();
  const versions = new Map<string, bigint>();
  const title = node('h1', 'My dashboard');
  const description = node('p', '', 'role-description');
  const badge = node('span', 'Driver workspace', 'role-badge');
  const navigation = document.querySelector<HTMLElement>('.sidebar nav')!;
  const publicNavigation = [...navigation.childNodes];
  const publicSections = ['overview','location-section','preview-section'].map(id=>document.getElementById(id)!);
  const account = document.getElementById('account-section')!;
  const accountMessage=document.getElementById('account-message')!;
  const signout=document.getElementById('account-logout')!;
  const accountStrip=node('div','','workspace-account');accountStrip.append(accountMessage,signout);
  let activeView='dashboard',navigationKey='';
  const views: Record<string,[string,string,string][]> = {
    driver:[['dashboard','My dashboard','Your current parking session and the next step.'],['availability','Find parking','Choose a location and compare available spaces by floor.'],['vehicle','My vehicle','Register or replace the one vehicle linked to your account.'],['history','My parking history','Review your own arrivals and departures.']],
    attendant:[['occupancy','Space occupancy','View parking spaces and location availability.'],['drivers','Driver accounts & vehicles','Create driver accounts and register or manage their vehicles.'],['checkin','Check in a vehicle','Find a registered vehicle and confirm its physical arrival.'],['checkout','Check out a vehicle','Select an occupied space and confirm departure.']],
    operator_admin:[['approvals','Account approvals','Approve driver and employee registration requests.'],['overview','Location overview','Monitor capacity and occupancy at this location.'],['spaces','Floors & spaces','Configure floors, numbered spaces, compatibility and maintenance.'],['locations','Location settings','Edit this location or create another location.'],['drivers','Drivers','Find driver accounts and manage their vehicles. Drivers cannot be assigned staff roles.'],['people','Staff accounts','Approve separate employee accounts and assign their location roles.'],['audit','Audit records','Search recorded actions at this location.'],['operations','Check-in / check-out','Perform authorized staff parking operations.']],
  };
  const controls = node('div', '', 'workspace-controls');
  const location = node('select'); location.setAttribute('aria-label', 'Parking location');
  const role = node('select'); role.setAttribute('aria-label', 'Switch workspace');
  const floor = node('select'); floor.setAttribute('aria-label', 'Floor filter');
  const search = node('input'); search.placeholder = 'Search this page: space, plate, owner'; search.setAttribute('aria-label', 'Search current space page');
  const status = node('p', 'Loading your dashboard…', 'workspace-status'); status.setAttribute('role', 'status');
  const floors = node('div', '', 'floor-grid'), spaces = node('div', '', 'space-grid');
  const session = node('div', '', 'session-panel'), history = node('div'), admin = node('div', '', 'admin-panel');
  const staff = node('div', '', 'staff-panel');
  const pages = node('div', '', 'workspace-controls');
  const previous = button('Previous spaces', () => {offset = Math.max(0, offset - 100); void refresh();});
  const next = button('Next spaces', () => {offset += 100; void refresh();}); pages.append(previous, next);
  const filters=node('div','','workspace-controls space-filters');filters.append(floor,search);
  function labeled(text:string,field:HTMLElement):HTMLLabelElement {const label=node('label',text);label.append(field);return label;}
  controls.append(labeled('Parking location',location),labeled('Switch workspace',role),button('Refresh now', () => {void loadLocations().catch(fail);}));
  section.replaceChildren(badge,title,description,accountStrip,controls,status,filters,floors,session,staff,spaces,pages,history,admin,account); section.hidden = false;
  for(const panel of publicSections)panel.hidden=true;
  document.body.classList.add('authenticated-workspace');
  const topbarTitle=document.querySelector<HTMLElement>('.topbar strong')!;
  const publicLabel=document.querySelector<HTMLElement>('.public-label')!;
  function applyView():void {
    for(const label of controls.querySelectorAll('label'))label.hidden=setupPending;
    if(setupPending) {
      badge.textContent='Pending staff approval';title.textContent='Waiting for administrator approval';
      description.textContent='Your employee account is registered. An administrator must approve and assign your location access before you can work.';
      topbarTitle.textContent='Pending approval';publicLabel.textContent='Pending staff approval';
      for(const panel of [account,session,history,floors,spaces,pages,filters,staff,admin])panel.hidden=true;
      navigation.replaceChildren(node('span','Pending approval','nav-item active'));
      navigationKey='pending';return;
    }
    const workspace=role.value || 'driver';
    const available=views[workspace] ?? views.driver;
    if(!available.some(([key])=>key===activeView))activeView=available[0][0];
    const selected=available.find(([key])=>key===activeView)!;
    const roleName=workspace==='operator_admin'?'Administrator':workspace==='attendant'?'Staff':'Driver';
    section.dataset.role=workspace;badge.textContent=`${roleName} workspace`;title.textContent=selected[1];description.textContent=selected[2];
    topbarTitle.textContent=selected[1];publicLabel.textContent=`${roleName} workspace`;
    account.hidden=activeView!=='vehicle';session.hidden=activeView!=='dashboard';history.hidden=activeView!=='history';
    floors.hidden=!['availability','occupancy','overview','spaces'].includes(activeView);
    const showSpaces=['occupancy','checkout','spaces','operations'].includes(activeView) && workspace!=='driver';
    spaces.hidden=pages.hidden=!showSpaces;filters.hidden=!showSpaces;
    staff.hidden=!['checkin','operations','drivers'].includes(activeView) || workspace==='driver';
    if(activeView==='drivers' && workspace!=='attendant')staff.hidden=true;
    for(const child of staff.children)if(child instanceof HTMLElement)child.hidden=child.dataset.view!==activeView && !(activeView==='operations' && child.dataset.view==='checkin');
    admin.hidden=workspace!=='operator_admin' || !['approvals','locations','spaces','people','drivers','audit'].includes(activeView);
    for(const child of admin.children) {
      if(child instanceof HTMLElement)child.hidden=child.dataset.view!==activeView;
    }
    if(navigationKey===`${workspace}/${activeView}`)return;
    navigationKey=`${workspace}/${activeView}`;navigation.replaceChildren();
    for(const [key,label] of available) {
      const link=node('a',label,'nav-item'+(key===activeView?' active':''));link.href=`#workspace/${workspace}/${key}`;
      if(key===activeView)link.setAttribute('aria-current','page');
      link.addEventListener('click',event=>{event.preventDefault();navigate(key);});navigation.append(link);
    }
    const security=node('a','Account security','nav-item');security.href='http://127.0.0.1:8180/realms/parking/account/#/security/signingin';security.target='_blank';security.rel='noopener';navigation.append(security);
  }
  function navigate(view:string,replace=false):void {
    activeView=view;applyView();renderSpaces();
    window.history[replace?'replaceState':'pushState'](null,'',`#workspace/${role.value}/${activeView}`);
    title.tabIndex=-1;title.focus({preventScroll:true});section.scrollIntoView({block:'start'});
  }
  function restoreRoute():void {
    const parts=window.location.hash.split('/');
    if(parts[0]==='#workspace' && parts[1]!==role.value && [...role.options].some(option=>option.value===parts[1])) {
      role.value=parts[1];void changed().catch(fail);return;
    }
    if(parts[0]==='#workspace' && parts[1]===role.value) {activeView=parts[2] ?? '';applyView();renderSpaces();}
  }
  window.addEventListener('popstate',restoreRoute);
  function fail(error: unknown): void {status.textContent = `Could not complete request: ${String(error)}. Displayed data may be stale.`;}
  async function mutate(path: string, method: string, body: unknown, idempotent = false): Promise<Record<string, unknown>> {
    const operation = path + JSON.stringify(body);
    let key = keys.get(operation); if (!key) { key = crypto.randomUUID(); keys.set(operation, key); }
    const result = await api(path, method, body, idempotent ? key : undefined);
    if(result.setupEmailSent!==false)keys.delete(operation); return result;
  }
  function form(title: string, fields: [string, string, string, string?][], submit: (body: Record<string, string>) => Promise<void>): HTMLFormElement {
    const view = node('form', '', 'workspace-form'); view.append(node('h3', title));
    for (const [name, label, placeholder, value] of fields) {
      const field = node('label', label);
      const choices: Record<string,string[][]> = {role:[['attendant','Attendant'],['operator_admin','Operator administrator'],['none','Remove assignment']],status:[['enabled','Enabled'],['disabled','Disabled']],vehicleType:[['car','Car'],['motorcycle','Motorcycle'],['van','Van']]};
      if(choices[name]) {
        const select=node('select');select.name=name;select.required=true;
        for(const [key,text] of choices[name])select.append(new Option(text,key));
        if(value)select.value=value;field.append(select);
      } else {
        const input = node('input'); input.name = name; input.placeholder = placeholder; input.required = true; input.maxLength = name === 'reason' ? 500 : 200; input.value = value ?? ''; field.append(input);
      }
      view.append(field);
    }
    const save = node('button', 'Save', 'primary-button'); save.type = 'submit'; view.append(save);
    const feedback = node('p'); feedback.setAttribute('role', 'status'); view.append(feedback);
    view.addEventListener('submit', event => {
      event.preventDefault(); save.disabled = true; feedback.textContent = 'Waiting for server confirmation…';
      void submit(Object.fromEntries(new FormData(view)) as Record<string, string>).then(() => {
        if (!stopped) feedback.textContent = 'Saved by the server.';
      }).catch(error => {feedback.textContent = String(error);}).finally(() => {save.disabled = false;});
    }); return view;
  }
  async function confirmAction(text: string, action: () => Promise<void>): Promise<void> {
    const dialog = node('dialog'); dialog.setAttribute('aria-label', 'Confirm parking action');
    const feedback = node('p'); feedback.setAttribute('role', 'status');
    const commit = button('Confirm', () => {
      commit.disabled = true; feedback.textContent = 'Waiting for server…';
      void action().then(() => dialog.close()).catch(error => {feedback.textContent = String(error);}).finally(() => {commit.disabled = false;});
    }, 'primary-button');
    dialog.append(node('h2', 'Confirm action'), node('p', text), feedback, commit, button('Cancel', () => dialog.close()));
    dialog.addEventListener('close', () => dialog.remove()); section.append(dialog); dialog.showModal();
  }
  function renderSpaces(): void {
    spaces.replaceChildren();
    if (!snapshot?.spaces) return;
    const matching = snapshot.spaces.filter(item => (activeView!=='checkout' || Boolean(item.session_id)) && (floor.value === 'all' || (item.zone_id ?? 'unassigned') === floor.value)
      && [item.label, item.registration_snapshot, item.display_name, item.email].some(value => (value ?? '').toLowerCase().includes(search.value.toLowerCase())));
    for (const item of matching) {
      const occupied = Boolean(item.session_id), maintenance = item.operational_status !== 'enabled';
      const card = node('article', '', `space-card ${occupied ? 'occupied' : maintenance ? 'maintenance' : 'empty'}`);
      const floorName = snapshot.floors.find(f => f.id === item.zone_id)?.label ?? 'Unassigned floor';
      card.append(node('h3', `${floorName} · ${item.label}`), node('strong', occupied ? '● Occupied' : maintenance ? '⊘ Out of service' : '○ Empty'), node('p', `Compatible: ${item.supported_vehicle_type}`));
      if (occupied) {
        card.append(node('p', `${item.registration_snapshot} · ${item.vehicle_type ?? ''} · ${item.color ?? ''}`), node('p', `${item.display_name ?? ''} · ${item.email ?? ''}`), node('p', `Arrival: ${date(item.checked_in_at)}`));
        if(role.value==='attendant' || activeView==='operations')card.append(button('Check out', () => {void confirmAction(`Confirm departure of ${item.registration_snapshot} from ${item.label}?`, async () => {
          await mutate(`/api/staff/sessions/${item.session_id}/check-out`, 'POST', {}, true); await refresh();
        });}));
      }
      if (role.value === 'operator_admin' && activeView==='spaces' && !occupied) card.append(button(maintenance ? 'Restore space' : 'Mark out of service', () => {
        const dialog = node('dialog'); dialog.setAttribute('aria-label', 'Space maintenance reason');
        dialog.append(form('Space maintenance', [['reason', 'Reason', 'Explain the maintenance change']], async body => {
          await mutate(`/api/admin/spaces/${item.id}/status`, 'PUT', {status: maintenance ? 'enabled' : 'out_of_service', reason: body.reason}); dialog.close(); await refresh();
        }), button('Cancel', () => dialog.close())); dialog.addEventListener('close', () => dialog.remove()); section.append(dialog); dialog.showModal();
      }));
      if (role.value === 'operator_admin' && activeView==='spaces' && !occupied) card.append(button('Edit space', () => {
        const dialog = node('dialog'); dialog.setAttribute('aria-label','Edit numbered space');
        dialog.append(form('Edit space', [['label','Space label','F1-01',item.label!],['vehicleType','Compatible type: car, motorcycle, van','car',item.supported_vehicle_type!],['reason','Reason','Explain the change']],async body=>{
          const zone = dialog.querySelector<HTMLSelectElement>('select')!;
          await mutate(`/api/admin/locations/${location.value}/spaces`,'PUT',{...body,id:item.id,zoneId:zone.value});dialog.close();await refresh();
        }),button('Cancel',()=>dialog.close()));
        const label = node('label','Floor / zone'), select=node('select');select.required=true;
        for(const row of snapshot?.floors ?? []) select.append(new Option(row.label!,row.id!));
        select.value=item.zone_id ?? ''; label.append(select);dialog.querySelector('form')!.prepend(label);
        dialog.addEventListener('close',()=>dialog.remove());section.append(dialog);dialog.showModal();
      }));
      spaces.append(card);
    }
    if (!matching.length) spaces.append(node('p', 'No spaces match this page and floor filter.'));
    previous.disabled = offset === 0; next.disabled = snapshot.spaces.length < 100;
  }
  async function driver(): Promise<void> {
    const data = await api(`/api/me/dashboard?offset=${historyOffset}`); if (stopped) return;
    const current = data.current as Row | null;
    session.replaceChildren(node('h3', 'Your current parking session'));
    if (current) {
      const arrival = new Date(current.checked_in_at!).getTime();
      session.append(node('p', `${current.location} · ${current.floor ?? 'Unassigned floor'} · Space ${current.space}`), node('p', `${current.registration_snapshot} · Arrived ${date(current.checked_in_at)}`), node('p', `Elapsed: ${Math.max(0, Math.floor((Date.now() - arrival) / 60000))} minutes`));
    } else session.append(node('p', 'You are not currently parked. Authorized staff must confirm your arrival.'));
    const records = (data.history as Row[]).map(row => ({...row, checked_in_at: date(row.checked_in_at), checked_out_at: row.checked_out_at ? date(row.checked_out_at) : 'Active'}));
    const prev = button('Previous history', () => {historyOffset = Math.max(0, historyOffset - 50); void driver().catch(fail);}); prev.disabled = historyOffset === 0;
    const more = button('Next history', () => {historyOffset += 50; void driver().catch(fail);}); more.disabled = records.length < 50;
    history.replaceChildren(node('h3', 'Your parking history'), table(records, [['location','Location'],['floor','Floor'],['space','Space'],['registration_snapshot','Vehicle'],['checked_in_at','Arrival'],['checked_out_at','Departure']]), prev, more);
    applyView();
  }
  async function refresh(): Promise<void> {
    const generation = ++epoch;
    if (!location.value || stopped || setupPending) return;
    status.textContent = 'Loading confirmed parking records…';
    try {
      const data = await api(`/api/${scope}/${location.value}/dashboard?offset=${offset}`) as unknown as Snapshot;
      if (stopped || generation !== epoch) return;
      snapshot = data; cursor = data.cursor; lastSuccess = Date.now();
      for (const space of data.spaces ?? []) if(space.id && space.version) versions.set(space.id,BigInt(space.version));
      const selected = floor.value; floor.replaceChildren(new Option('All floors', 'all'));
      floors.replaceChildren(node('h3', `${data.floors.length} floors / zones`));
      for (const item of data.floors) {
        floor.append(new Option(item.label!, item.id!));
        const card = node('article', '', 'floor-card');
        card.append(node('h3', item.label!), node('p', `${item.available} available · ${item.occupied} occupied`), node('p', `${item.out_of_service} out of service · ${item.capacity} operational`)); floors.append(card);
      }
      if (Number(data.unassigned.total)) {floor.append(new Option('Unassigned floor', 'unassigned')); floors.append(node('p', `${data.unassigned.total} spaces have no assigned floor.`));}
      if ([...floor.options].some(item => item.value === selected)) floor.value = selected;
      spaces.hidden = pages.hidden = staff.hidden = scope === 'locations';
      renderSpaces(); await driver();
      applyView();
      status.textContent = `Confirmed snapshot · Updated ${date(data.timestamp)}. Connecting for changes…`;
      window.dispatchEvent(new Event('parking-updated'));
    } catch (error) {
      if (generation === epoch && !stopped) {
        // Remove sensitive detail on any failed authorization or unavailable server.
        spaces.replaceChildren(); staff.hidden = true; admin.replaceChildren(); session.replaceChildren(); history.replaceChildren(); snapshot = undefined;
        fail(error);
      }
    }
  }
  async function connect(ticket = subscription): Promise<void> {
    if (stopped || ticket !== subscription) return;
    const selectedLocation = location.value, selectedScope = scope;
    try {
      streamController = new AbortController(); const timeout = setTimeout(() => streamController?.abort(), 5000);
      let response: Response;
      try {response = await fetch(`/api/${selectedScope}/${selectedLocation}/events?after=${cursor}`, {headers: {Authorization: `Bearer ${await getToken()}`}, signal: streamController.signal, cache: 'no-store'});} finally {clearTimeout(timeout);}
      if(response.status===401) await api('/api/me');
      if (!response.ok) throw new Error(`Event authorization / delivery failed (${response.status})`);
      const body = await response.text();
      if (stopped || ticket !== subscription || selectedLocation !== location.value || selectedScope !== scope) return;
      const payload = body.split('\n').find(line => line.startsWith('data: ')); if (!payload) throw new Error('Missing heartbeat');
      const data = JSON.parse(payload.slice(6)) as {cursor: string; reset: boolean; events: Change[]};
      if (!/^\d{1,18}$/.test(data.cursor)) throw new Error('Invalid replay cursor');
      // The SSE batch has monotonic delivery IDs. Duplicate and older batches do
      // not overwrite a newer snapshot. Refresh always reads authoritative state.
      const recovering=failures>0;
      if (recovering || !snapshot || data.reset || (BigInt(data.cursor) >= BigInt(cursor) && changedResources(data.events,cursor,versions))) await refresh();
      if(recovering && snapshot){await buildStaff();await buildAdmin();}
      if (BigInt(data.cursor) >= BigInt(cursor)) cursor = data.cursor;
      if(!snapshot) throw new Error('Snapshot unavailable');
      failures = 0; status.textContent = `Connected · Last confirmed snapshot ${date(snapshot.timestamp)}`;
      // Periodic snapshot also covers floor/name/role changes that have no space event yet.
      if (Date.now() - lastSuccess > 15000) await refresh();
    } catch {
      if (!stopped && ticket === subscription) {
        failures++; status.textContent = 'Disconnected / stale · Reconnecting with backoff. Snapshot fallback runs every 15 seconds.';
        spaces.replaceChildren(); admin.replaceChildren(); session.replaceChildren();history.replaceChildren();staff.hidden = true;
        section.querySelectorAll('dialog').forEach(dialog=>dialog.close());
        if (Date.now() - lastSuccess > 15000) await refresh();
      }
    } finally {if (!stopped && ticket === subscription) timer = setTimeout(() => {void connect(ticket);}, Math.min(15000, 1000 * 2 ** Math.min(failures, 4)));}
  }
  async function buildStaff(): Promise<void> {
    staff.replaceChildren(); if (scope === 'locations') return;
    const ticket = subscription, selectedLocation = location.value;
    const lookup = form('Check in a registered vehicle', [['jurisdiction','Registration jurisdiction','e.g. IN-GJ'],['registration','Exact vehicle registration','e.g. GJ 01 AB 1234']], async body => {
      const data = await api(`/api/staff/locations/${selectedLocation}/vehicles?jurisdiction=${encodeURIComponent(body.jurisdiction)}&registration=${encodeURIComponent(body.registration)}`);
      if (stopped || ticket !== subscription) return;
      const vehicles = data.vehicles as Row[]; const result = node('div');
      if (!vehicles.length) result.append(node('p', 'No enabled vehicle matches. Ask the driver to register it first.'));
      for (const vehicle of vehicles) {
        result.append(node('p', `${vehicle.normalized_registration} · ${vehicle.display_name} · ${vehicle.vehicle_type} · ${vehicle.color ?? ''}`));
        const options = node('select'); options.setAttribute('aria-label', 'Compatible empty space');
        for (const space of snapshot?.spaces ?? []) if (!space.session_id && space.operational_status === 'enabled' && space.supported_vehicle_type === vehicle.vehicle_type) options.append(new Option(space.label!, space.id!));
        const check = button('Confirm check-in…', () => {void confirmAction(`Confirm ${vehicle.normalized_registration} has physically arrived at ${options.selectedOptions[0]?.text}?`, async () => {
          await mutate('/api/staff/check-ins','POST',{vehicleId:vehicle.id,spaceId:options.value},true); await refresh(); result.remove();
        });},'primary-button'); check.disabled = !options.options.length;
        result.append(options, check); if (!options.options.length) result.append(node('p', 'No compatible empty space on the current page. Change the space page and search again.'));
      }
      staff.querySelector('.lookup-results')?.remove(); result.className = 'lookup-results';result.dataset.view='checkin'; staff.append(result);
    }); lookup.querySelector('button')!.textContent = 'Find vehicle';lookup.dataset.view='checkin'; staff.append(lookup);
    const created=node('div','','staff-guide');created.dataset.view='drivers';
    created.append(node('h3','Driver onboarding'),node('p','1. Create the driver account with their email and name.'),node('p','2. The driver opens the Mailpit setup link to verify email and choose a password.'),node('p','3. Find the driver below and save their vehicle. Then confirm arrival on Check in a vehicle.'));
    const create=form('Create a driver account',[['email','Driver email','driver@example.com'],['firstName','First name','First name'],['lastName','Last name','Last name']],async body=>{
      const result=await mutate(`/api/staff/locations/${selectedLocation}/drivers`,'POST',body,true);
      created.replaceChildren(node('p',result.setupEmailSent?'Driver account created. Open the setup email in local Mailpit to verify email and choose a password.':'Driver account saved, but setup email was not sent. Retry the same form to send the setup link.'));
    });create.dataset.view='drivers';create.querySelector('button')!.textContent='Create driver and send setup email';
    const foundDriver=node('div','','staff-driver-results');foundDriver.dataset.view='drivers';
    const find=form('Find a driver to register or manage a vehicle',[['search','Driver name or email','Name or driver@example.com']],async body=>{
      const data=await api(`/api/staff/locations/${selectedLocation}/drivers?${body.search.includes('@')?'email':'name'}=${encodeURIComponent(body.search)}`);
      foundDriver.replaceChildren();
      for(const owner of data.users as Row[]) {
        let details:Row={};
        if(owner.vehicle_id) {
          const match=await api(`/api/staff/locations/${selectedLocation}/vehicles?jurisdiction=${encodeURIComponent(owner.registration_jurisdiction!)}&registration=${encodeURIComponent(owner.normalized_registration!)}`);
          details=(match.vehicles as Row[])[0] ?? {};
        }
        const summary=node('p',`${owner.display_name} · ${owner.email} · Current vehicle: ${owner.normalized_registration ?? 'none'}`);foundDriver.append(summary);
        const registration=form('Register vehicle for this driver',[
          ['registrationJurisdiction','Registration jurisdiction','e.g. IN-GJ',owner.registration_jurisdiction ?? ''],['registration','Vehicle registration','e.g. GJ08AB1234',owner.normalized_registration ?? ''],
          ['vehicleType','Vehicle type','car',details.vehicle_type ?? 'car'],['make','Make (optional)','e.g. Maruti',details.make ?? ''],['model','Model (optional)','e.g. Swift',details.model ?? ''],['color','Color (optional)','e.g. White',details.color ?? '']
        ],async values=>{
          const saved=await mutate(`/api/staff/locations/${selectedLocation}/drivers/${owner.id}/vehicle`,'PUT',values);
          const vehicle=saved.vehicle as Row;owner.vehicle_id=vehicle.id;owner.normalized_registration=vehicle.normalized_registration;
          summary.textContent=`${owner.display_name} · ${owner.email} · Current vehicle: ${vehicle.normalized_registration}`;disable.disabled=false;await refresh();
        });
        for(const name of ['make','model','color'])registration.querySelector<HTMLInputElement>(`[name=${name}]`)!.required=false;
        registration.querySelector('button')!.textContent='Save driver vehicle';foundDriver.append(registration);
        const disable=button('Disable driver vehicle…',()=>{void confirmAction('Disable this driver vehicle? Active parking must end first.',async()=>{
          await mutate(`/api/staff/locations/${selectedLocation}/drivers/${owner.id}/vehicle`,'PUT',{disabled:true});owner.vehicle_id=null;summary.textContent=`${owner.display_name} · ${owner.email} · Current vehicle: none`;disable.disabled=true;await refresh();
        });});disable.disabled=!owner.vehicle_id;foundDriver.append(disable);
      }
      if(!(data.users as Row[]).length)foundDriver.append(node('p','No driver account found. Create it above. Employee accounts are excluded.'));
    });find.dataset.view='drivers';find.querySelector('button')!.textContent='Find driver';staff.append(create,created,find,foundDriver);applyView();
  }
  async function buildAdmin(): Promise<void> {
    admin.replaceChildren(); if (role.value !== 'operator_admin') return;
    const ticket = subscription;
    const base = `/api/admin/locations/${location.value}`;
    const approvalPanel=node('div');approvalPanel.dataset.view='approvals';admin.append(approvalPanel);
    let approvalOffset=0;const approvalSearch=node('input');approvalSearch.maxLength=200;approvalSearch.setAttribute('aria-label','Applicant name or email');
    async function showApprovals():Promise<void> {
      const data=await api(base+'/approvals?offset='+approvalOffset+'&search='+encodeURIComponent(approvalSearch.value));if(stopped || ticket!==subscription)return;
      approvalPanel.replaceChildren(node('h2','Pending account approvals'),node('p','Approve drivers before parking access. Approve employees with a role for this location. Decisions require a reason and are audited.'));
      const requests=data.requests as Row[];
      approvalPanel.append(labeled('Applicant name or email',approvalSearch),button('Find requests',()=>{approvalOffset=0;void showApprovals().catch(fail);}));
      for(const request of requests) {
        const decision=form(`${request.display_name} · ${request.email} · ${request.registration_kind}`, [['reason','Reason','Explain the approval or rejection']],async body=>{
          await mutate(base+'/approvals','POST',{userId:request.id,decision:choice.value,role:employeeRole.value,...body});await showApprovals();
        });
        const choice=node('select');choice.append(new Option('Select decision',''),new Option('Approve','approved'),new Option('Reject','rejected'));choice.required=true;
        const employeeRole=node('select');employeeRole.append(new Option('Attendant','attendant'),new Option('Operator administrator','operator_admin'));
        decision.insertBefore(labeled('Decision',choice),decision.querySelector('button'));
        if(request.registration_kind==='employee')decision.insertBefore(labeled('Location role',employeeRole),decision.querySelector('button'));
        decision.querySelector('button')!.textContent='Save decision';approvalPanel.append(decision);
      }
      if(!requests.length)approvalPanel.append(node('p','No pending account requests.'));
      const previous=button('Previous requests',()=>{approvalOffset=Math.max(0,approvalOffset-100);void showApprovals().catch(fail);});previous.disabled=approvalOffset===0;
      const next=button('Next requests',()=>{approvalOffset+=100;void showApprovals().catch(fail);});next.disabled=requests.length<100;approvalPanel.append(previous,next);
    }
    await showApprovals();
    const data = await api(base + '/configuration'); if (stopped || ticket !== subscription || role.value !== 'operator_admin') return;
    const config = data.location as Row;
    admin.append(node('h2', 'Location administration'), node('p', 'Changes require a reason and are audited. Account status applies across this single operator.'));
    admin.append(form('Location settings', [['name','Location name','Name',config.name!],['timezone','Display timezone','e.g. Asia/Kolkata',config.timezone!],['reason','Reason','Why are these settings changing?']], async body => {await mutate(base+'/configuration','PUT',body); await refresh();}));
    admin.append(form('Create another location', [['name','Location name','e.g. City Centre'],['timezone','Timezone','e.g. Asia/Kolkata'],['reason','Reason','Reason for new location']], async body => {await mutate('/api/admin/locations','POST',body); await loadLocations();}));
    async function syncZones(): Promise<void> {
      const updated=await api(base+'/configuration');if(stopped || ticket!==subscription)return;
      for(const select of admin.querySelectorAll<HTMLSelectElement>('[data-zone-picker]')) {
        const selected=select.value;select.replaceChildren();
        for(const row of updated.zones as Row[])select.append(new Option(row.label!,row.id!));
        if([...select.options].some(option=>option.value===selected))select.value=selected;
      }
    }
    admin.append(form('Add a floor / zone', [['label','Floor / zone name','e.g. First floor'],['reason','Reason','Why add this floor?']], async body => {await mutate(base+'/zones','POST',body); await refresh(); await syncZones();}));
    const rename=form('Rename a floor / zone',[['label','New floor name','First floor'],['reason','Reason','Explain the name change']],async body=>{
      await mutate(base+'/zones','PUT',{...body,id:rename.querySelector<HTMLSelectElement>('select')!.value});await refresh();await syncZones();
    });
    const zoneLabel=node('label','Existing floor / zone'),zoneSelect=node('select');zoneSelect.required=true;zoneSelect.dataset.zonePicker='true';
    for(const row of data.zones as Row[]) zoneSelect.append(new Option(row.label!,row.id!));zoneLabel.append(zoneSelect);rename.insertBefore(zoneLabel,rename.querySelector('button'));admin.append(rename);
    const spaceForm = form('Add a numbered space', [['label','Space label','e.g. F1-01'],['reason','Reason','Why add this space?']], async body => {
      const zone = spaceForm.querySelector<HTMLSelectElement>('[name=zoneId]')!, type = spaceForm.querySelector<HTMLSelectElement>('[name=vehicleType]')!;
      await mutate(base+'/spaces','POST',{...body,zoneId:zone.value,vehicleType:type.value}); await refresh();
    });
    for (const [name,label,options] of [['zoneId','Floor / zone',(data.zones as Row[]).map(row => [row.id!,row.label!])],['vehicleType','Compatible vehicle type',[['car','Car'],['motorcycle','Motorcycle'],['van','Van']]]] as [string,string,string[][]][]) {
      const field = node('label', label), select = node('select'); select.name = name; select.required = true;if(name==='zoneId')select.dataset.zonePicker='true'; for(const [value,text] of options) select.append(new Option(text,value)); field.append(select); spaceForm.insertBefore(field,spaceForm.querySelector('button'));
    } admin.append(spaceForm);
    const staffResult = node('div');staffResult.dataset.view='drivers';
    const userForm = form('Find a user / vehicle', [['search','Driver name or email','Name or driver@example.com']], async body => {
      const found = await api(base+'/users?'+(body.search.includes('@')?'email':'name')+'='+encodeURIComponent(body.search));
      if (stopped || ticket !== subscription) return;
      staffResult.replaceChildren(table(found.users as Row[],[['display_name','Name'],['email','Email'],['id','User ID'],['status','Status'],['normalized_registration','Vehicle']]));
      for(const user of found.users as Row[]) {
        const manage = form(`Account status for ${user.email}`, [['status','Status: enabled or disabled', 'disabled'],['reason','Reason','Explain this account change']], async body => {await mutate(base+'/users','PUT',{...body,userId:user.id});});
        staffResult.append(manage, button('Disable this vehicle…', () => {void confirmAction('Disable this registered vehicle? Any active parking session must end first.', async () => {
          await mutate(base+'/users','PUT',{userId:user.id,status:user.status,disableVehicle:true,reason:'Administrator confirmed vehicle disable from user management'});
        });}));
      }
    }); userForm.querySelector('button')!.textContent = 'Find user'; admin.append(userForm, staffResult);
    const enroll=form('Add / approve an employee account', [['email','Employee email (separate from parking customers)','employee@example.com'],['reason','Reason','Employee onboarding']],async body=>{
      await mutate(base+'/staff-accounts','POST',body);await showStaff();
    });
    enroll.querySelector('button')!.textContent='Approve employee email';
    enroll.append(node('p','Enter the employee email here even if they already registered. Accounts with vehicle or parking history cannot be enrolled as employees. Then find the employee below and assign a location role. Enrollment alone grants no location access.'));
    admin.append(enroll);
    const employeeSearch=node('input');employeeSearch.setAttribute('aria-label','Staff name or email');employeeSearch.placeholder='Staff name or email';employeeSearch.maxLength=200;
    const searchStaff=button('Find staff',()=>{employeeOffset=0;void showStaff().catch(fail);});
    const staffSearchPanel=node('div');staffSearchPanel.dataset.view='people';staffSearchPanel.append(labeled('Staff name or email',employeeSearch),searchStaff);admin.append(staffSearchPanel);
    const list = node('div');list.dataset.view='people'; admin.append(list);let employeeOffset=0;
    async function showStaff(): Promise<void> {
      const data = await api(base+'/staff-accounts?offset='+employeeOffset+'&search='+encodeURIComponent(employeeSearch.value)); if(stopped || ticket!==subscription)return;
      const rows=data.staffAccounts as Row[];
      list.replaceChildren(node('h3','Employee accounts and location roles'),table(rows,[['display_name','Name'],['email','Staff email'],['role','Assigned role']]));
      for(const employee of rows) {
        if(!employee.user_id){list.append(node('p',`${employee.email}: awaiting registration, email verification and first parking-app sign-in.`));continue;}
        const assign=form(`Location role for ${employee.email}`, [['reason','Reason','Explain this staff role change']],async body=>{
          await mutate(base+'/staff','POST',{...body,userId:employee.user_id,role:choice.value});await showStaff();
        });
        const choice=node('select');choice.name='role';choice.required=true;
        for(const [value,label] of [['attendant','Attendant — check-in / check-out'],['operator_admin','Administrator — manage location and staff'],['none','No location access']])choice.append(new Option(label,value));
        choice.value=employee.role ?? 'none';assign.insertBefore(labeled('Employee role',choice),assign.querySelector('button'));
        list.append(assign);
      }
      if(!rows.length)list.append(node('p','No employee accounts approved for this location. Driver accounts never appear in this list.'));
      const previous=button('Previous employees',()=>{employeeOffset=Math.max(0,employeeOffset-100);void showStaff().catch(fail);});previous.disabled=employeeOffset===0;
      const next=button('Next employees',()=>{employeeOffset+=100;void showStaff().catch(fail);});next.disabled=rows.length<100;list.append(previous,next);
    }
    await showStaff();
    const audit = node('div');audit.dataset.view='audit'; let auditOffset = 0;
    const auditForm = form('Search audit records', [['action','Exact action (e.g. check_in, audit_read)','check_in']], async body => {auditOffset = 0; await showAudit(body.action);});
    auditForm.querySelector<HTMLInputElement>('input')!.required = false;
    async function showAudit(action = auditForm.querySelector<HTMLInputElement>('input')!.value): Promise<void> {
      const data = await api(base+`/audit?action=${encodeURIComponent(action)}&offset=${auditOffset}`); if(stopped || ticket!==subscription)return; const rows = data.events as Row[];
      const prev = button('Previous audit records',()=>{auditOffset=Math.max(0,auditOffset-50);void showAudit().catch(fail);}); prev.disabled=auditOffset===0;
      const next = button('Next audit records',()=>{auditOffset+=50;void showAudit().catch(fail);}); next.disabled=rows.length<50;
      audit.replaceChildren(table(rows,[['action','Action'],['occurred_at','Time (UTC)'],['actor_id','Actor'],['target_id','Target'],['request_id','Request'],['sanitized_changes','Changes']]),prev,next);
    }
    auditForm.querySelector('button')!.textContent='Search'; admin.append(auditForm,audit); await showAudit('');
    for(const item of admin.querySelectorAll<HTMLFormElement>(':scope > form')) {
      const heading=item.querySelector('h3')?.textContent ?? '';
      item.dataset.view=heading.includes('Location settings') || heading.includes('another location')?'locations':heading.includes('floor') || heading.includes('space')?'spaces':heading.includes('audit')?'audit':heading==='Find a user / vehicle'?'drivers':'people';
    }
    applyView();
  }
  async function changed(): Promise<void> {
    const ticket = ++subscription; streamController?.abort(); clearTimeout(timer); offset = 0; cursor = '0';
    versions.clear();
    spaces.replaceChildren();session.replaceChildren();history.replaceChildren();
    scope = role.value === 'driver' ? 'locations' : 'staff/locations';
    activeView=views[role.value][0][0];applyView();
    staff.replaceChildren(); admin.replaceChildren(); await refresh();
    if(stopped || ticket!==subscription)return;
    restoreRoute();applyView();renderSpaces();
    await buildStaff();
    if(stopped || ticket!==subscription)return;
    await buildAdmin();
    if(stopped || ticket!==subscription)return;
    void connect(ticket);
  }
  function roles(): void {
    role.replaceChildren();
    if(me.accountType!=='staff')role.append(new Option('Driver','driver'));
    const assignment = assignments.find(item => item.locationId === location.value);
    if (assignment && (me.mfa || me.staffMfaRequired===false)) {role.append(new Option(assignment.role === 'operator_admin' ? 'Administrator' : 'Staff',assignment.role));role.value=assignment.role;}
    if(!role.options.length)role.append(new Option('Staff setup','attendant'));
  }
  async function loadLocations(): Promise<void> {
    const data = await api('/api/locations'); if (stopped) return;
    const profile=await api('/api/me');if(stopped)return;
    assignments.splice(0,assignments.length,...profile.assignments as Assignment[]);
    me.accountType=profile.accountType;
    me.staffMfaRequired=profile.staffMfaRequired;
    const selected = location.value; location.replaceChildren();
    for (const item of data.locations as Row[]) location.append(new Option(item.name!,item.id!));
    if([...location.options].some(item=>item.value===selected)) location.value=selected;
    else if(me.accountType==='staff' && assignments.length)location.value=assignments[0].locationId;
    if(me.accountType==='staff' && ((me.staffMfaRequired!==false && !me.mfa) || !assignments.some(item=>item.locationId===location.value))) {
      setupPending=true;
      ++subscription;++epoch;streamController?.abort();clearTimeout(timer);
      snapshot=undefined;spaces.replaceChildren();staff.replaceChildren();admin.replaceChildren();session.replaceChildren();history.replaceChildren();
      roles();activeView='occupancy';applyView();
      status.textContent=me.staffMfaRequired!==false && !me.mfa?'Staff account: enroll an authenticator in Account security, then sign out and sign in again.':'Staff account: ask your administrator to assign a location role. Driver registration is unavailable for employee accounts.';
      return;
    }
    setupPending=false;
    roles(); if (!location.options.length) {status.textContent='No locations configured. Ask your operator administrator.';return;} await changed();
  }
  function switchWorkspace():void {
    window.history.replaceState(null,'',`#workspace/${role.value}/${views[role.value][0][0]}`);
    void changed().catch(fail);
  }
  location.addEventListener('change',()=>{roles();switchWorkspace();}); role.addEventListener('change',switchWorkspace);
  floor.addEventListener('change',renderSpaces); search.addEventListener('input',renderSpaces);
  void loadLocations().catch(fail);
  const fallback = setInterval(()=>{if(!stopped && (failures > 0 || Date.now()-lastSuccess>15000)) void refresh();},15000);
  return () => {
    stopped=true;epoch++;streamController?.abort();clearTimeout(timer);clearInterval(fallback);window.removeEventListener('popstate',restoreRoute);
    document.body.classList.remove('authenticated-workspace');for(const panel of publicSections)panel.hidden=false;
    navigation.replaceChildren(...publicNavigation);topbarTitle.textContent='Overview';publicLabel.textContent='Public availability';
    document.getElementById('overview')!.after(account);account.hidden=false;account.prepend(accountMessage);account.append(signout);
    section.replaceChildren();section.hidden=true;
  };
}
