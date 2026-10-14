# VehicleParkingSystem

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

Normalization, disabled-user/vehicle eligibility, compatibility, maintenance coordination,
role enforcement and vehicle replacement locks are **phase 3–4 work**, not guarantees from
this scaffold. Do not give drivers or staff direct database access.

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

Only public aggregate endpoints and health/readiness are implemented (see `openapi.yaml`).
The location list is capped at 100; pagination is required before larger installations.
Authentication/recovery/MFA, protected roles and dashboards, vehicle APIs, parking actions,
idempotency handling, administrative corrections, audit write protection, durable SSE,
request IDs, abuse controls, privacy controls and production observability remain future phases.
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
