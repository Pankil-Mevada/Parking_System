# VehicleParkingSystem

**Local hardware simulator:** `python scripts/test_phase34.py --simulator` starts
six synthetic bays, RFID cards, sensor controls and gate faults at
http://127.0.0.1:8766 after live verification. Uses isolated retained test data;
no new simulator application or Wokwi installation is needed.
See [local simulator walkthrough](docs/LOCAL_SIMULATOR.md).

**Latest local workflow:** email/password verification, required Driver/user or
Employee selection, and administrator approval for both account types. Pending
accounts cannot access parking information. Signed-out visitors see only the
product introduction. Approved staff manage driver vehicles and confirm parking
at assigned locations. See the current
[manual guide](docs/ROLE_UI_GUIDE.md). Existing accounts/passwords/history are preserved.

**Driver/staff separation:** admin navigation now separates **Drivers** from
**Staff accounts**. Employees may register and request staff access, then an admin
assigns their location role. Pre-approving an unused employee email remains optional.
Driver accounts with vehicle/parking history cannot be
assigned staff roles. See [employee onboarding](docs/ROLE_UI_GUIDE.md).
Database migration 006 is required; existing assigned staff/admin accounts are preserved.

**Phase 7 is in progress:** [operations commands and explicit launch blockers](docs/PHASE_7.md),
[incident/recovery/pilot runbook](docs/OPERATIONS_RUNBOOK.md), and
`operations/launch-gates.json`. India is confirmed; state and incident/alert owners
are pending. Local metrics, encrypted PostgreSQL restore drills, load measurement,
runtime-role verification and review bundles are implemented. The container
dependency scan reports high/critical matches requiring triage. No launch is approved.

Local recovery now also covers the stopped Keycloak development data volume and
private configuration: `python scripts/recover_local.py`. It briefly pauses the
source API/login service, restarts them, and verifies encrypted backups in separate
retained resources. Use a maintenance window; see the Phase 7 guide for scope and
repeat-restore commands. Authenticated dashboard/SSE load with concurrent parking
actions is opt-in: `python scripts/test_phase34.py --password-only --test-name test_50 --load-concurrency 50`.

For the current screens and manual role-based testing, see
[Driver, Staff and Administrator UI guide](docs/ROLE_UI_GUIDE.md).

Current data/email policy: [database viewer, retained tests and real SMTP setup](docs/DATABASE_AND_EMAIL.md).
Use `py scripts/view_database.py --start` to inspect records at http://127.0.0.1:8090.
Tests now retain case schemas and identity realms; the earlier disposable-cleanup
descriptions below are historical and superseded by the linked policy.

**Start/resume here:** [RESUME.md](RESUME.md) records completed phases, remaining
work and verified tests.

**Current: phase 5–6 dashboards and durable updates.** See
[current setup, UI walkthrough, architecture, sequences and tests](docs/PHASE_5_6.md).
Authentication/MFA, scoped roles and transactional parking remain documented in
[phases 3–4](docs/PHASE_3_4.md).
The phase 1–2 setup and verification history below is retained for context; the
database now needs migrations through 006 and the identity services. Driver,
staff/admin dashboards and PostgreSQL-backed finite SSE batches are implemented.
Phase 7 launch verification and phase 8 hardware integration remain.

After the phase 3–4 setup in that guide, use Python commands:

```powershell
py scripts/start_dev.py
# Keep startup running; use a second terminal for checks:
py -m pip install --target .tools/test-python -r requirements-test.txt
py scripts/setup_browser_tests.py
py scripts/test_phase34.py
py scripts/test_system.py
```

Engineering reference: [architecture and data model](docs/ARCHITECTURE.md),
[sequence diagrams](docs/SEQUENCE_DIAGRAMS.md),
[software design concepts](docs/SOFTWARE_DESIGN.md), and
[review and verification status](docs/REVIEW_AND_VERIFICATION.md).

