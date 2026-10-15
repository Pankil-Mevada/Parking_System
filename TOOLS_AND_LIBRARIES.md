# Phase 3–4 additions

Current phases 5–6 retain the runtime stack below. New testing dependencies are
Playwright 1.63.0, pyee 13.0.1, greenlet 3.5.6 and typing_extensions 4.16.0, pinned
in `requirements-browser.txt`. Chromium is installed in ignored `.tools/browsers`.
No runtime broker or UI framework was added: PostgreSQL holds durable delivery;
native browser dialogs and TypeScript provide the UI. See `docs/PHASE_5_6.md`.

- Keycloak 26.8.1: maintained external authentication provider for email verification,
  recovery, OTP and sessions; local container pinned by digest in Compose.
- keycloak-js 26.2.4: official browser adapter; authorization code with PKCE and
  tokens in memory; exact package and pnpm lockfile.
- Nginx 1.30.5: pinned stable image; local login/recovery request limits.
- Mailpit 1.27.8: pinned local mail capture; verification/recovery tests never send
  mail outside this computer.
- libpq/OpenSSL: existing native dependencies now explicitly linked for parameterized
  PostgreSQL transactions and SHA-256 idempotency hashing.
- Psycopg/psycopg-binary 3.3.6 and Windows tzdata 2026.5: test-only pinned Python
  dependencies installed under ignored `.tools/test-python`.

See [current setup](docs/PHASE_3_4.md). The inventory below records the earlier
phase 1–2 installation and native Windows status.

---

# VehicleParkingSystem — tools and libraries

Inventory checked on 14 October 2026. This document applies only to the independent
`Parking_System` project. Versions below distinguish verified local installations from
dependencies declared for the container build.

## Languages and main libraries

| Item | Version | Purpose | Installation/status |
| --- | --- | --- | --- |
| TypeScript | 5.9.3 | Type-checked frontend code | Installed in project `node_modules`; locked by pnpm |
| HTML and CSS | Browser standards | Accessible page structure and responsive styling | Source files; no extra installation |
| C++ | C++17 | Backend API implementation | Compiled successfully inside backend container |
| Drogon | 1.9.14 | C++ HTTP routing, JSON responses and asynchronous PostgreSQL client | Built and statically linked into the running API |
| Trantor | Pinned Drogon submodule revision | Drogon's event loop/networking and UTC time utilities | Built with Drogon and statically linked into the API |
| PostgreSQL | 17.11, `postgres:17-bookworm` image | Persistent relational data, transactions and database constraints | Downloaded and running locally; migration/seed/constraint tests passed |
| SQL / PL/pgSQL | PostgreSQL 17 dialect | Migrations, constraints, immutable-history trigger and SQL tests | Run by PostgreSQL; no standalone package |

Drogon source is checked against commit `3aae769cc405cf5abb9d477675c6430924f02c7c`.
Exact frontend resolutions and transitive package integrity hashes are in `pnpm-lock.yaml`.
Debian/PostgreSQL container images are pinned to tested digests in Dockerfile/Compose.
Complete Debian build/runtime package versions are pinned in `backend/build-packages.lock`
and `backend/runtime-packages.lock` and checked against installed inventories during build.
These Linux amd64 locks fail rather than substitute unavailable package versions; update
them deliberately alongside image pins and verification results.
Container OS package patch versions are selected at image build time; measured runtime
versions are recorded below. The PostgreSQL client library and server have different major
versions (15.19 client / 17.11 server); this connection passed database/API integration checks.

## Development and build tools

