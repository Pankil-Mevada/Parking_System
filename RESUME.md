# Resume here — VehicleParkingSystem

**Latest owner change:** retain databases and committed test records until explicitly
deleted by the owner/admin. The test runner now retains per-run identity realms and
per-case schemas; it no longer truncates earlier cases or removes test databases.
See [database inspection and SMTP setup](docs/DATABASE_AND_EMAIL.md). Start the local
read-only viewer with `py scripts/view_database.py --start` (port 8090).
The owner selected Mailpit for now. Real SMTP is not enabled; the optional helper
`py scripts/configure_smtp.py` requires a Gmail app password entered privately.
Never send synthetic automated test emails through real SMTP.

Last updated: 2026-10-15.
Previous phase 3–4 checkpoint: `f52b6fd96c89bf340eb4c53a2aa28617a4bc1e2f` on `main`.
Current phase 5–6 checkpoint: see `git log -1` and the recorded verification below.
Repository: https://github.com/Pankil-Mevada/Parking_System

**Resume with phase 7: production operations and launch verification.**
Read `AGENTS.md`, this note, and `docs/PHASE_5_6.md` before making changes.
Check `git status --short` first and preserve any newer user changes.

## Phase status

These are the eight implementation steps in AGENTS.md. Completion below refers
to the implemented development scope, not commercial launch readiness.

| Phase | Status | Delivered / remaining |
| --- | --- | --- |
| 1. Inspect project and select stack | Completed | Independent parking repository; TypeScript frontend, owner-selected C++ backend, PostgreSQL |
| 2. Scaffold and local setup | Completed for WSL Docker route | Runnable frontend/API, migrations, placeholder configuration, seed, Python commands and README |
| 3. Authentication, roles and vehicle registration | Implemented and locally tested | Keycloak login, verification, password recovery, OTP; location-scoped roles; own vehicle registration/replacement/disable; database constraints |
| 4. Transactional parking and verification | Implemented and locally tested | Staff check-in/out, idempotency, locks, audit/outbox writes, authorization and concurrency/rollback tests |
| 5. Real driver/staff/admin pages | Implemented; local verification recorded below | Floor summaries, scoped space grid/search, driver current session/history, vehicle dialog, confirmed staff parking controls, admin configuration/staff/users/audit; Chromium journey and basic mobile/keyboard checks |
| 6. Durable realtime | Implemented; local verification recorded below | PostgreSQL delivery ledger, serialized retrying relay across API instances, authenticated finite SSE replay, snapshot cursor, version deduplication, reconnect/backoff/stale states and polling fallback |
| 7. Production operations and pilot | Not completed | Some local health/configuration foundations exist; CI, production security/deployment, metrics, restore/load evidence, runbooks and pilot acceptance remain |
| 8. Hardware integration | Planned by owner; not implemented | ANPR cameras, RFID readers/tags, occupancy sensors, and barrier gates. Device selection/protocols, failure handling, manual overrides, authorization and integration tests remain |

## What works now

- Public aggregate availability, location selection, loading/error/stale states.
- Provider registration/login, email verification, password recovery preserving
  enrolled OTP, session expiry/revocation and MFA checks for parking staff/admins.
- One enabled vehicle per user; one active session per user, vehicle and space.
- Own vehicle dialog with field examples; current session and paginated history UI.
- Location-authorized staff detail reads and confirmed check-in/check-out APIs.
- Location-admin staff assignments and space maintenance APIs with audit records.
- Atomic parking/session, audit, version, outbox and idempotency changes.
- Same-key retries replay original results; changed-body key reuse conflicts.

The sample bay animation is **demo data only**. It never writes a parking session.
Anonymous availability uses 15-second aggregate snapshots. Authenticated dashboards
use finite SSE batches and authorized fresh snapshots. The durable outbox relay now
publishes committed changes. Test users/vehicles/sessions are retained in the separate
test database's case schemas. Inspect them with the database viewer; they are not
normal application records or demo users in the main dashboard.

## Previous phase 5 plan (implemented; kept as checklist)

1. Inspect `frontend/account.ts`, `frontend/main.ts`, `openapi.yaml` and the
   protected C++ routes. Reuse the existing authentication and parking services.
2. Build authenticated navigation and a driver dashboard showing own vehicle,
   location availability, current space/arrival/duration and paginated history.
3. Build the staff space grid/search and vehicle selection workflow. Add any
   missing lookup APIs with explicit location authorization and privacy checks.
   Show empty/occupied/out-of-service text, authorized vehicle/owner information,
   and confirmed check-in/out controls with idempotency keys.
4. Build location-admin pages for locations, zones, spaces, users/vehicles and
   assignments, plus searchable audit records. Add missing scoped administration
   APIs and pagination rather than bypassing the backend with browser state.