The public dashboard now includes responsive navigation, availability summary cards,
location selection and a per-location availability breakdown, all driven by the real
aggregate API. The parking graphic is an illustration, not a physical-space map.
An explicitly labelled interactive sample bay lets you preview an arrival/departure;
it changes browser preview state only and never sends a parking write or changes real counts.
Real parking actions still require the later authenticated staff workflow.

See [TOOLS_AND_LIBRARIES.md](TOOLS_AND_LIBRARIES.md) for the dependency inventory,
versions, purposes and installation status.
Use [HOW_TO_TEST.md](HOW_TO_TEST.md) for a short manual and automated phase 1–2 test walkthrough.
For the configured local project, run `py scripts/start_dev.py` and keep that terminal
open, then visit <http://127.0.0.1:5173>. Closing the frontend terminal stops the website.
The startup script keeps an Ubuntu WSL session active for the development session;
systemd services alone do not keep WSL alive. For separate manual startup commands,
keep an Ubuntu terminal open while testing. Vite excludes ignored tool/build directories
from file watching and tool downloads/backups from serving.
On a terminal without Node/pnpm on PATH, use `py scripts/pnpm.py` wherever the commands
below say `pnpm`. This wrapper finds the installed or bundled tools and supplies Node
to pnpm child processes for that invocation only. Windows/user PATH settings are unchanged.
The Python startup script uses this tooling automatically. Run all explained phase 1–2 checks
with `py scripts/test_system.py` while the server is running. Python helpers use the standard
library and invoke Node/WSL directly; the older PowerShell helpers are retained for compatibility.
Docker Engine in Ubuntu WSL still runs the C++ API and PostgreSQL; Docker Desktop is not used.
The test runner checks the real frontend URL first. A successful build does not start a
server: keep the Python startup command running while browsing and testing the site.
If port 5173 is already occupied, the launcher reports it before starting anything and
returns without stopping other processes. Reuse the running page, or stop its original
frontend terminal with Ctrl+C before restarting.

Independent parking project in `Parking_System`. No FoodService code or resources are used.
Phases 1–2 provide runnable source and local infrastructure. Frontend build, C++ container
build, database constraints and API integration checks have passed locally. This is not production-ready.

## Architecture decision

