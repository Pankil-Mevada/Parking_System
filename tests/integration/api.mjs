import test, { before } from 'node:test';
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';
const base = process.env.PARKING_TEST_API_URL ?? 'http://127.0.0.1:8080';
before(async () => {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(base + '/api/ready', { signal: AbortSignal.timeout(2000) });
      if (response.ok && (await response.json()).status === 'ready') return;
    } catch { /* A new container or WSL localhost forwarding may still be starting. */ }
    await delay(500);
  }
  throw new Error(`API did not become ready at ${base} within 30 seconds. Start the migrated API first.`);
});
async function get(path) {
  const response = await fetch(base + path, { signal: AbortSignal.timeout(5000) });
  assert.equal(response.status, 200);
  return response.json();
}
test('health and migrated database readiness', async () => {
  assert.deepEqual(await get('/api/health'), { status: 'ok' });
  assert.deepEqual(await get('/api/ready'), { status: 'ready' });
});
test('availability conforms to public contract and capacity invariants', async () => {
  const body = await get('/api/locations');
  assert.deepEqual(Object.keys(body).sort(), ['locations', 'timestamp']);
  assert.ok(Number.isFinite(Date.parse(body.timestamp)));
  assert.ok(Array.isArray(body.locations));
  assert.ok(body.locations.length <= 100);
  for (const location of body.locations) {
    assert.deepEqual(Object.keys(location).sort(), ['available', 'capacity', 'id', 'name', 'occupied', 'outOfService']);
    assert.match(location.id, /^[0-9a-f-]{36}$/i);
    assert.equal(typeof location.name, 'string');
    for (const key of ['available', 'capacity', 'occupied', 'outOfService']) {
      assert.ok(Number.isInteger(location[key]) && location[key] >= 0);
    }
    assert.equal(location.available + location.occupied, location.capacity);
  }
});