5. Test login → vehicle registration → staff check-in → refreshed driver/staff
   views → checkout → availability/history. Add keyboard/mobile checks and useful
   loading, empty, denied, failed and stale states. Never show success before commit.
6. Update OpenAPI, architecture/sequences, README and this note with actual results.
   Realtime uses the phase 6 implementation documented in `docs/PHASE_5_6.md`.

## Current phase 5–6 handoff

Latest verification, 2026-10-15: C++ build and TypeScript/production build passed;
5 frontend/source/replay checks passed; complete phases 3–6 integration/browser
suite **37/37 passed in 161.157 s**; retained-tools checks **8/8 passed in 0.559 s**;
all 6 system-check groups passed. Last run ID
`5a865933-d03f-4475-900e-b038a728b43f`. Local peer replay was 0.068 s; browser driver
update was 0.342 s. These do not establish a staging/load SLA. See the detailed
phase 5–6 guide for commands, architecture, sequences, limitations and screenshots.

- Additive migration 003 creates the durable delivery ledger; apply migrations
  before starting the rebuilt API. `docs/PHASE_5_6.md` has exact commands.
- Initial local administrator: `py scripts/grant_local_admin.py --email YOUR_EMAIL`
  after registering, verifying email, enrolling OTP and signing into the app once.
  Further roles are assigned in the location administrator UI. No default password.
- `py scripts/setup_browser_tests.py` installs pinned Playwright/Chromium locally.
  Keep the frontend on 5173 running, then `py scripts/test_phase34.py` runs phases
  3–6 against retained test schemas and two API instances on 18080/18081.
- Realtime is intentionally finite authenticated SSE batches, normally one second
  apart; details in the design guide. Anonymous aggregates poll every 15 seconds.
- Commercial load/security/restore evidence and comprehensive accessibility/real
  mobile-browser verification remain phase 7. Local timing does not establish a
  staging latency guarantee. Hardware remains planned phase 8.

## Commands to resume locally

Use the existing configured workspace:

```powershell
Set-Location -LiteralPath 'C:\Users\Pankil\Documents\ChatGPT\Parking_System'
git status --short
py scripts/start_dev.py
```

Keep the startup terminal open. Website: http://127.0.0.1:5173.
Provider: http://127.0.0.1:8180. Local captured mail: http://127.0.0.1:8025.
If the port is already occupied, inspect/reuse its existing terminal; do not start
a second frontend or stop unrelated processes.

In a second terminal:

```powershell
py -m pip install --target .tools/test-python -r requirements-test.txt
py scripts/test_phase34.py
py scripts/test_system.py
```

For a fresh checkout or changed backend, follow the complete configuration,
migration and build commands in [docs/PHASE_3_4.md](docs/PHASE_3_4.md).
The identity client redirects and API Origin are currently configured for port
5173; changing that port also requires updating those identity/API settings.

## Last verified results

On 2026-10-14: C++ container build passed; all **28 phase 3–4 integration tests**
passed; all **six existing check groups** passed; Nginx configuration and source
secret checks passed. The earlier cleanup-based harness took 9.850 seconds.
After the retention update, all 28 integration cases passed in 193.777 seconds;
a second run preserved the first run's 28 schemas and history, and eight local
viewer/SMTP/locking safety tests passed. All 19 captured emails were preserved when
Mailpit was moved to persistent storage.
These are recorded results, not a claim that checks were rerun when this note was written.

Coverage includes simultaneous parking/registration/replacement, one-space and
one-user conflicts, cross-location/role denial, MFA, idempotency/retries, duplicate
checkout, maintenance races, forced rollback, verification/recovery and revocation.
The test harness verifies a retained-test-database guard, creates isolated case
schemas, and leaves the databases, committed records and provider realms in place.
It briefly restarts the local identity gateway before/after tests to reset rate
quotas; provider sessions are preserved. There is no automatic database cleanup.

## Preserve these boundaries

- Keep this project independent from FoodService. No deployment or purchases.
- One operator with multiple locations; independent-operator tenant isolation
  has not been implemented or tested. Payments, reservations and guest vehicles
  remain future scope. Cameras, RFID, sensors and gates are planned for phase 8.
- Occupancy is staff-confirmed software data, not proof of physical occupancy.
- Docker Engine runs inside Ubuntu WSL; Docker Desktop is not used. Python is
  tooling, TypeScript is frontend, and C++ remains the backend.
- `.env`, `.tools`, dependencies, backups and generated artifacts stay ignored.
  Never commit real database/provider secrets or production data.
- Local Keycloak uses development mode/H2 and local mail capture. Production
  HTTPS, database/SMTP/secrets, provider-admin MFA/bootstrap removal, least-privilege
  roles, security review, load/restore evidence and operator sign-off remain required.
- No prerequisite was missing for the tested WSL route. Optional native Windows
  compilation still needs MSVC Build Tools and has not been verified.