There was no existing application stack. The owner's final instruction, **C++ for backend**,
overrides the earlier TypeScript API baseline. Use a modular C++17 API with Drogon 1.9.14,
TypeScript 5.9 and Vite 7 for the frontend, and PostgreSQL 17. Drogon supplies HTTP routing,
JSON and asynchronous PostgreSQL access; Vite provides a small frontend build without an
unnecessary UI framework. These are maintained upstream projects. References:
[Drogon](https://github.com/drogonframework/drogon),
[Vite supported releases](https://vite.dev/releases),
[PostgreSQL version policy](https://www.postgresql.org/support/versioning/).

The Docker build checks Drogon's release commit `3aae769cc405cf5abb9d477675c6430924f02c7c`;
its submodules are pinned by that commit. `pnpm-lock.yaml` locks frontend dependencies.
Debian/PostgreSQL images are pinned to tested digests. `backend/build-packages.lock` and
`backend/runtime-packages.lock` pin the complete Debian package sets, including transitive
dependencies, for the tested Linux amd64 environment. Docker builds compare installed package
inventories with those locks and fail on drift. If Debian removes a pinned package version,
the build fails rather than silently upgrades; deliberately refresh and retest pins for updates.
This pins dependency versions; it is not a claim of byte-for-byte binary reproducibility.
Frontend calls same-origin `/api`; Vite proxies to the local API. The database is authoritative.
HTTP wiring and aggregate persistence query are separate files; future validation, policy,
transactions and outbox delivery should be separate modules. No personal-data endpoint exists.

Preserved assumptions: one operator with multiple locations; one enabled vehicle per user;
one active session per user, vehicle and space. Occupancy derives from active sessions,
initially confirmed by staff. Out-of-service spaces are excluded from operational capacity.
Vehicle replacement requires checkout and must retain history. Payments, reservations,
guests, cameras, sensors and gates are outside this implementation.

## Prerequisites

- Python 3.12+ for startup/testing helpers. `py --version` reports Python 3.14.0 here.
- Node.js 24 LTS and pnpm 11.25.0. With a normal npm-enabled Node installation:
  `npm install --global pnpm@11.25.0`.
- Ubuntu 24.04 in WSL 2, with systemd, Docker Engine and the Compose plugin. This is now
  the recommended backend/database route. Docker Desktop, a Windows C++ compiler and
  host `psql` are not required. The Windows frontend tools remain available as before.
- Internet access for package installation, container images and the pinned Drogon source.
- Ports 5173, 8080 and 5432 available on localhost.

## Install and run (PowerShell, from this directory)

Docker Engine 29.9.0 and Compose 5.6.0 are already installed directly in Ubuntu WSL.
Docker Desktop is stopped. `scripts/docker_wsl.py` runs commands against Ubuntu's Unix
socket, so Windows Docker Desktop contexts and PATH entries are not used. The bridge
runs Docker as WSL root; no Docker TCP listener or new docker-group membership is configured.

For a fresh Ubuntu 24.04 WSL installation, enable systemd first, then run the included
installer using Docker's official signed apt repository:

```powershell
wsl -d Ubuntu -u root --exec bash /mnt/c/Users/Pankil/Documents/ChatGPT/Parking_System/scripts/install-docker-wsl.sh
```

The installer refuses conflicting container packages rather than removing them. On future
starts, if needed, start the service and verify the engine:

```powershell
wsl -d Ubuntu -u root --exec systemctl start docker
py scripts/docker_wsl.py version
py scripts/docker_wsl.py compose version
```

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

If `.env` still contains placeholders, replace both with the **same** random local password.
The installation task already created a random local password; preserve that existing file.
Use a long alphanumeric value to avoid connection-string escaping. These credentials are
local development only. Compose reads `.env`; the native executable does not parse it.
Never commit `.env`. The local database account is a bootstrap superuser; provision separate
migration and least-privilege runtime roles before staging or production.

```powershell
py scripts/pnpm.py install --frozen-lockfile
py scripts/docker_wsl.py compose up -d db
py scripts/docker_wsl.py compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /workspace/database/migrate.sql'
py scripts/docker_wsl.py compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /workspace/database/seed.sql'
py scripts/docker_wsl.py compose up --build -d api
Invoke-RestMethod http://127.0.0.1:8080/api/ready
py scripts/pnpm.py dev
```

Open <http://127.0.0.1:5173>. Synthetic seed creates six car spaces, five operational and
one out of service, with no accounts or vehicles. The page displays a snapshot from the real
API, offers manual refresh and labels failures/stale data. It does not claim to be live.
For an empty database, skip the seed; the page displays “No locations configured”.

The migration runner holds an advisory lock, checks the migration ledger and commits schema
and ledger together. Re-running it is safe. Never edit an applied migration: add a numbered
migration and a corresponding runner entry. Seed is repeatable and does not reset occupied spaces.

## Checks

```powershell
py scripts/pnpm.py test
py scripts/pnpm.py typecheck
py scripts/pnpm.py build
py scripts/docker_wsl.py compose config --quiet
py scripts/docker_wsl.py compose exec -T db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /workspace/database/tests/constraints.sql'
Invoke-RestMethod http://127.0.0.1:8080/api/health
Invoke-RestMethod http://127.0.0.1:8080/api/ready
Invoke-RestMethod http://127.0.0.1:8080/api/locations
py scripts/pnpm.py test:api
```

`pnpm test` runs three static scaffold checks, not runtime authorization/security tests.
SQL tests exercise enabled-vehicle/registration uniqueness, active occupancy conflicts,
immutable snapshots, checkout/history and required partial indexes. Test fixtures roll back.
They do not prove concurrent transaction behavior; phase 4 must add independent simultaneous
connections and check-in/replacement/maintenance/checkout races.
`pnpm test:api` requires the migrated running API and verifies successful health/readiness,
public response fields, timestamps and capacity arithmetic against the documented contract.
It is deliberately separate from the dependency-free scaffold tests.

Schema includes users, vehicles, locations/zones/spaces, staff assignments, sessions,
audit events, outbox events and idempotency records. Foreign keys prevent dangling entity
references; composite keys bind sessions to vehicle owners and zones to their locations.
Audit targets are polymorphic identifiers. UTC `timestamptz` values are stored; the browser
shows local time. Registration snapshots and checkout history are protected by a trigger.
Partial unique indexes enforce one enabled vehicle per user, unique enabled registration
within jurisdiction, and one active session per user/vehicle/space even under concurrent SQL.

Phases 3–4 now implement normalization, eligibility, compatibility, maintenance
coordination, roles and vehicle replacement locks in the protected API. These
business policies still require that API; database uniqueness alone is not the
whole workflow. Do not give drivers or staff direct database access.

## Native backend alternative

Native Windows verification was requested before the owner selected WSL Docker Engine.
It is not needed for the selected WSL route. On 2026-10-14 the MSVC installer was
started, but Windows cancelled it at the administrator approval step (exit 1602;
bootstrapper log: `0x80070642`, “User may have declined UAC prompt”). The compiler
was not installed, and native compilation/runtime tests remain **blocked**, not passed.
The pinned vcpkg manager and Drogon source were downloaded into ignored `.tools`.

Install the compiler workload (approve the Windows administrator prompt):

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity --override '--wait --quiet --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended'
.\scripts\build-native.ps1
```

The PowerShell 7 build script selects the Visual Studio 2022 x64 compiler, validates vcpkg
baseline `44ccfd88b3eca6929d6d16398c7b19945c29a5f6`, installs `backend/native/vcpkg.json`
dependencies, and builds Drogon 1.9.14 with its pinned Trantor submodule. It produces
`build/native-windows/Release/parking_api.exe`. Framework source, native libraries and
build outputs remain in ignored `.tools`/`build` folders. Native package versions differ
from Debian packages and require their own runtime verification.

Keep PostgreSQL running locally, stop the Docker API to free port 8080, then start native:

```powershell
py scripts/docker_wsl.py compose up -d db
py scripts/docker_wsl.py compose stop api
.\scripts\run-native.ps1
```

The run script reads the existing local `.env` without printing credentials and maps
the container-only database hostname `db` to `127.0.0.1`. An explicitly set
`API_DATABASE_URL` takes precedence. In another terminal run `pnpm test:api`.
Stop native with Ctrl+C and restore Docker with `py scripts/docker_wsl.py compose up -d api`.
This builds the backend for native Windows and uses the existing PostgreSQL container;
it does not install a second database server. Script parsing passed and the build script
correctly reports the missing compiler. Native compilation and runtime tests are unrun.

### Manual native build reference

Install C++17 build tools (MSVC developer shell on Windows, or GCC/Clang), CMake >=3.20,
and Drogon 1.9.14 with PostgreSQL support and its dependencies following the
[official installation guide](https://github.com/drogonframework/drogon/wiki/ENG-02-Installation).
The Dockerfile records the exact Linux dependency/build recipe. With Drogon discoverable
through `CMAKE_PREFIX_PATH`:

```powershell
cmake -S backend -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --config Debug
$env:API_DATABASE_URL='host=127.0.0.1 port=5432 dbname=parking_dev user=parking_local password=REPLACE_WITH_LOCAL_RANDOM_PASSWORD connect_timeout=3'
# MSVC multi-configuration build:
.\build\Debug\parking_api.exe
# For a single-configuration generator, executable is build/parking_api(.exe).
```

## Local operation and scope

`py scripts/docker_wsl.py compose logs api db` shows diagnostics;
`py scripts/docker_wsl.py compose stop` stops services.
`py scripts/docker_wsl.py compose down` removes containers but retains the database volume. Do not remove
the volume unless its data may be destroyed. There is no destructive down migration: for a
shared database, back up and restore or use a reviewed forward migration. Migration compatibility,
restore drills and rollback procedures remain phase 7 work. No deployment command is provided;
there is no production deployment configuration yet. `pnpm build` produces frontend artifacts
only; a production reverse proxy, TLS and artifact rollout are not configured.

Public aggregates, identity configuration and protected phase 3–4 endpoints are
implemented (see `openapi.yaml` and `docs/PHASE_3_4.md`).
The location list is capped at 100; pagination is required before larger installations.
Full role dashboards, administrative corrections, audit write protection, durable
SSE, production privacy controls and observability remain future phases. Identity,
vehicle and parking APIs, idempotency, protected request IDs and local identity
abuse controls are now implemented and tested.
No public response includes owner or registration data. SSE is not implemented.

## Verification recorded on 2026-10-14

- Node.js 24.19.0; bundled pnpm 11.25.0.
- Frozen dependency install passed; esbuild's required build script explicitly allowed.
- Three scaffold tests passed; TypeScript checking and Vite production build passed.
- `git diff --check` passed for tracked changes (new files were still untracked).
- CMake configuration attempted and failed: NMake and a C++ compiler are unavailable.
- Docker, Compose and `psql` not found on PATH: container build, database migration/seed,
  SQL tests, API execution, browser-to-API integration and Compose validation are **unrun**.
- Drogon release tag/commit was verified remotely. No backend compilation is claimed.

These missing prerequisites prevent full phase 2 runtime acceptance. Authentication,
concurrency, realtime, accessibility, security/load verification and operator approval
must precede a commercial launch. Nothing has been deployed or purchased.

### Installation follow-up, 2026-10-14

Docker Desktop 4.95.0 was installed successfully with winget. Docker CLI 29.8.2 and
Compose 5.6.0 were verified. WSL 2.6.3.0 was already installed. Compose configuration
validation passed, and frontend dependency installation/tests/typecheck/build passed again.
Docker's first Linux engine startup temporarily returned HTTP 500 during WSL provisioning;
it subsequently became ready and reported server version 29.8.2. PostgreSQL 17.11 is running.
Migration, seed, safe migration re-run and SQL constraint tests passed. The pinned Drogon/C++
backend image compiled successfully, and both API integration tests passed against the
running API. A deprecated application timestamp formatter was replaced during verification.
The local API and database are left running on localhost ports 8080 and 5432. The frontend
dev server is not left running. A random-password `.env` was created and confirmed ignored
by Git; do not overwrite it with placeholders. A new terminal may be needed for Docker's
PATH entry. Native Windows C++ compilation remains optional and unverified. The focused
browser checks are recorded in the closure section below; full accessibility auditing is
still later-phase work. See the tools inventory for exact installed versions.

### Phase 1–2 closure checks, 2026-10-14

Browser checks passed in the Codex Chromium-based in-app browser: real API aggregate counts,
visible keyboard focus and Enter activation, desktop rendering and a 375 x 812 mobile viewport
with no horizontal overflow. Clearly synthetic browser fixtures verified empty, delayed-loading,
HTTP failure, retained stale snapshot, timeout and recovery states. This is a focused scaffold
check, not a complete accessibility audit or real-device/mobile-browser certification.
Container image digests and complete Debian package sets are now pinned and rebuilt.
Native Windows compilation remains optional and unverified; the recommended Docker build works.
Phases 1–2 are complete for the documented local Docker route. Later-phase acceptance, security,
concurrency/load testing and commercial launch approval remain outstanding.

To reproduce browser state checks without changing the real API or database, start these
two commands in separate terminals from the project root:

```powershell
py scripts/pnpm.py exec node tests/fixtures/browser-api.mjs
py scripts/pnpm.py exec vite --config tests/fixtures/vite.config.ts
```

Open <http://127.0.0.1:5174>. This uses synthetic responses on localhost:8081. In a third terminal:

```powershell
New-Item -ItemType Directory -Path .tools -Force | Out-Null
Set-Content .tools/browser-scenario.txt empty
# Other scenarios: success, slow (4 seconds), failure (HTTP 503), timeout (10 seconds).
```

Refresh the page for each scenario. The frontend aborts requests after five seconds. Stop
both fixture servers with Ctrl+C when done. Use localhost:5173 for the real API page.

### WSL Engine migration, 2026-10-14

The project now runs on Docker Engine 29.9.0 directly inside Ubuntu 24.04.4 WSL, with
Compose 5.6.0, Buildx 0.38.0 and containerd 2.4.2. Docker Desktop was stopped and its
processes were confirmed absent while the WSL API tests passed from Windows localhost.
The daemon reports Ubuntu as its OS and stores its data in Ubuntu's `/var/lib/docker`.

Before switching engines, a consistent PostgreSQL custom-format backup and tested image
archive were saved in ignored `.tools/parking-wsl-transfer.dump` and
`.tools/parking-wsl-images.tar`. The database was restored into a new WSL volume. Verification
found one location, six spaces and migration 001, and SQL constraints plus all five
scaffold/API tests passed. The old Docker Desktop project volume is retained, with its
containers stopped. These engines have separate image/volume stores; restarting the old
Desktop containers would serve an older database copy and conflict with local ports.
Use the WSL bridge for this project. No Docker Desktop uninstallation or data deletion occurred.

The previously compiled Linux API image was initially imported and runtime-tested on WSL.
A subsequent fresh source build on the Ubuntu WSL engine also passed, including compilation
of Drogon and the application and both complete Debian package-lock checks. The freshly
built API was started and both API integration tests passed. Frontend tests/typechecking/build
and SQL constraint tests also passed again. Rebuild with
`py scripts/docker_wsl.py compose build api`. No native Windows compiler is needed.
No service was purchased or remotely deployed. See HOW_TO_TEST.md for the concise walkthrough.

Fresh-start verification also corrected the container's default runtime directory permissions:
the API still runs as UID/GID 65534, with `/var/lib/parking` writable for Drogon's temporary
files and no upload-directory permission errors. API tests now wait for readiness before
asserting responses, avoiding a race with container startup/WSL localhost forwarding.
All five scaffold/API checks passed immediately after recreating the corrected container.
# Account registration and approval

Open http://127.0.0.1:5173/ and select the single header **Sign in / register**
button. New users choose **Register** on the sign-in page, complete registration
and email verification in http://127.0.0.1:8025/, then choose Requested access in
the app: Driver/user, Employee, or Building owner/administrator. Driver and staff
accounts wait for approval. Owner intent shows **Administrator access not
activated yet** and remains an unprivileged employee request until trusted owner
setup assigns real access; choosing the option never creates an administrator role.

An approved administrator opens **Account approvals**, reviews the name/email/type,
selects Approve or Reject and enters a reason. Employee approval also requires an
explicit location role. The applicant clicks **Check approval status** or signs in
again. New driver accounts created by staff require verification and approval by assigned staff or an administrator before parking.

Administrator accounts do not wait for another administrator's approval. Create
the first local owner directly with:

```powershell
py scripts/grant_local_admin.py --email admin@gmail.com --create
```

Open http://127.0.0.1:8025/ and use the setup email to verify and choose a private
password, then sign in directly. There is no default password. The script creates
the parking identity and audited location role without a preliminary app login.
For an existing verified owner account, omit `--create`. This is local development
setup only; public registration never grants administrator privileges. Driver and
Employee accounts still require UI approval. Migration 006 preserves assigned
staff/admin access and requires approval for other existing accounts; data remains.

Unified-entry verification on 19 October 2026: retained password-only run
`6ead72fe-986e-452e-8080-cf153a72118b` passed both the existing driver/staff browser
journey and expanded registration/approval browser checks (32.654 seconds). The
checks cover the provider Register link, driver/staff/owner waiting copy, no roles
from an owner request, pending-access denial and trusted administrator activation.
TypeScript/production build and all 5 source/replay checks passed. Screenshots are
retained under `.tools/browser-results/RUN_ID/`.

Verify this flow: `py scripts/test_phase34.py --password-only --test-name test_48 --test-name test_49`.


### Access queues, building position and session refresh

Administrator **Account approvals** and staff **Driver approvals** open with the
Pending list already loaded. Pending, Approved and Rejected tabs show building
counts; search and pagination work within the selected status. Staff can approve
or reject drivers in their assigned building only. Approval requires confirming
driver identity/building access and entering an audited reason. Employee approval
and staff/administrator role grants remain administrator-only. Previously unscoped
requests remain visible for authorized verification; a decision assigns their
registration building. New registrations select their building (automatic for a
single building), and staff-created drivers inherit the staff-selected building.

**Location settings** accepts an address and paired latitude/longitude. **Use
current location** requests browser permission and fills coordinates; review
these against the building before saving. Manual entry works without location
permission. No external geocoding service receives the address or coordinates.

Driver vehicle cards show a registration plate, vehicle sticker and labelled
make/model/color/type/jurisdiction. Floors and spaces have stickers and explicit
Available, Occupied and Out of service states. In-app notices announce confirmed
space changes, personal arrival/departure and saved approval decisions. These
notifications reflect recorded staff/simulator actions, not physical sensors.

Local password mode uses Keycloak's Cookie SSO execution, falling back to the
password form when no valid provider session exists. Refresh restores the active
workspace route and remembered building while authorization is checked again.
Bearer tokens remain in memory; only interface preferences are stored in session
storage. Expired/revoked sessions still require authentication. Strict production
MFA flow is unchanged.

For an existing local installation, preserve all records and apply:

```powershell
py scripts/migrate_access_location.py
py scripts/configure_identity.py
py scripts/docker_wsl.py compose build api
py scripts/docker_wsl.py compose up -d --no-deps api
py scripts/pnpm.py build
```

Fresh installations use `database/migrate.sql`, including additive migration 008.
Version 007 is deliberately reserved for existing local hardware integration.
Retained verification:

```powershell
py scripts/test_phase34.py --password-only --test-name test_36 --test-name test_48 --test-name test_49 --test-name test_53 --test-name test_54
```

Verified on 19 October 2026: retained local run
`3870a6c1-e992-4a95-b0af-8cdf20799610` passed all five focused integration/browser
tests (55.116 seconds), including refresh for driver, staff and admin, route
restoration, staff verification approval, rejection/history lists, wrong-building
and role-grant denial, automatic/manual coordinates, parking updates and mobile
layout. Local browser arrival-to-driver update measured 0.906 seconds; this is
local evidence only. Frontend production build and all five source/replay tests
passed. Existing main records were preserved by the additive migration.

Strict-MFA regression run `a5b4225d-0f21-40c7-9547-ba56e882671f`
also passed seven tests (28.660 seconds): logout/provider-session revocation,
actual MFA-claim enforcement, scoped role management, administration lookup,
staff driver queues and coordinate validation. Main API readiness and frontend
both returned HTTP 200 after the local update.


### Main-gate plate verification and floor selection

Desktop floor/space cards and form fields use two columns, with a single column
on phones. **Find parking**, **Location overview** and space views expose a floor
selector. A floor card can select that floor or return to all floors.

Staff **Check in a vehicle** and administrator **Check-in / check-out** share the
main-gate workflow. Enter the registration jurisdiction and exact number plate,
then choose **Find vehicle**. The result explicitly identifies not registered,
disabled vehicle, disabled driver, pending/rejected approval, already parked, or
registered-and-enabled eligibility. Eligible vehicles offer a floor selector and
up to 500 compatible available spaces. **Confirm check-in…** rechecks current
eligibility/capacity transactionally before recording arrival. **Reject entry…**
records a gate rejection without changing registration approval or creating a
parking session. Either decision accepts an optional comment and is audited;
retries use idempotency keys. Employee access remains scoped to assigned buildings.

Drivers retain their own vehicle/status view; staff or administrators confirm
physical arrival. These controls record software decisions only. No camera or
physical barrier is operated; camera recognition can supply the plate in a later
hardware integration.

Run retained verification:

```powershell
py scripts/test_phase34.py --password-only --test-name test_36 --test-name test_55
py scripts/pnpm.py test
py scripts/pnpm.py build
```

Gate/floor verification on 19 October 2026: retained password-mode run
`d15dd848-6f74-4b2a-99e5-29443b0c7d9b` passed all five selected tests
(84.317 seconds): role/location authorization, rollback and retry,
check-in-versus-maintenance, full Chromium staff/admin gate journey and API gate
status/decision validation. Browser checks include desktop/mobile layout,
number-plate verification, optional comments, unknown-vehicle rejection and floor
filtering. API checks cover disabled/pending/rejected/already-parked states,
duplicate rejection retries and audited comments. Local arrival-to-driver update
measured 0.890 seconds. All test records and realms are retained.


### Vehicle register and readable building preview

Both **Staff** and **Administrator** have a **Vehicle register** page. It loads
building-scoped records without a search, with vehicle name (make/model), plate,
owner name, type, colour and status. Summary counts include registered records,
enabled, parked here, vehicle disabled, account disabled, pending and rejected.
Status filters, plate/owner/vehicle-name search and pagination are available.
Disabled vehicle history remains visible and is labelled. Records belong to this
building through the owner's registration building or vehicle parking history;
legacy unassigned registrations are included only when there is one building.
Drivers cannot access the register. Gate and space notices include owner names
alongside plates when a registered owner is known.

Location preview shows building name, area, city, country and address/landmark.
Admin **Location settings** uses these editable names instead of coordinate
fields. **Use current location** requests browser permission, then calls
BigDataCloud directly from that browser to suggest locality/city/country. Review
the names and enter the building name/address/landmark before saving. It never
geocodes saved or manually entered coordinates. Manual entry works when location
permission, internet access or the provider is unavailable. The screen links to
BigDataCloud's location policy and explains that the lookup sends the device's
current position. Free client lookup is subject to its current-location-only,
client-side fair use policy:
https://www.bigdatacloud.com/docs/article/why-is-reverse-geocoding-api-free

Browser tests intercept the external lookup with a labelled synthetic response;
no synthetic GPS position is sent to the public provider. Real area suggestions
depend on the network/provider and should be checked by the administrator.
Migration 009 adds area/city/country without deleting data. Existing local setup:

```powershell
py scripts/migrate_access_location.py
py scripts/docker_wsl.py compose build api
py scripts/docker_wsl.py compose up -d --no-deps api
py scripts/test_phase34.py --password-only --test-name test_36 --test-name test_54 --test-name test_56
```

Verified 19 October 2026: retained run
`ce3711f2-733f-403e-8e23-5242c52ade26` passed three integration/browser tests
(45.163 seconds), covering building-scoped register access/counts/status,
owner/vehicle names, readable location preview, simulated browser area lookup,
manual correction and coordinate-validation compatibility. The five source/replay
tests and frontend/API production builds passed. Local main API readiness and
frontend returned HTTP 200 after the additive migration and API update.


### Single saved-location flow

**Location settings** now shows one saved building/address card. **Set building
location** or **Edit saved location** opens a focused picker with **Use current
location**, **Enter address manually**, an address preview and editable building,
area/city/country and entrance/landmark details. **Save location** waits for the
write, reads the saved details back, closes the picker and updates the card.
Cancel discards draft edits. Reopening/reloading displays persisted details.
Choosing manual entry clears any previous device position on save; area names
remain editable. Detection requests are ignored/cancelled when the picker closes.
The location page no longer contains a second form to create another location.
Existing locations, accounts and parking records are preserved.

Saved-location and combined regression verification: retained run
`aab29642-7151-456d-a355-b57ff436e933` passed seven integration/browser tests
(71.347 seconds), including saved-address reload, preview, manual entry,
cancelled drafts, mobile picker layout, approval/role/location boundaries, gate
decisions and the vehicle register. External area lookup remained intercepted by
the browser test. Frontend build, five source/replay checks and tracked-snapshot
secret scan passed. The picker updates the current building; no extra creation
form or location tabs are added.
