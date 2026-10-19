# Parking System resume checkpoint

Updated: 2026-10-19 (Asia/Calcutta).

Source: https://github.com/Pankil-Mevada/Parking_System/tree/main
Baseline commit: `9447dd1ab932b8642ab8ad4f38cca3924e3a80c6`.
Local branch: `codex/phase-5-6`.

## Current focus: local Phase 7 implementation and verification

Latest UI improvement: one header **Sign in / register** entry for all users.
Duplicate **Create account** button and pre-login registration dialog removed.
New users register through the provider and choose requested access after verification.
Driver/staff waiting messages explain approval; owner intent explains trusted
administrator activation and remains an unprivileged employee request on the server.
Frontend port 5173 now serves this `Parking_System 2` checkout. Production build
and 5 source/replay checks passed. Retained run
`6ead72fe-986e-452e-8080-cf153a72118b` passed 2 browser cases in 32.654 seconds:
existing driver/staff parking and unified registration with all pending states,
no owner self-grant, denied parking access before approval and trusted activation.

Latest owner-requested main-data reset completed on 2026-10-19: zero main login
accounts, app users, vehicles and parking sessions; one building and six spaces
retained. Encrypted pre-reset checkpoint: `ac5e61a7-f8dd-47f9-b5ca-0655030ea69a`.
Main API readiness and six retained simulator bays were verified. No administrator
was recreated. Use trusted owner setup in `scripts/grant_local_admin.py --create`
before onboarding staff/drivers. Simulator is stopped; test data and backups remain.

Owner-requested hardware simulation was verified at http://127.0.0.1:8766.
Run `7ea7a5eb-7637-4515-9cea-dab64724725c` passed 5 standalone device tests and six
live integration/browser groups, including real API writes, peer SSE, replay,
denied cards/gate faults and sensor reconciliation. Six synthetic bays are retained;
P02 starts occupied and P03 has a deliberate mismatch. See `docs/LOCAL_SIMULATOR.md`.
The simulator holds the retained-test lock while running; stop it before other
integration suites. No physical hardware or Wokwi has been installed.

- Phase 5 is implemented in the baseline: driver, staff and administrator screens,
  vehicle and account workflows, location authorization and confirmed parking actions.
- Phase 6 is implemented in the baseline: PostgreSQL delivery ledger, transactional
  outbox relay, authenticated finite SSE batches, replay, reconnect and stale states.
- Historical runtime verification is documented in `docs/PHASE_5_6.md` and `RESUME.md`.
  It has not yet been reproduced in this checkout.
- Later onboarding changes require explicit Driver/Employee selection and administrator
  approval. Owner administrators use trusted local setup. Local login uses verified
  email/password; normal email is captured in Mailpit. Follow AGENTS.md and the latest
  RESUME.md entries when older documentation differs.

## Checks performed in this checkout

- Retrieved main into the previously empty workspace.
- `node --test tests/*.test.mjs`: 5 passed, 0 failed.
- Node version: 24.19.0.
- Existing local `.env` was recovered privately from the original parking checkout.
  Python launcher `py` could not execute, but the bundled Python runtime works.
  Locked frontend install, TypeScript/production build
  and Python syntax compilation passed (an existing bootstrap docstring warning remains).
- Phase 7 continuation adds automatic isolated source/build CI, a redacted tracked
  snapshot secret scanner and scanner regression tests. GitHub execution is unverified.
- Local API checks: 2 passed. Operational tests: 4 passed. Recovery safety tests:
  3 passed. Added authenticated dashboard/SSE load with concurrent parking writes.
- Encrypted recovery checkpoint: `a7d37010-f3db-4a0d-a5f8-c00df23d24c1`.
  Successful isolated restore: `bf2ba638dc0f4498839bfd094bdc944c` (316.719 seconds).
  Parking table counts, all 41 realms/420 identity IDs, administrator password login
  and application-service credentials verified. Failed attempts and their data are
  retained. Source restarted and recovered duplicate stopped.
- Frontend audit reported zero findings. API image scan was interrupted to relieve
  low memory; no accepted image-scan result exists from this continuation.
- No accounts, databases or retained test fixtures were reset.

## Resume steps

1. Serialized browser/password-login/authenticated-load verification passed:
   `380f1ced-2617-470f-a287-ecfbaec53a40`, 3 tests in 167.355 seconds. With 50
   simulated authenticated clients, 496 reads completed with zero errors while
   check-in/out succeeded; p95 2391 ms, peak 48 requests in flight. Clients shared
   a synthetic identity; this does not meet or establish the 500-user target.
   Browser arrival-to-driver update measured 1.578 seconds locally. Initial
   concurrent setup timed out under memory pressure; its retained run is
   `a055ca07-dc11-4759-a5f9-942a5d0b4250`. The runner now records early setup failures.
   Optimized single-call table count verification also passed on fresh retained
   database `restore_dafdbf680b6d4a9a906b551565ed9491` (39.329 seconds).
2. Complete dependency-image triage/scanning with sufficient memory; preserve reports.
3. Verify the full app against both recovered services, including end-user browser
   password/OTP flows; move production identity persistence off development H2.
4. Continue local deployment/rollback, acceptance and pilot preparation. Hosting and
   operator decisions remain later gates; they do not block local development.

Phase 7 remains partial; phase 8 hardware remains planned. This checkpoint creates
no scheduled monitoring and makes no production-readiness claim.
