# Checkpoint review and verification

Historical phase 1–2 review. Current phase 3–4 verification is recorded in
[the current implementation reference](PHASE_3_4.md).

Review date: 2026-10-14. Scope: this parking repository's current uncommitted
application scaffold, dashboard, database schema, tooling and documentation.
This is a source review and local verification, not an independent security audit.

## Review outcome

The source is suitable for a phase 1–2 development checkpoint. Public availability
uses database aggregates and does not return owner/registration details. The UI
uses safe text rendering, validates responses and marks failed refreshes stale.
The sample vehicle animation is labeled as browser-only demo behavior. Database
indexes enforce the one-enabled-vehicle and one-active-session uniqueness rules.

Review corrected a misleading migration comment: audit targets are polymorphic,
but outbox aggregate IDs really do reference spaces. Architecture and sequence
documentation now distinguishes working code from future services.

No claim is made that all AGENTS.md requirements are completed. The remaining
requirements below are material blockers for real parking workflows and launch.

## Verification executed for this checkpoint

With the local website, API and WSL database already running:

```powershell
py scripts/test_system.py
py scripts/docker_wsl.py compose build api
```

The test runner completed all six groups successfully:

| Group | Evidence | Limits |
| --- | --- | --- |
| Website | Actual port 5173 page and API proxy reachable | Smoke test, not browser interaction automation |
| Scaffold | Three Node source-rule checks passed | Selected assertions, not exhaustive static/security analysis |
| Frontend | TypeScript and Vite production build passed | Does not inspect visual layout |
| API | Two running integration tests passed | Current public contract only; no authenticated endpoints |
| Database | SQL constraint/history assertions passed; fixtures rolled back | Sequential constraint tests, not concurrent parking transactions |
| Python tools | Four Windows regression tests passed | Current Windows/bundled-runtime setup |

The C++ container build completed successfully using cached build layers.
Dependency/tool versions and exact setup
commands are recorded in the root README and tools inventory. Prior browser checks
covered desktop/mobile layout, preview isolation and loading/empty/stale states;
they are manual evidence, not a committed automated browser test suite.

Test vehicles/users/sessions exist only inside a rolled-back SQL transaction.
Persistent seed records are a synthetic location, zone and six spaces. Consequently
there are no test vehicle histories to browse in the UI. Real vehicle status cannot
be changed until authenticated parking write workflows are implemented.

## Remaining verification and implementation

- Phase 3: authentication/recovery, verified accounts, privileged MFA, session/CSRF
  controls, role/location policy, normalized vehicle registration and APIs.
- Phase 4: transactional check-in/out, replacement/maintenance coordination,
  idempotency behavior, safe conflicts and simultaneous concurrency tests.
- Phase 5: actual driver/staff/admin pages and login-to-checkout end-to-end tests.
- Phase 6: durable outbox relay, authorized SSE, snapshot/replay cursor protocol,
  revocation, reconnect, multi-instance, stale/polling and latency tests.
- Phase 7: CI, lint/security scans, production configuration, least-privilege DB
  roles, observability, backup restore drills, load/accessibility verification,
  privacy review, incident/runbooks and operator acceptance.

Native Windows C++ compilation remains unverified: MSVC Build Tools installation
did not complete. The selected WSL container backend is the tested route. No
production deployment or service purchase was performed.

## Source-control hygiene

Only project source, placeholder configuration, lockfiles, tests and documentation
belong in this checkpoint. Local `.env`, `.tools`, dependencies, database backups,
container exports and generated build files are ignored. Verify the staged file
list and whitespace before commit. Push the normal branch update without force.