| Tool | Version observed/requested | Why used | Status |
| --- | --- | --- | --- |
| Node.js | 24.19.0 observed | Runs frontend tooling and built-in tests | Available through Codex bundled runtime |
| Python | 3.14.0 via `py`; bundled runtime 3.12.14 also available | Starts local services and runs explained test checks | Installed; new helpers use the standard library only |
| pnpm | 11.25.0 observed and declared | Installs dependencies with a lockfile | Available through Codex bundled runtime |
| Vite | 7.3.7 installed | Frontend development server, local API proxy and production build | Installed in project |
| esbuild | 0.28.2 installed | Vite's TypeScript transformation dependency | Installed transitively; required build script explicitly allowed |
| Rollup | 4.64.6 installed | Vite's production bundler | Installed transitively |
| Node `node:test` / `node:assert` | Built into Node.js | Scaffold checks and separate API integration tests | Available; no testing-library dependency |
| Git | 2.55.0.windows.1 observed | Version control and pinned Drogon source retrieval | Available on Windows |
| CMake | 4.2.0-rc4 observed on Windows; 3.25.1 in container | Configures backend build | Container build passed; Windows native compiler remains absent |
| GCC / G++ and Make | GCC 12.2.0 / Make 4.3 selected during image build | Compile/link C++ backend inside Linux container | Installed in backend build stage; not installed on Windows |
| Docker Engine (Ubuntu WSL) | 29.9.0 | Current local container runtime, independent of Docker Desktop | Installed from Docker's official signed apt repository; running |
| Docker Desktop | 4.95.0 installed; Docker CLI 29.8.2 | Previous runtime | Stopped; not required for the selected WSL route |
| Docker Compose | 5.6.0 | Starts database and backend using `compose.yaml` | Installed and version verified |
| WSL | 2.6.3.0 observed | Linux virtualization backend on Windows | Already installed |
| Ubuntu WSL distribution | Ubuntu 24.04.4 LTS, WSL 2, systemd | Runs Docker Engine directly | Running; daemon uses `/var/lib/docker` |
| Docker Buildx (WSL) | 0.38.0 | Container build plugin | Installed with Engine |
| containerd (WSL) | 2.4.2 | Docker container runtime dependency | Installed with Engine |
| Windows Package Manager (`winget`) | Present; version not recorded | Official package-manager route for Docker installation | Available |
| OpenAPI | Specification 3.0.3 | Documents implemented public API routes | `openapi.yaml`; no generator package installed |
| MSVC C++ Build Tools | Visual Studio 2022 Build Tools 17.14.41 selected | Native Windows C++ compiler and SDK | Installer cancelled at Windows administrator prompt (exit 1602); not installed |
| vcpkg | Tool 2026-09-26; baseline `44ccfd88b3eca6929d6d16398c7b19945c29a5f6` | Pins native Windows dependencies | Downloaded and bootstrapped in ignored `.tools/vcpkg` |

The project deliberately uses plain TypeScript rather than adding a frontend UI framework
at this stage. No authentication library is selected yet because authentication is phase 3.
SSE is a planned delivery mechanism; no realtime library or broker is installed yet.
Python is now the primary startup/test scripting language, not the API language. Use
`py scripts/start_dev.py`, `py scripts/test_system.py`, `py scripts/docker_wsl.py ...`,
and `py scripts/pnpm.py ...`. These helpers do not invoke the PowerShell wrappers.
Existing tests remain JavaScript and SQL where appropriate; Python orchestrates them.

Native Windows libraries are declared separately in `backend/native/vcpkg.json`:
JsonCpp 1.9.6, OpenSSL 3.6.5#1, zlib 1.3.2#2, Brotli 1.2.0 and libpq 18.4#1 at the
pinned baseline. These versions were inspected in the registry, but are **not installed or
runtime-verified yet** because MSVC installation was cancelled by Windows.
`scripts/build-native.ps1` preserves Drogon 1.9.14 and its upstream Trantor submodule rather
than silently substituting vcpkg's older Drogon port. `scripts/run-native.ps1` runs the
result against the existing local PostgreSQL database. Both scripts parse successfully;
native compilation and tests remain blocked on compiler installation approval. The owner
subsequently selected Docker Engine in WSL, which does not require MSVC or those native libraries.

## Backend container system libraries

These packages are installed by `backend/Dockerfile`, not directly on Windows.

| Debian package(s) | Purpose |
| --- | --- |
| `libpq-dev`, runtime `libpq5` (15.19-0+deb12u1) | Official PostgreSQL C client used by Drogon |
| `libjsoncpp-dev`, runtime `libjsoncpp25` (1.9.5-4) | JSON parsing and serialization used by Drogon |
| `libssl-dev`, runtime `libssl3` (3.0.22-1~deb12u1) | Cryptographic/TLS dependency support; application HTTPS is not yet configured |
| `uuid-dev`, runtime `libuuid1` (2.38.1-5+deb12u3) | UUID dependency support |
| `zlib1g-dev`, runtime `zlib1g` (1:1.2.13.dfsg-1) | Compression dependency support |
| `ca-certificates` | Verifies HTTPS certificates when retrieving source |
| `git`, `cmake`, `g++`, `make` | Retrieve and compile the pinned backend framework/application |
| Debian `bookworm-slim` | Build and runtime base image |
| `psql` 17.11 in PostgreSQL container | Applies migrations, seed and database tests |

