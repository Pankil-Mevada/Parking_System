import './style.css';
import './account';
type Location = { id: string; name: string; capacity: number; occupied: number; available: number; outOfService: number };
type Snapshot = { locations: Location[]; timestamp: string };
const status = document.querySelector<HTMLParagraphElement>('#status')!;
const locations = document.querySelector<HTMLElement>('#locations')!;
const refresh = document.querySelector<HTMLButtonElement>('#refresh')!;
const selector = document.querySelector<HTMLSelectElement>('#location-select')!;
const metrics = document.querySelector<HTMLElement>('#metrics')!;
const connection = document.querySelector<HTMLElement>('#connection')!;
let snapshot: Snapshot | undefined;
let lastSuccess: Date | undefined;

function text(id: string, value: string | number): void {
  document.getElementById(id)!.textContent = String(value);
}
function element<K extends keyof HTMLElementTagNameMap>(tag: K, className: string, content?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}
function isLocation(value: unknown): value is Location {
  if (typeof value !== 'object' || value === null) return false;
  const item = value as Record<string, unknown>;
  return typeof item.id === 'string' && typeof item.name === 'string'
    && ['capacity', 'occupied', 'available', 'outOfService'].every(key => Number.isSafeInteger(item[key]) && Number(item[key]) >= 0)
    && Number(item.available) + Number(item.occupied) === item.capacity;
}
function render(): void {
  if (!snapshot) return;
  const visible = snapshot.locations.filter(item => selector.value === 'all' || item.id === selector.value);
  const totals = visible.reduce((sum, item) => ({ available: sum.available + item.available, occupied: sum.occupied + item.occupied, outOfService: sum.outOfService + item.outOfService, capacity: sum.capacity + item.capacity }), { available: 0, occupied: 0, outOfService: 0, capacity: 0 });
  text('hero-available', totals.available);
  text('hero-scope', selector.value === 'all' ? `Across ${visible.length} ${visible.length === 1 ? 'location' : 'locations'}` : visible[0]?.name ?? 'Selected location');
  text('metric-available', totals.available);
  text('metric-occupied', totals.occupied);
  text('metric-maintenance', totals.outOfService);
  text('metric-capacity', totals.capacity);
  text('location-count', `${visible.length} ${visible.length === 1 ? 'location' : 'locations'}`);
  locations.replaceChildren();
  if (!visible.length) locations.append(element('p', 'empty-state', 'No locations configured yet. Availability will appear here when locations are added.'));
  for (const item of visible) {
    const card = element('article', 'location-card');
    const heading = element('div', 'location-card-heading');
    const title = element('div', '');
    title.append(element('span', 'location-kicker', 'PARKING LOCATION'), element('h3', '', item.name));
    heading.append(title, element('span', 'location-symbol', 'P'));
    const summary = element('div', 'location-summary');
    summary.append(element('strong', '', String(item.available)), element('span', '', 'spaces available'));
    const total = item.capacity + item.outOfService;
    const bar = element('div', 'availability-bar');
    bar.setAttribute('aria-hidden', 'true');
    for (const [kind, count] of [['available', item.available], ['occupied', item.occupied], ['maintenance', item.outOfService]] as const) {
      const segment = element('span', `bar-${kind}`);
      segment.style.width = `${total ? count / total * 100 : 0}%`;
      bar.append(segment);
    }
    const legend = element('div', 'location-legend');
    for (const [kind, label, count] of [['available', 'Available', item.available], ['occupied', 'Occupied', item.occupied], ['maintenance', 'Out of service', item.outOfService]] as const) {
      const labelNode = element('span', `legend-item legend-${kind}`);
      labelNode.append(element('i', '', ''), document.createTextNode(`${count} ${label}`));
      legend.append(labelNode);
    }
    const footer = element('div', 'location-card-footer');
    footer.append(element('span', '', `${item.capacity} operational spaces`), element('span', '', item.capacity ? `${Math.round(item.occupied / item.capacity * 100)}% occupied` : 'No operational capacity'));
    card.append(heading, summary, bar, legend, footer);
    locations.append(card);
  }
}

async function load(): Promise<void> {
  const restoreFocus = document.activeElement === refresh;
  refresh.disabled = true;
  metrics.setAttribute('aria-busy', 'true');
  connection.dataset.state = 'loading';
  text('connection-label', 'Loading snapshot');
  status.textContent = 'Loading availability…';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch('/api/locations', { signal: controller.signal, cache: 'no-store' });
    if (!response.ok) throw new Error('Availability request failed');
    const body: Snapshot = await response.json();
    if (!body || !Array.isArray(body.locations) || body.locations.length > 100 || !body.locations.every(isLocation) || typeof body.timestamp !== 'string' || !Number.isFinite(Date.parse(body.timestamp))) throw new Error('Invalid availability snapshot');
    snapshot = body;
    const selected = selector.value;
    selector.replaceChildren(new Option('All locations', 'all'));
    for (const item of body.locations) selector.append(new Option(item.name, item.id));
    selector.value = body.locations.some(item => item.id === selected) ? selected : 'all';
    selector.disabled = !body.locations.length;
    lastSuccess = new Date(body.timestamp);
    render();
    connection.dataset.state = 'ready';
    text('connection-label', 'Snapshot available');
    status.textContent = `${body.locations.length ? 'Snapshot updated' : 'No locations configured'}. Last updated: ${lastSuccess.toLocaleString()}. Refresh to update.`;
  } catch {
    connection.dataset.state = 'error';
    text('connection-label', lastSuccess ? 'Stale snapshot' : 'Disconnected');
    if (!snapshot) {
      text('location-count', 'Unavailable');
      locations.replaceChildren(element('p', 'empty-state', 'Availability could not be loaded. Check your connection and use Refresh availability to try again.'));
    }
    status.textContent = `Disconnected: availability could not be loaded.${lastSuccess ? ` Displayed snapshot is stale; last updated ${lastSuccess.toLocaleString()}.` : ' No availability snapshot received.'} Try again.`;
  } finally {
    clearTimeout(timeout);
    refresh.disabled = false;
    metrics.setAttribute('aria-busy', 'false');
    if (restoreFocus && document.activeElement === document.body) refresh.focus({ preventScroll: true });
  }
}
selector.addEventListener('change', render);
refresh.addEventListener('click', () => { void load(); });

const arrival = document.querySelector<HTMLButtonElement>('#preview-arrival')!;
const departure = document.querySelector<HTMLButtonElement>('#preview-departure')!;
function preview(occupied: boolean): void {
  document.getElementById('sample-bay')!.dataset.occupied = String(occupied);
  text('preview-state', occupied ? 'Occupied' : 'Empty');
  text('preview-message', occupied ? 'Sample vehicle is parked in the demo bay.' : 'Sample vehicle is not parked.');
  arrival.disabled = occupied;
  departure.disabled = !occupied;
  (occupied ? departure : arrival).focus({ preventScroll: true });
}
arrival.addEventListener('click', () => preview(true));
departure.addEventListener('click', () => preview(false));
void load();
window.addEventListener('parking-updated', () => {void load();});
// Anonymous visitors receive aggregate snapshots only; authenticated floor views
// use the replayable SSE endpoint. Keep a bounded aggregate fallback for visitors.
setInterval(() => {if (!document.hidden) void load();}, 15000);
