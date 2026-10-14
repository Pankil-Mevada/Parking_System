# Use this parking specification with Codex

## 1. Use the existing parking repository
The documentation is already in the local clone of:
https://github.com/Pankil-Mevada/Parking_System

Local directory: C:\Users\Pankil\Documents\ChatGPT\Parking_System

Open this directory as a separate Codex project. No file copying or git init is
needed. The files are currently local changes; review before committing them.

```powershell
Set-Location -LiteralPath 'C:\Users\Pankil\Documents\ChatGPT\Parking_System'
git status --short
git add AGENTS.md HOW_TO_USE.md
git commit -m 'Add parking product and engineering requirements'
```

To publish the commit to your existing GitHub repository when ready:

```powershell
git push -u origin main
```

## 2. Open the folder as a Codex project
Open the destination folder in Codex and start a new chat there. Codex loads
AGENTS.md as project instructions. Ask:

```text
Summarize the AGENTS.md instructions you loaded. Confirm this is the independent
VehicleParkingSystem project. List the one-vehicle and parking concurrency rules.
```

## 3. Generate the first working code
Paste this prompt in that chat:

```text
Follow AGENTS.md. Implement phases 1 and 2 for the vehicle parking system.
Use TypeScript for the frontend/API and PostgreSQL unless existing code dictates
otherwise. Select maintained packages and explain the choice briefly.
Create actual runnable source code, migrations, .env.example with placeholders,
local database setup, and README with exact install/run/test commands.
Include one enabled vehicle per user and one active session per user, vehicle,
and space as database constraints. Keep this project separate from FoodService.
Run the available checks and report prerequisites that are missing.
Do not deploy or purchase services.
```

Do not run invented npm commands before scaffolding exists. Follow the generated
README for the actual package manager, environment variables, and database setup.

## 4. Implement core functionality

```text
Follow AGENTS.md and implement phases 3 and 4: authentication, roles, vehicle
registration, transactional staff check-in/check-out, and idempotency.
Write database concurrency tests proving that simultaneous requests cannot give
one space to two vehicles or let one user park two vehicles. Test cross-location
authorization and rollback. Run the tests and report the results.
```

## 5. Build the website and realtime updates

```text
Implement phases 5 and 6 from AGENTS.md using the real API. Show a responsive
empty/occupied/out-of-service space grid. Authorized staff can see who parked,
which vehicle, and arrival time; drivers see only their own personal details.
Add SSE backed by the transactional outbox, reconnect/resync, stale indicators,
and polling fallback. Test event privacy and simultaneous browser updates.
```

## 6. Prepare and verify a pilot release

```text
Implement phase 7 from AGENTS.md. Add CI, deployment configuration, migration
and rollback documentation, monitoring, backup/restore steps, and a pilot
acceptance checklist. Identify launch blockers with evidence. Do not call the
product production-ready until the required checks and operator review are done.
Do not deploy yet.
```

## 7. Manually verify the business rules
Create two test drivers and one attendant in a local/staging environment. Register
one vehicle for each driver. Confirm a second enabled vehicle for the same driver
is rejected. Check the first driver into a space and verify two browser windows
update. Attempt to check the same driver into another space and the other driver
into the occupied space; both must fail. Check out and confirm availability and
history. Verify drivers cannot access other owners' details via API or SSE.

## Understanding the SQL example
The partial unique indexes in AGENTS.md enforce the business rules even under
concurrent requests. They must be included in real migrations after tables exist.
They do not replace transactions, ownership checks, or role authorization.

AGENTS.md guides code generation; it is not executable software. The generated
application still needs validation, staging, operational preparation, and a pilot.