There is no need to install MySQL, SQLite, Redis, a Windows PostgreSQL server or MSVC for
the recommended Docker route. The native-build alternative requires its own compiler and
Drogon dependencies, as documented in README.

## Commands and package locations

Standard terminal commands after installing Node.js/pnpm into your own PATH:

```powershell
py scripts/pnpm.py install --frozen-lockfile
py scripts/pnpm.py test
py scripts/pnpm.py typecheck
py scripts/pnpm.py build
py scripts/docker_wsl.py compose version
```

Project pnpm wrapper (works without global Node/npm/pnpm when the Codex bundled runtime is present):

```powershell
py scripts/pnpm.py install --frozen-lockfile
```

Frontend packages are local to `Parking_System/node_modules` and are excluded from Git.
The wrapper temporarily adds Node's directory to its process PATH so pnpm lifecycle
commands can find `node`; it restores the caller PATH afterwards. Windows PowerShell
5.1 with Node/pnpm absent from PATH was verified using a real build and scaffold tests.
The package manager's shared download cache is outside the project. Backend libraries and
PostgreSQL are isolated in Docker images/volumes. See README for database setup and run commands.

## Installation and verification status

- Existing frontend dependencies, Node.js, pnpm, Git, CMake and WSL were verified.
- Docker Desktop installation requested using:
  `winget install --id Docker.DockerDesktop --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity`.
- Docker Desktop installer completed successfully. Docker CLI 29.8.2 and Compose 5.6.0
  versions were verified using their installed executables. Docker Desktop was started.
  Its first Linux engine startup temporarily returned HTTP 500 during WSL provisioning;
  it subsequently became ready and reported server version 29.8.2.
- PostgreSQL 17.11 image downloaded and local database started. Schema migration, seed,
  repeat migration and SQL constraint tests passed.
- Backend libraries and final Compose API image compiled successfully. The API is running
  on localhost port 8080; two API integration tests passed, including readiness and capacity
  invariants. The compiler identified a deprecated timestamp formatter; application source
  was updated to its maintained replacement and rebuilt successfully.
- `docker compose config --quiet` passed using process-local validation placeholders.
- A git-ignored `.env` was subsequently created with a cryptographically random local
  password to start the local database. The password was not printed or committed.
- Frozen frontend installation, three scaffold tests, TypeScript checking and production
  build passed during this installation task.
- No services were purchased and no application was deployed.
- Closure browser checks passed for the real public availability page, keyboard refresh,
  desktop/mobile viewport layout and synthetic empty/loading/failure/stale/timeout/recovery
  states. Fixtures are isolated in `tests/fixtures`; no real database data was changed.

The current engine runs directly in Ubuntu WSL. Use `py scripts/docker_wsl.py info` from
PowerShell, or `sudo docker info` inside Ubuntu. Docker Desktop's Windows CLI is not used
by the bridge. No WSL reset, volume deletion or computer restart was performed.

Local services left running: `vehicle-parking-system-api-1` (127.0.0.1:8080) and
`vehicle-parking-system-db-1` (127.0.0.1:5432), now on Ubuntu's own Docker Engine.
Stop them with `py scripts/docker_wsl.py compose stop`.
The frontend development server is not left running; start it with `pnpm dev` using
the bundled pnpm path above if pnpm is not on your terminal PATH.

## Upstream references

- [Drogon source and documentation](https://github.com/drogonframework/drogon)
- [Vite documentation](https://vite.dev/guide/)
- [PostgreSQL documentation](https://www.postgresql.org/docs/17/)
- [Docker Desktop Windows setup](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Docker Engine Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/)

Docker Desktop is stopped and no longer required by this project. Its former database
volume is retained; the database was backed up/restored into WSL and verified. All five
scaffold/API tests and SQL constraint tests passed while Desktop was stopped. No paid
subscription was purchased. The existing Linux API image was initially imported into WSL;
a subsequent fresh source build on the WSL daemon passed, including Drogon/application
compilation and both package-lock checks. The newly built API passed its two integration tests.
Frontend tests/typechecking/build and SQL constraint tests passed again. See HOW_TO_TEST.md
for exact commands and expected results.
