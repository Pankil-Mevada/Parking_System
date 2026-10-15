import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const read = path => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
test('public query returns aggregates without selecting driver identity', () => {
  const source = read('backend/src/availability.cpp');
  assert.match(source, /checked_out_at IS NULL/);
  assert.match(source, /operational_status='enabled' AND p.id IS NULL/);
  assert.doesNotMatch(source, /JOIN users|JOIN vehicles|registration_snapshot|identity_provider_reference/);
});
test('frontend uses safe text rendering and bounded requests', () => {
  const source = read('frontend/account.ts') + read('frontend/dashboard.ts');
  assert.doesNotMatch(source, /innerHTML|localStorage/);
  assert.match(source, /AbortController/);
  assert.match(source, /data may be stale/);
});
test('migration runner serializes and records transactional migrations', () => {
  const source = read('database/migrate.sql');
  assert.match(source, /pg_advisory_xact_lock/);
  assert.match(source, /ON_ERROR_STOP on/);
  assert.match(source, /BEGIN;[\s\S]*INSERT INTO schema_migrations[\s\S]*COMMIT;/);
});
