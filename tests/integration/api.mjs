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
test('parking locations require authentication', async () => {
  const response = await fetch(base + '/api/locations');
  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), {error:'authentication_required'});
});
