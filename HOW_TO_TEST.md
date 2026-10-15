# Current authentication and parking tests

**Phases 5–6:** [dashboard and realtime test guide](docs/PHASE_5_6.md).
Keep the frontend running on port 5173, run `py scripts/setup_browser_tests.py`
once, then `py scripts/test_phase34.py` for the complete phases 3–6 integration
suite, including Chromium driver/staff/admin flows and two API instances.
Run the retained-tools safety suite after that finishes, not concurrently:
`py -m unittest discover -s tests -p test_retained_tools.py -v`.

**Updated:** tests retain each case's database records and provider realms. Open
the [database/email guide](docs/DATABASE_AND_EMAIL.md) for the read-only viewer and
new retention behavior. Earlier temporary/deleted-fixture descriptions are historical.

For phases 3–4, use [the current setup and test guide](docs/PHASE_3_4.md).
After installing its test prerequisites, run `py scripts/test_phase34.py`.
It tests real provider login/MFA, separate PostgreSQL connections, competing parking
requests, location permissions, idempotency and rollback in disposable test services.
The phase 1–2 guide below remains useful for the public page and scaffold runner.

---

# Test phases 1 and 2

These phases cover project inspection, architecture choice and a runnable scaffold:
TypeScript frontend, C++ API, PostgreSQL schema/migrations, local setup and documentation.
Login and vehicle registration were later work at this checkpoint and are now
implemented as described above. Full role dashboards and realtime remain later
phases. The public availability page still shows an aggregate snapshot.

Tests are checks that catch different problems. No single test proves the whole product works:

| Check | In plain language | What a pass tells you |
| --- | --- | --- |
| Website running | Open the real website URL and its API proxy | The frontend is running and can reach the API |
| Project scaffold | Inspect selected rules in the source files | Those basic code rules are present |
| Frontend build | Compile and package the website | TypeScript/build tools accept the code |
| Running API | Ask the actual server for availability | The server and database answer, counts add up, public fields are limited |
| Database rules | Try to insert invalid parking records | The database rejects tested conflicts; temporary records are rolled back |
| Launcher tools | Simulate missing Node and duplicate starts | The Python helpers handle those startup problems |
| Your browser checks | Look at the page and click Refresh | You can use the visible page; automated build tests do not prove this |

Docker Engine is still used inside Ubuntu WSL to run the C++ API and PostgreSQL.
Docker Desktop is not used. Python now starts the tools and runs the checks; it does
not change the TypeScript frontend or C++ backend. No extra Python packages are needed.

Phase 1 is complete: this project was inspected independently, and stack/assumptions are
recorded in README. Phase 2 is complete for the selected WSL Docker route: runnable source,
migrations, configuration and local commands are in place. A fresh WSL source build, frontend
build/typechecking, three scaffold checks, two API checks and SQL constraint tests passed on
14 October 2026. This is scaffold completion, not completion of the whole commercial product.

## 1. Start the local API and database

Quick start for the already configured project:

```powershell
Set-Location -LiteralPath 'C:\Users\Pankil\Documents\ChatGPT\Parking_System'
py scripts/start_dev.py
```

Keep this terminal open and visit <http://127.0.0.1:5173>. This starts the WSL Docker
service, backend/database containers and frontend. If the frontend terminal is closed,
the website stops accepting connections; run this command again. The frontend uses a
fixed port and reports a conflict instead of silently moving to another port.
The startup script holds a WSL session open while running, because systemd services
alone do not keep Ubuntu alive. Ctrl+C releases that session. If you follow the separate
startup steps below, keep an Ubuntu WSL terminal open as well. Downloaded `.tools`
directories are excluded from frontend scanning and serving.
If you run the startup command twice, it reports that port 5173 is already in use and
returns without launching a second server or stopping any process. Use the already-running
page, or press Ctrl+C in its existing frontend terminal before starting it again.

Expect the API to be running on `127.0.0.1:8080` and the database to be healthy on
`127.0.0.1:5432`. Docker Desktop can remain closed. Keep the existing `.env`; do not
replace its generated password with the `.env.example` placeholders.
For a first source build, use `py scripts/docker_wsl.py compose build api`.

## 2. Start and inspect the website

The startup command already starts the website. Do not launch a second frontend.
If your older PowerShell startup script is running, keep using that session now;
switch to the Python startup command next time after stopping it with Ctrl+C.
Visit <http://127.0.0.1:5173>.

With the supplied synthetic seed, expect:

| Field | Expected value |
| --- | --- |
| Location | Demo parking location |
| Available | 5 |
| Occupied | 0 |
| Out of service | 1 |
| Operational capacity | 5 |

Click **Refresh availability**: the last-updated time should change and the counts
should stay the same. Press Tab to focus the refresh button, then Enter to refresh.
Inspect a narrow browser window: text and cards should fit without horizontal scrolling.
The page should describe its data as a snapshot, with no claim of live occupancy updates.
The current account section supports login and own-vehicle registration. Staff
parking actions are currently APIs; their full dashboard controls remain phase 5.

The redesigned dashboard also has a separate **Interactive demo · Sample data** section.
Click **Preview arrival**: its demo bay becomes Occupied and shows a sample car. Click
**Preview departure**: it becomes Empty. The real Available/Occupied cards must stay
unchanged (5/0 with the supplied seed). No database write occurs, and reloading resets
the preview. This is an illustration of the future workflow, not a real staff check-in.

Where are the test vehicles? `database/tests/constraints.sql` creates them inside a
transaction and rolls that transaction back. They never persist on the dashboard.
`database/seed.sql` creates the visible demo location and six spaces, but no vehicles
or active parking sessions. Actual vehicle status changes are later-phase functionality.

## 3. Run automated checks

In a second PowerShell terminal, from the same project directory:

```powershell
py scripts/test_system.py
```

This prints the explanation before each check and a `PASS` message after it succeeds.
The first check requires the actual website on port 5173. Running tests or building
files does not start a web server. Keep `py scripts/start_dev.py` running in the first
terminal while running tests in the second. Closing that first terminal makes the
browser show connection refused even if the API/database are still running.
Expect three scaffold checks, a successful TypeScript/production build, two API tests,
`Constraint tests passed; fixtures rolled back.`, and four Python tooling regression checks.
One regression performs the full frontend build with both Node and pnpm absent from the
terminal PATH. The build uses local compiler/bundler commands, without a nested pnpm call.
It stops on the first failure; copy that error when asking for help.
The API tests wait up to 30 seconds for database readiness to allow container startup
and WSL localhost forwarding to settle. An unavailable API still fails with a clear error.
SQL tests exercise enabled-vehicle/registration uniqueness, active occupancy conflicts,
immutable history and checkout behavior. Simultaneous transactions and role authorization
are phase 4 tests and are not proved by this suite.

The API tests already check `ok`, `ready`, and aggregate response fields. No owner details
or vehicle registrations should appear in the public response.

## 4. Check failure and recovery

```powershell
py scripts/docker_wsl.py compose stop api
```

Refresh the page. Expect a disconnected message; if you previously loaded a snapshot,
the old counts must be marked stale. The refresh button must become usable again.

```powershell
py scripts/docker_wsl.py compose up -d api
```

Refresh again and expect a successful snapshot. This does not remove database data.
For empty/loading/timeout scenarios using synthetic fixtures, see the browser-check
instructions in README; they do not change the real parking database.

## 5. Stop when finished

Press Ctrl+C in the frontend terminal, then:

```powershell
py scripts/docker_wsl.py compose stop
```

The local database volume is preserved. Full setup, migrations and dependency details
are in README and TOOLS_AND_LIBRARIES.md.
