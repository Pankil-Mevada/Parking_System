import {changedResources, type Change} from './realtime';
export type Api = (path: string, method?: string, body?: unknown, key?: string) => Promise<Record<string, unknown>>;
type Row = Record<string, string | null>;
type Assignment = {locationId: string; role: string};
type Snapshot = {cursor: string; timestamp: string; floors: Row[]; location?:Row; spaces?: Row[]; unassigned: {total: string}};
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
  let activeView='dashboard',navigationKey='',previousSession:string|null|undefined;
  const views: Record<string,[string,string,string][]> = {
    driver:[['dashboard','My dashboard','Your current parking session and the next step.'],['availability','Find parking','Choose a location and compare available spaces by floor.'],['vehicle','My vehicle','Register or replace the one vehicle linked to your account.'],['history','My parking history','Review your own arrivals and departures.']],
    attendant:[['vehicles','Vehicle register','Review this building’s registered vehicles, owners and status.'],['approvals','Driver approvals','Verify driver registration requests and review previous decisions.'],['occupancy','Space occupancy','View parking spaces and location availability.'],['drivers','Driver accounts & vehicles','Create driver accounts and register or manage their vehicles.'],['checkin','Check in a vehicle','Verify a number plate at the main gate, then approve check-in or reject entry.'],['checkout','Check out a vehicle','Select an occupied space and confirm departure.']],
    operator_admin:[['vehicles','Vehicle register','Review this building’s registered vehicles, owners and status.'],['approvals','Account approvals','Approve driver and employee registration requests.'],['overview','Location overview','Monitor capacity and occupancy at this location.'],['spaces','Floors & spaces','Configure floors, numbered spaces, compatibility and maintenance.'],['locations','Location settings','Manage your saved building address and entrance details.'],['drivers','Drivers','Find driver accounts and manage their vehicles. Drivers cannot be assigned staff roles.'],['people','Staff accounts','Approve separate employee accounts and assign their location roles.'],['audit','Audit records','Search recorded actions at this location.'],['operations','Check-in / check-out','Perform authorized staff parking operations.']],
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
  const approvals=node('div','','approval-panel');const registry=node('div','','vehicle-register');const locationPreview=node('article','','location-preview');
  const notifications=node('div','','parking-notifications');notifications.setAttribute('role','log');notifications.setAttribute('aria-live','polite');
  function notify(text:string):void {notifications.prepend(node('p',text));while(notifications.children.length>3)notifications.lastChild!.remove();}
  const pages = node('div', '', 'workspace-controls');
  const previous = button('Previous spaces', () => {offset = Math.max(0, offset - 100); void refresh();});
  const next = button('Next spaces', () => {offset += 100; void refresh();}); pages.append(previous, next);
  const filters=node('div','','workspace-controls space-filters');filters.append(floor,search);
  function labeled(text:string,field:HTMLElement):HTMLLabelElement {const label=node('label',text);field.setAttribute('aria-label',text);if(field instanceof HTMLInputElement && field.type==='checkbox')label.className='verification-label';label.append(field);return label;}
  controls.append(labeled('Parking location',location),labeled('Switch workspace',role),button('Refresh now', () => {void loadLocations().catch(fail);}));
  section.replaceChildren(badge,title,description,accountStrip,controls,status,notifications,locationPreview,filters,floors,session,approvals,registry,staff,spaces,pages,history,admin,account); section.hidden = false;
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
      for(const panel of [account,session,history,floors,spaces,pages,filters,staff,admin,approvals,registry,locationPreview])panel.hidden=true;
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
    registry.hidden=activeView!=='vehicles' || workspace==='driver';locationPreview.hidden=!['availability','overview','occupancy'].includes(activeView);
    approvals.hidden=activeView!=='approvals' || workspace==='driver';
    account.hidden=activeView!=='vehicle';session.hidden=activeView!=='dashboard';history.hidden=activeView!=='history';
    floors.hidden=!['availability','occupancy','overview','spaces'].includes(activeView);
    const showSpaces=['occupancy','checkout','spaces','operations'].includes(activeView) && workspace!=='driver';
    spaces.hidden=pages.hidden=!showSpaces;filters.hidden=!showSpaces && !['availability','overview'].includes(activeView);search.hidden=!showSpaces;
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
    activeView=view;applyView();renderSpaces();if(view==='vehicles')void buildRegistry().catch(fail);
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
        if (!stopped) feedback.textContent = view.dataset.successMessage ?? 'Saved by the server.';
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
  function renderFloors():void {
    floors.replaceChildren();if(!snapshot)return;
    const rows=snapshot.floors.filter(item=>floor.value==='all' || item.id===floor.value);
    floors.append(node('h3',floor.value==='all'?`${rows.length} floors / zones`:'Selected floor'));
    for(const item of rows){const card=node('article','','floor-card'),icon=node('span','🏢','floor-sticker');icon.setAttribute('aria-hidden','true');
      card.append(icon,node('h3',item.label!),node('p',`${item.available} available · ${item.occupied} occupied`),node('p',`${item.out_of_service} out of service · ${item.capacity} operational`));
      card.append(button(floor.value===item.id?'Show all floors':'Select this floor',()=>{floor.value=floor.value===item.id?'all':item.id!;renderFloors();renderSpaces();}));floors.append(card);
    }
    if(Number(snapshot.unassigned.total) && ['all','unassigned'].includes(floor.value))floors.append(node('p',`${snapshot.unassigned.total} spaces have no assigned floor.`));
    if(!rows.length && floor.value!=='unassigned')floors.append(node('p','No floors configured at this location yet.'));
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
      const sticker=node('span',maintenance?'🛠':occupied?'🚘':'🅿','parking-sticker');sticker.setAttribute('aria-hidden','true');card.append(sticker);
      card.append(node('h3', `${floorName} · ${item.label}`), node('strong', occupied ? '● Occupied' : maintenance ? '⊘ Out of service' : '○ Available'), node('p', `Compatible: ${item.supported_vehicle_type}`));
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
    const sessionKey=current?.id ?? (current?`${current.location}/${current.space}/${current.checked_in_at}`:null);
    if(previousSession!==undefined && previousSession!==sessionKey && role.value==='driver')notify(current?`Arrival confirmed: ${current.location}, space ${current.space}.`:'Departure confirmed. Your parking history has been updated.');
    previousSession=sessionKey;
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
      if(snapshot?.spaces && data.spaces)for(const current of data.spaces){const before=snapshot.spaces.find(item=>item.id===current.id);if(before && (before.session_id!==current.session_id || before.operational_status!==current.operational_status))notify(`Space ${current.label}: ${current.session_id?'Occupied':current.operational_status==='enabled'?'Available':'Out of service'}${(current.display_name || before.display_name)?` · ${current.display_name || before.display_name} · ${current.registration_snapshot || before.registration_snapshot || ''}`:''}.`);}
      locationPreview.replaceChildren(node('span','📍','floor-sticker'),node('h2',data.location?.name ?? location.selectedOptions[0]?.text ?? 'Building'),node('p',[data.location?.area,data.location?.city,data.location?.country].filter(Boolean).join(' · ') || 'Area details have not been added yet.'),node('p',data.location?.address || 'Ask your administrator to add the building address and landmark.'));
      snapshot = data; cursor = data.cursor; lastSuccess = Date.now();
      for (const space of data.spaces ?? []) if(space.id && space.version) versions.set(space.id,BigInt(space.version));
      const selected = floor.value; floor.replaceChildren(new Option('All floors', 'all'));
      for(const item of data.floors)floor.append(new Option(item.label!,item.id!));
      if(Number(data.unassigned.total))floor.append(new Option('Unassigned floor','unassigned'));
      if ([...floor.options].some(item => item.value === selected)) floor.value = selected;
      spaces.hidden = pages.hidden = staff.hidden = scope === 'locations';
      renderFloors();renderSpaces(); await driver();
      applyView();
      status.textContent = `Confirmed snapshot · Updated ${date(data.timestamp)}. Connecting for changes…`;
      window.dispatchEvent(new Event('parking-updated'));
    } catch (error) {
      if (generation === epoch && !stopped) {
        // Remove sensitive detail on any failed authorization or unavailable server.
        spaces.replaceChildren(); staff.hidden = true; admin.replaceChildren(); session.replaceChildren(); history.replaceChildren(); snapshot = undefined;approvals.replaceChildren();registry.replaceChildren();locationPreview.replaceChildren();
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
      if(recovering && snapshot){await buildStaff();await buildAdmin();await buildApprovals();await buildRegistry();}
      if (BigInt(data.cursor) >= BigInt(cursor)) cursor = data.cursor;
      if(!snapshot) throw new Error('Snapshot unavailable');
      failures = 0; status.textContent = `Connected · Last confirmed snapshot ${date(snapshot.timestamp)}`;
      // Periodic snapshot also covers floor/name/role changes that have no space event yet.
      if (Date.now() - lastSuccess > 15000) await refresh();
    } catch {
      if (!stopped && ticket === subscription) {
        failures++; status.textContent = 'Disconnected / stale · Reconnecting with backoff. Snapshot fallback runs every 15 seconds.';
        spaces.replaceChildren(); admin.replaceChildren();approvals.replaceChildren();registry.replaceChildren();locationPreview.replaceChildren(); session.replaceChildren();history.replaceChildren();staff.hidden = true;
        section.querySelectorAll('dialog').forEach(dialog=>dialog.close());
        if (Date.now() - lastSuccess > 15000) await refresh();
      }
    } finally {if (!stopped && ticket === subscription) timer = setTimeout(() => {void connect(ticket);}, Math.min(15000, 1000 * 2 ** Math.min(failures, 4)));}
  }
  async function buildStaff(): Promise<void> {
    staff.replaceChildren(); if (scope === 'locations') return;
    const ticket = subscription, selectedLocation = location.value;
    const lookup = form('Check in a registered vehicle', [['jurisdiction','Registration jurisdiction','e.g. IN-GJ'],['registration','Exact vehicle registration','e.g. GJ 01 AB 1234']], async body => {
      staff.querySelector('.lookup-results')?.remove();
      const data = await api(`/api/staff/locations/${selectedLocation}/gate-check?jurisdiction=${encodeURIComponent(body.jurisdiction)}&registration=${encodeURIComponent(body.registration)}`);
      if (stopped || ticket !== subscription || !snapshot || failures>0) return;
      const vehicle=data.vehicle as Row|null,result=node('div','','gate-review');result.dataset.status=String(data.status);
      const labels:Record<string,string>={eligible:'Registered and enabled — entry can be approved',not_registered:'Vehicle is not registered',vehicle_disabled:'Vehicle registration is disabled',account_disabled:'Driver account is disabled',approval_pending:'Driver registration is waiting for approval',registration_rejected:'Driver registration was rejected',already_parked:'This driver already has an active parking session'};
      result.append(node('h3',`Main gate verification · ${body.registration} (${body.jurisdiction})`),node('strong',labels[String(data.status)] ?? 'Check unavailable','gate-status'));
      if(vehicle)result.append(node('p',`${vehicle.normalized_registration} · ${vehicle.display_name} · ${vehicle.vehicle_type} · ${vehicle.color || 'Color not provided'}`));
      const comment=node('textarea');comment.maxLength=500;comment.rows=2;comment.placeholder='Optional reason or observation';result.append(labeled('Gate comment (optional)',comment));
      const gateFloor=node('select');gateFloor.append(new Option('All floors','all'));for(const item of snapshot?.floors ?? [])gateFloor.append(new Option(item.label!,item.id!));
      const available=data.spaces as Row[],options=node('select');options.setAttribute('aria-label','Compatible empty space');
      if(available.some(item=>!item.zone_id))gateFloor.append(new Option('Unassigned floor','unassigned'));
      function fillSpaces():void{options.replaceChildren();for(const space of available)if(gateFloor.value==='all' || (space.zone_id || 'unassigned')===gateFloor.value)options.append(new Option(`${space.floor || 'Unassigned floor'} · ${space.label}`,space.id!));check.disabled=!data.canCheckIn || !options.options.length;}
      const check=button('Confirm check-in…',()=>{void confirmAction(`Approve entry and confirm ${vehicle?.normalized_registration} has arrived at ${options.selectedOptions[0]?.text}?`,async()=>{
        await mutate('/api/staff/check-ins','POST',{vehicleId:vehicle!.id,spaceId:options.value,comment:comment.value},true);notify(`Entry approved for ${vehicle!.display_name} · ${vehicle!.normalized_registration}.`);result.remove();await refresh();
      });},'primary-button');
      if(data.canCheckIn){result.append(labeled('Check-in floor',gateFloor),labeled('Compatible empty space',options),node('p','Select a floor and an empty compatible space. Shows up to 500 available spaces. Availability may change before you confirm.'));gateFloor.addEventListener('change',fillSpaces);}
      fillSpaces();result.append(check);
      const reject=button('Reject entry…',()=>{void confirmAction(`Reject entry for ${body.registration}? No parking session will be created.`,async()=>{
        await mutate(`/api/staff/locations/${selectedLocation}/gate-decisions`,'POST',{jurisdiction:body.jurisdiction,registration:body.registration,decision:'rejected',comment:comment.value},true);notify(`Entry rejected for ${vehicle?.display_name?vehicle.display_name+' · ':''}${body.registration}.`);result.replaceChildren(node('p','Entry rejection recorded. No parking session was created.'));
      });});result.append(reject,node('p','Gate decisions do not open or close a physical barrier. Camera and barrier integration will be added later.'));
      staff.querySelector('.lookup-results')?.remove(); result.classList.add('lookup-results');result.dataset.view='checkin'; staff.append(result);applyView();
    }); lookup.querySelector('button')!.textContent = 'Find vehicle';lookup.dataset.view='checkin';lookup.dataset.successMessage='Vehicle status checked. Review the result below; entry is not confirmed yet.';lookup.insertBefore(node('p','Enter any arriving vehicle’s exact number plate and jurisdiction to check registration and entry eligibility.'),lookup.querySelector('label'));lookup.addEventListener('input',()=>staff.querySelector('.lookup-results')?.remove()); staff.append(lookup);
    const created=node('div','','staff-guide');created.dataset.view='drivers';
    created.append(node('h3','Driver onboarding'),node('p','1. Create the driver account with their email and name.'),node('p','2. The driver opens the Mailpit setup link to verify email and choose a password.'),node('p','3. Verify and approve the request under Driver approvals. Then find the driver below, save their vehicle, and confirm arrival on Check in a vehicle.'));
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
  async function buildApprovals():Promise<void> {
    approvals.replaceChildren();if(role.value==='driver')return;
    const ticket=subscription,administrator=role.value==='operator_admin';
    const base=`/api/${administrator?'admin':'staff'}/locations/${location.value}/approvals`;
    let state='pending',page=0;
    const query=node('input');query.maxLength=200;query.setAttribute('aria-label','Applicant name or email');query.placeholder='Search name or email';
    async function show():Promise<void> {
      const data=await api(`${base}?status=${state}&offset=${page}&search=${encodeURIComponent(query.value)}`);
      if(stopped || ticket!==subscription)return;
      approvals.replaceChildren(node('h2',administrator?'Account requests':'Driver registration requests'),node('p',administrator?'Review requests for this building. Every decision is recorded.':'Verify the driver’s identity and building access before approval. Employee requests are managed by administrators.'));
      const tabs=node('div','','approval-tabs');tabs.setAttribute('role','group');tabs.setAttribute('aria-label','Request status');
      const counts=data.counts as Record<string,number>;
      for(const [key,label] of [['pending','Pending'],['approved','Approved'],['rejected','Rejected']]) {
        const tab=button(`${label} (${counts[key] ?? 0})`,()=>{state=key;page=0;void show().catch(fail);});tab.setAttribute('aria-pressed',String(state===key));tabs.append(tab);
      }
      approvals.append(tabs,labeled('Applicant name or email',query),button('Find requests',()=>{page=0;void show().catch(fail);}));
      const requests=data.requests as Row[];
      for(const request of requests) {
        const card=node('article','','request-card');card.append(node('h3',request.display_name ?? 'Driver'),node('p',request.email ?? ''),node('p',`${request.registration_kind} · ${state}`));
        card.append(node('p',`Vehicle: ${request.vehicle_registration || 'Not registered yet'}`));if(request.decision_reason)card.append(node('p',`Decision reason: ${request.decision_reason}`));
        if(state==='pending') {
          const choice=node('select');choice.append(new Option('Select decision',''),new Option('Approve','approved'),new Option('Reject','rejected'));choice.required=true;
          const employeeRole=node('select');employeeRole.append(new Option('Attendant','attendant'),new Option('Operator administrator','operator_admin'));
          const verified=node('input');verified.type='checkbox';
          const decision=form('Review request',[['reason','Reason','Record what you verified or why you rejected']],async body=>{
            if(choice.value==='approved' && request.registration_kind==='driver' && !verified.checked)throw new Error('Confirm driver identity and building access verification first.');
            await mutate(base,'POST',{...body,userId:request.id,decision:choice.value,...(request.registration_kind==='employee'?{role:employeeRole.value}:{}),verificationConfirmed:verified.checked});
            notify(`Request ${choice.value} for ${request.display_name}.`);await show();
          });
          const submit=decision.querySelector('button')!;submit.textContent='Save decision';decision.insertBefore(labeled('Decision',choice),submit);
          if(request.registration_kind==='employee')decision.insertBefore(labeled('Location role',employeeRole),submit);
          else decision.insertBefore(labeled('I verified this driver’s identity and building access',verified),submit);
          card.append(decision);
        }
        approvals.append(card);
      }
      if(!requests.length)approvals.append(node('p',`No ${state} requests match this building and search.`));
      const prev=button('Previous requests',()=>{page=Math.max(0,page-100);void show().catch(fail);});prev.disabled=page===0;
      const next=button('Next requests',()=>{page+=100;void show().catch(fail);});next.disabled=requests.length<100;approvals.append(prev,next);applyView();
    }
    await show();
  }
  async function buildRegistry():Promise<void> {
    registry.replaceChildren();if(role.value==='driver')return;
    const ticket=subscription,base=`/api/staff/locations/${location.value}/vehicle-register`;
    let offset=0,loadEpoch=0;const search=node('input');search.maxLength=200;search.placeholder='Plate, vehicle name or owner';const filter=node('select');
    const labels:Record<string,string>={all:'All vehicles',enabled:'Enabled',parked:'Parked here',disabled:'Vehicle disabled',account_disabled:'Owner account disabled',approval_pending:'Approval pending',registration_rejected:'Registration rejected'};
    for(const [value,label] of Object.entries(labels))filter.append(new Option(label,value));
    async function show():Promise<void>{const load=++loadEpoch;registry.replaceChildren(node('p','Loading vehicle records…'));const data=await api(`${base}?offset=${offset}&status=${filter.value}&search=${encodeURIComponent(search.value)}`).catch(error=>{if(!stopped && ticket===subscription && load===loadEpoch)registry.replaceChildren(node('p','Could not load vehicle records. Use Refresh now to retry.'));throw error;});if(stopped || ticket!==subscription || load!==loadEpoch || !snapshot)return;
      const counts=data.counts as Record<string,number>,summary=node('div','','registry-counts');
      for(const [key,label] of [['total','Registered records'],['enabled','Enabled'],['parked','Parked here'],['disabled','Disabled'],['approval_pending','Pending'],['registration_rejected','Rejected'],['account_disabled','Account disabled']])summary.append(node('div',`${counts[key] ?? 0} ${label}`));
      registry.replaceChildren(node('h2','Registered vehicles'),node('p','This building’s vehicle records, including disabled registration history. Parked status refers to this building.'),summary);
      const filters=node('div','','workspace-controls');filters.append(labeled('Search registered vehicles',search),labeled('Vehicle status',filter),button('Search vehicles',()=>{offset=0;void show().catch(fail);}));registry.append(filters);
      const rows=(data.vehicles as Row[]).map(row=>({...row,vehicle_name:row.vehicle_name || row.vehicle_type,status:labels[row.status!] ?? row.status}));
      registry.append(table(rows,[['vehicle_name','Vehicle name'],['normalized_registration','Number plate'],['owner_name','Owner name'],['vehicle_type','Type'],['color','Color'],['status','Status']]));
      const prev=button('Previous vehicles',()=>{offset=Math.max(0,offset-100);void show().catch(fail);});prev.disabled=offset===0;
      const next=button('Next vehicles',()=>{offset+=100;void show().catch(fail);});next.disabled=rows.length<100;registry.append(prev,next);applyView();
    }
    filter.addEventListener('change',()=>{offset=0;void show().catch(fail);});await show();
  }
  async function buildAdmin(): Promise<void> {
    section.querySelectorAll<HTMLDialogElement>('.location-picker').forEach(dialog=>{if(dialog.open)dialog.close();dialog.remove();});admin.replaceChildren(); if (role.value !== 'operator_admin') return;
    const ticket = subscription;
    const base = `/api/admin/locations/${location.value}`;
    const data = await api(base + '/configuration'); if (stopped || ticket !== subscription || role.value !== 'operator_admin') return;
    const config = data.location as Row;
    const savedLocation=node('article','','saved-location-card');savedLocation.dataset.view='locations';
    const locationDialog=node('dialog');locationDialog.className='location-picker';locationDialog.setAttribute('aria-label','Set building location');section.append(locationDialog);
    function showSavedLocation():void {
      const complete=Boolean(config.area || config.city || config.address);
      savedLocation.replaceChildren(node('span','📍','location-pin'),node('span',complete?'Saved location':'Complete your building address','saved-location-label'),node('h2',config.name || 'Your building'),node('p',[config.area,config.city,config.country].filter(Boolean).join(' · ') || 'Add your area and city'),node('p',config.address || 'Add an address or landmark so staff can identify the entrance.'),node('p',config.latitude && config.longitude?'Building position saved':'You can use your current location or enter the address manually.','location-note'));
      savedLocation.append(button(complete?'Edit saved location':'Set building location',openLocationPicker,'primary-button'));
    }
    function openLocationPicker():void {
      ++pickerEpoch;coordinates={};geoStatus.textContent='';settings.querySelector<HTMLElement>('[role=status]')!.textContent='';
      for(const name of ['name','area','city','country','address','timezone'])settings.querySelector<HTMLInputElement>(`[name=${name}]`)!.value=config[name] ?? '';
      renderAddressPreview();locationDialog.showModal();
    }
    showSavedLocation();admin.append(savedLocation);
    const settings=form('Location settings', [['name','Building / location name','e.g. Arjun Apartment',config.name!],['area','Area / neighbourhood','e.g. Navrangpura',config.area ?? ''],['city','City / town','e.g. Ahmedabad',config.city ?? ''],['country','Country','e.g. India',config.country ?? ''],['address','Address / landmark','Street, building entrance and nearby landmark',config.address ?? ''],['timezone','Display timezone','e.g. Asia/Kolkata',config.timezone!],], async body => {
      await mutate(base+'/configuration','PUT',{...body,...coordinates,reason:'Administrator reviewed and saved building location'});
      const saved=await api(base+'/configuration');if(stopped || ticket!==subscription)return;
      Object.assign(config,saved.location as Row);showSavedLocation();if(location.selectedOptions[0])location.selectedOptions[0].text=config.name!;
      locationDialog.close();notify('Building location settings saved.');await refresh();
    });
    let coordinates:Record<string,string>={};
    for(const name of ['area','city','country','address'])settings.querySelector<HTMLInputElement>(`[name=${name}]`)!.required=false;
    settings.querySelector<HTMLInputElement>('[name=address]')!.maxLength=500;
    settings.querySelector<HTMLButtonElement>('button[type=submit]')!.textContent='Save location';settings.querySelector<HTMLInputElement>('[name=country]')!.maxLength=100;
    const geoStatus=node('p');geoStatus.setAttribute('role','status');let detecting=false,pickerEpoch=0;let geoRequest:AbortController|undefined;
    const detect=button('Use current location',()=>{
      if(detecting)return;if(!navigator.geolocation){geoStatus.textContent='Location detection is unavailable. Enter the building details manually.';return;}
      const detection=++pickerEpoch;detecting=true;detect.disabled=true;geoStatus.textContent='Finding your current area…';
      navigator.geolocation.getCurrentPosition(position=>{void (async()=>{
        if(stopped || ticket!==subscription || detection!==pickerEpoch || !locationDialog.open)return;
        coordinates={latitude:String(position.coords.latitude),longitude:String(position.coords.longitude)};
        try {
          const url=new URL('https://api.bigdatacloud.net/data/reverse-geocode-client');url.search=new URLSearchParams({latitude:coordinates.latitude,longitude:coordinates.longitude,localityLanguage:'en'}).toString();
          geoRequest=new AbortController();const response=await fetch(url,{credentials:'omit',referrerPolicy:'no-referrer',signal:AbortSignal.any([geoRequest.signal,AbortSignal.timeout(8000)])});if(!response.ok)throw new Error('Area lookup unavailable');const place=await response.json();
          if(stopped || ticket!==subscription || detection!==pickerEpoch || !locationDialog.open)return;
          if(!place.locality && !place.city)throw new Error('No readable area returned');
          for(const [name,value] of [['area',place.locality || place.city],['city',place.city || place.principalSubdivision],['country',place.countryName]])if(typeof value==='string')settings.querySelector<HTMLInputElement>(`[name=${name}]`)!.value=value.slice(0,name==='country'?100:200);
          renderAddressPreview();geoStatus.textContent='Current area found. Check the building name, area and city, then add the address or landmark and Save.';
        }catch{if(detection!==pickerEpoch || !locationDialog.open)return;geoStatus.textContent='Your position was detected, but area lookup is unavailable. Enter the area, city and address manually.';}
      })().finally(()=>{if(detection===pickerEpoch){detecting=false;detect.disabled=false;}});},()=>{if(detection!==pickerEpoch || !locationDialog.open)return;detecting=false;detect.disabled=false;geoStatus.textContent='Location permission was denied or unavailable. Enter building and area details manually.';},{timeout:10000,maximumAge:0});
    });
    locationDialog.addEventListener('close',()=>{++pickerEpoch;geoRequest?.abort();detecting=false;detect.disabled=false;});
    detect.className='primary-button location-detect';
    const pickerActions=node('div','','location-picker-actions');pickerActions.append(detect,button('Enter address manually',()=>{++pickerEpoch;geoRequest?.abort();detecting=false;detect.disabled=false;coordinates={latitude:'',longitude:''};geoStatus.textContent='Enter your building and area details below. The previous device position will be cleared when you save.';settings.querySelector<HTMLInputElement>('[name=name]')!.focus();}));
    const addressPreview=node('article','','address-review');addressPreview.setAttribute('aria-label','Address preview');
    function renderAddressPreview():void {
      const value=(name:string)=>settings.querySelector<HTMLInputElement>(`[name=${name}]`)!.value.trim();
      addressPreview.replaceChildren(node('span','📍','location-pin'),node('strong',value('name') || 'Your building'),node('p',[value('area'),value('city'),value('country')].filter(Boolean).join(' · ') || 'Detect your area or enter it below'),node('p',value('address') || 'Add the building entrance, street or nearby landmark'));
    }
    settings.addEventListener('input',renderAddressPreview);
    const credit=node('p','Current-location lookup shares your device position with BigDataCloud to suggest area and city names. You can enter everything manually instead. ');credit.className='location-privacy';const policy=node('a','Lookup policy');policy.href='https://www.bigdatacloud.com/docs/article/why-is-reverse-geocoding-api-free';policy.target='_blank';policy.rel='noopener';credit.append(policy);
    settings.prepend(node('p','Review the building name, area and entrance details before saving.'));settings.querySelector('h3')!.textContent='Building address';
    locationDialog.append(node('h2','Set building location'),node('p','Use your current area, then add the building and entrance details.'),pickerActions,geoStatus,addressPreview,settings,credit,button('Cancel',()=>locationDialog.close()));
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
    activeView=role.value==='driver'?'dashboard':'approvals';applyView();
    staff.replaceChildren(); admin.replaceChildren();approvals.replaceChildren();registry.replaceChildren();notifications.replaceChildren();snapshot=undefined; await refresh();
    if(stopped || ticket!==subscription)return;
    restoreRoute();applyView();renderSpaces();
    await buildRegistry();
    await buildApprovals();
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
    const selected = location.value || sessionStorage.getItem(`parking-location-${me.id}`) || String(profile.registrationLocationId ?? ''); location.replaceChildren();
    for (const item of data.locations as Row[]) if(me.accountType!=='staff' || assignments.some(assignment=>assignment.locationId===item.id))location.append(new Option(item.name!,item.id!));
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
  location.addEventListener('change',()=>{sessionStorage.setItem(`parking-location-${me.id}`,location.value);roles();switchWorkspace();}); role.addEventListener('change',switchWorkspace);
  floor.addEventListener('change',()=>{renderFloors();renderSpaces();}); search.addEventListener('input',renderSpaces);
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
