# Resume here — VehicleParkingSystem

GitHub checkpoint prepared 2026-10-15: account type selection, mandatory driver/
employee approval, direct owner-admin setup, product-only public UI, name/email
search, migration 006, updated API contract and regression/browser tests.
Most recent owner-requested reset removed all three development login accounts
and associated parking records, cleared Mailpit and restored six demo spaces.
Isolated test databases and backups remain. Current admin setup command is
`py scripts/grant_local_admin.py --email admin@gmail.com --create`; omitting
`--create` expects an existing verified provider account. No automatic reset.
Earlier setup/test notes below are historical checkpoints, not current user data.

Administrator clarification: owner-provisioned admins do not require another
admin's approval. Latest requested reset removed admin@gmail.com; inspection
confirmed no provider/app identity existed. Added local-only `--create` to
grant_local_admin.py: create identity if missing, grant audited location role
before first app login, and send Mailpit verification/private-password setup.
No default password; verification remains enforced. UI distinguishes direct
administrator sign-in from pending Driver/Employee registration. Executed local
setup for admin@gmail.com; approved/employee/operator_admin verified in DB.
Owner must complete the Mailpit setup link and choose their private password.
Frontend build, 5 frontend checks and 2 API smoke checks passed. No data reset.

Mandatory approval workflow (supersedes earlier onboarding notes): migration 006
adds registration_kind and pending/approved/rejected approval_status. New driver
and employee accounts require an explicit type selection and admin decision.
Pending accounts can only read /api/me, submit type once, or logout; all parking
APIs and SSE batches require approval. Target driver must also be approved before
vehicle writes/check-in. Signed-out frontend is a product introduction and does
not fetch locations. Admin Account approvals approves/rejects registrations and
assigns employees an explicit role at the selected location. Bootstrap helper
approves the first local owner; no public administrator signup. Existing assigned
staff/admins preserved, other accounts made pending without deleting history.
C++ and frontend builds, 5 frontend checks and 2 API smoke checks passed. Local
password-only run 1ae77180-49a3-4e05-9576-7576b94f6d5f passed tests 43/48/49
(15.359s); browser coverage includes product-only landing, type selection and
pending screen. Full strict run 2b97b816-bc0e-48fa-b4f2-f13a62025e94 ran 49:
46 passed, 1 password-only skip, and 2 affected cases initially failed. Updated
the old pending-access expectation and replaced reload with in-page status checks
to preserve authentication. Both affected tests 39/49 then passed in retained
strict run 3b878b76-ad81-49be-940b-ecf0910d1783 (17.235s), including actual admin
UI approval and transition into the assigned staff workspace. Final pagination
and name/email-filter tests 42/48/49 passed in password-only run
6d100d34-f0ae-4453-ba83-abcf8a9064d3. That run exposed a browser-test wait race
at the emailed password-setup redirect in test 36; corrected the wait. Targeted
password-only test 36 passed (26.861s), retained run
0d813866-b01d-4670-ae32-4e18fd5b89c7. No remaining observed failures. Local code
and documentation changes are unpushed. Development admin remains approved;
staff@gmail.com is pending and must select Employee and submit its request.

Admin onboarding correction: Add / approve an employee account now accepts an
already registered enabled identity only if it has no vehicle/session history.
Enrollment creates a pending employee profile; location role remains a separate
admin action. No account was automatically promoted. C++/frontend builds passed;
test 47 passed (5.257s), retained run 79793899-aaba-4b2e-b32d-00074741b0d9,
proving denial before assignment, admin-only enrollment and driver-history guard.

Owner correction: staff@gmail.com must await administrator assignment. Removed
the temporary attendant assignment and audited revocation; employee profile stays
listed for admin approval. Pending employees now see only a waiting screen,
refresh/sign-out, with no driver/staff menus or location/workspace selectors.
Frontend build passed. Administrator must assign role through Staff accounts.

Name/email lookup: driver lookup now accepts exact email or a name substring
(minimum two characters, maximum 20 results); admin staff list has name/email
filtering. Employee accounts remain excluded from driver search. C++ and frontend
builds passed; retained password-only run `4502b212-9afa-4850-8364-4a66bac86ffb`
passed tests 43 and 46 (9.593s), including role/location denial and injection text.
Owner-identified staff@gmail.com had no staff profile after the requested reset;
confirmed no vehicle/session history, then assigned attendant at Demo parking
location with an audit event. Driver and admin records preserved. Local, unpushed.

Driver/staff separation UI correction: normal driver pages no longer show the
staff-access request button. Employee enrollment is available only through the
separate staff-signup flow, preserving its intent through login. Browser test
asserts the driver has no staff request control and verifies separate employee
enrollment. TypeScript/build passed; password-only browser run
`de282ef5-aed0-4c02-b391-ef42cd07e619` passed (34.330s). Local, not yet pushed.

Latest product UI change: only the header has **Sign in / register**; the duplicate
account/vehicle button is removed. Direct header login/logout wiring verified by
real password-only browser run `033ac3cd-ded6-443d-a8aa-d867d5d510b3` (passed,
32.548s), which asserts exactly one sign-in entry before login. TypeScript/build
and 5 frontend checks passed. This change is local and not yet pushed.

Checkpoint prepared for check-in on 2026-10-15. Use `git log -1 --oneline` for the
exact commit containing this note. Current manual steps are in `docs/ROLE_UI_GUIDE.md`.
Resume phase 7 from its visible blockers in `docs/PHASE_7.md`; phases 1–6 are locally
implemented, phase 7 remains partial, and phase 8 hardware remains planned.

Latest owner request: remove Microsoft/other authenticator-app requirement locally,
keep verified email/password login, let staff create driver accounts and manage
driver vehicles, and allow staff signup before administrator assignment.
Implemented local `parking-password` flow with `REQUIRE_STAFF_MFA=false`; normal
realm configured and old pending CONFIGURE_TOTP actions removed without deleting
credentials/accounts. Strict MFA mode remains testable and production-gated.
New staff page: **Driver accounts & vehicles**, with real Keycloak driver creation,
Mailpit setup email, driver lookup/vehicle registration/replace/disable. Dedicated
server-only `parking-driver-provisioner` client uses its own ignored secret. Account
creation retries are keyed; partial provider/email failures retain accounts and
same-key retries continue setup. New POST `/api/me/staff-application` lets an
explicit employee request be approved by the administrator after registration;
any driver vehicle/session history blocks conversion. No staff self-assignment.
See updated `docs/ROLE_UI_GUIDE.md` for exact manual steps.
Verification: strict baseline run `6259ad0a-984f-4e8e-b886-682835c83330`
ran 45 tests: **44 passed, 1 intentionally skipped** (password-only test), 210.898s.
Password-only run `b5a4ba1a-5fc8-4d10-846b-8543d29d9ef9`: **7 passed**, 52.957s,
including actual Chromium setup-email/password flow, staff signup after registration,
driver vehicle management/status, location denial and retained email-failure retry.
Frontend build, 5 Node checks and 4 operational checks passed. Runtime audit/schema
restrictions remain verified. No account, database or committed test record deleted.
Final provisioning account-status lock guard rebuilt and checked in password-only
run `f6bee67f-957e-4130-bfeb-00a207ba4887` (`test_43` passed, 5.131s). Normal local
API is running this final image; readiness/monitor report healthy with no alerts.

Vehicle-registration error improvement: duplicate enabled plate/jurisdiction now
returns `vehicle_registration_already_in_use` with actionable UI guidance; no owner
information or raw SQL diagnostics are exposed. Rejected replacement rollback
verified by `test_41` (passed, 5.603s), retained run
`170a5a3e-353e-4fbf-8aa6-9a455d8b61a6`. C++ and TypeScript builds passed.

Earlier account-separation checkpoint (refined by the workflow above): migration 005 adds approved
employee identities and a foreign key preventing staff assignments to non-employees.
Admin pages are now **Drivers** (account/vehicle management only) and **Staff accounts**
(approve unused email, await verified first login, select location role). Public
registration never exposes a privilege selector. New employee vehicle registration
is rejected; existing assignments/history are preserved. See `docs/ROLE_UI_GUIDE.md`.
Verified run `6f48aa3d-30ff-403a-af25-3b80debb67b4`: **40 integration tests passed**
in 162.090s, including real-browser employee onboarding/assignment, driver exclusion,
database foreign-key rejection, cross-location denial and email-change protection.
TypeScript/build and 5 frontend checks passed; 4 operations checks passed. Migration
005 applied and safely reapplied locally. Runtime grants refreshed without rotating
credentials; audit mutation/schema creation remain denied. Test realms/data retained.

**Current work: phase 7 is partially implemented, not complete or launch-ready.**
Read `docs/PHASE_7.md` and `docs/OPERATIONS_RUNBOOK.md` first. India is confirmed;
500 concurrent users is the confirmed main load-test target.
State/alert/incident owners remain pending. Only the
public-read baselines have run. The 500-client local run completed 14,468 requests
with zero errors in 31.446s (460.09 requests/s), p95 1.811s, p99 7.303s, peak 500
in-flight requests. Authenticated/write/SSE load and staging acceptance remain.
Report: `.tools/load-results/107890f5-cf21-4fe1-810c-0a81bc6fb958.json`.
New local tooling: private API metrics, structured request logs, client heartbeats,
secret-file configuration, native launcher auth configuration, checksum-pinned
age/Grype installers, encrypted PostgreSQL backup/isolated retained restore drill,
least-privilege runtime login and verification, bounded load runner, dependency
scanner, release review bundles and a manual dedicated-runner CI workflow.
No database records were deleted, no deployment performed, and no new push made.

Latest regression run `5bfa2755-bdaa-478e-8041-59e6169796f4`: **37 passed** in
161.344 seconds; local browser arrival update 0.831 seconds, peer replay 0.078 seconds.
Operations tests: **4 passed**. Three-user provisional read load: 262 requests,
zero errors, p95 35.124 ms. Encrypted restore verified all table counts in 31.218s,
database `restore_860e59548b034e2e9f7c43ba0fab99fc`, retained separately.
This restore excludes Keycloak H2. Runtime-role checks deny audit mutation/schema creation.
API image dependency scan **failed**: raw Grype matches include 8 critical and
90 high matches (not independently confirmed exploitability); pnpm audit passed.
Reports retained at `.tools/security-results/e5659983-e859-4d65-86a9-02c1d1d1e439`.

Resume priorities: triage/remediate container findings; finish full identity recovery,
production TLS/secret configuration and staging rollback verification; activate CI
with lint/secret scans; verify full API flow under runtime login; agree load/recovery
targets and owners; final security/access/privacy reviews and physical operator pilot.
Do not mark phase 7 complete while these gates remain open. Hardware remains phase 8.

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

**Continue phase 7: production operations and launch verification.**
The latest UI refinement separates driver/staff/admin sidebar screens and hides
the public demo after sign-in. See `docs/ROLE_UI_GUIDE.md`; this changes navigation,
not backend permissions or parking invariants.
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
| 7. Production operations and pilot | Partially implemented; launch blocked | Local metrics/logs, encrypted PostgreSQL restore, runtime login checks, provisional load results, review bundle and manual CI source; dependency triage, full identity recovery, production/staging setup, CI activation and operator acceptance remain; see docs/PHASE_7.md |
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
