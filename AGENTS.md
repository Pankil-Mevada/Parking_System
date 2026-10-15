# Vehicle Parking System - engineering instructions

## Purpose and scope
Build a commercial parking-management website that shows empty and occupied
spaces in real time and identifies the parked vehicle and its owner to authorized
staff. This directory is a separate parking project; do not reuse or modify the
unrelated applications. These instructions describe requirements, not a
claim that the application is implemented or ready for production.

## Assumptions to preserve until the owner changes them
- One registered, enabled vehicle per user across the product, and at most one
  active parking session per user. Historical vehicles/sessions remain auditable.
- A user must end their session before replacing or disabling their vehicle.
- Initial occupancy comes from staff-confirmed check-in/check-out. Live website
  updates do not prove physical occupancy without staff or hardware input.
- Start with one operator and multiple parking locations. If selling to separate
  operators, implement and test tenant isolation before onboarding them.
- Payments, reservations, and guest vehicles remain future scope.
- Owner-approved phase 8 covers ANPR cameras, RFID readers/tags, occupancy sensors,
  and barrier gates after phases 5–7. This is planned scope, not implemented hardware.

## Owner update: local test data and email
- Retain development/test databases, committed test records and test identity realms
  until the owner or an authorized administrator explicitly requests deletion.
- Do not automatically truncate prior test cases, drop their schemas/databases,
  remove identity realms, or prune database volumes as test cleanup. Use persistent,
  isolated case schemas. Intentional transaction rollback and tested business
  operations such as checkout or assignment revocation remain valid.
- Synthetic automated-test emails must stay in local Mailpit, even when normal
  user verification/recovery uses real SMTP. SMTP credentials must be entered
  privately and never committed or pasted into chat.
- Owner choice on 2026-10-15: use local Mailpit for normal verification/recovery
  for now, including real recipient addresses. Real SMTP is optional future setup.

## Architecture
- For a new implementation, proposed baseline: TypeScript web frontend and API,
  PostgreSQL, database migrations, and server-sent events (SSE). Reuse an existing
  stack if the parking repository already has one. Record the decision in README.
- Keep validation, authorization, parking transactions, persistence, and realtime
  delivery separate. The database is the source of truth; browser state is not.
- Use supported dependency versions and a lockfile. Document actual install,
  development, migration, seed, test, and deployment commands after scaffolding.
- Prefer a modular application before introducing microservices.

## Roles and access
- Owner update (2026-10-15): driver and employee accounts are separate. Public
  registration creates a driver unless the administrator approved a separate
  employee email before the first parking-app login. Driver search must never
  offer staff role assignment; the API/database must reject assigning drivers.
  Staff role selection is limited to separately enrolled employee accounts.
  Owner refinement: an employee may register first and explicitly request staff
  access before an administrator assigns a location role. Accounts with vehicle
  or parking history must use a separate employee identity. Public registration
  or a staff request alone grants no staff permissions.
  Employee accounts cannot register a personal vehicle under their own login;
  authorized staff may create driver accounts and register/manage those drivers'
  vehicles at assigned locations. Preserve existing
  assigned employee accounts and historical records during migration.
- Owner-approved local development login now uses verified email and password
  without Microsoft Authenticator or other OTP apps. `REQUIRE_STAFF_MFA=false`
  selects this local mode. Do not remove login, location authorization, or email
  verification. Production privileged MFA remains a launch gate; strict-mode tests
  and enrolled credentials are retained for future re-enablement.
- Driver: manage own vehicle, see availability and own session/history.
- Attendant: check vehicles in/out and see owner/vehicle information only at
  assigned locations. Cannot grant roles or manage other locations.
- Operator administrator: manage assigned locations, spaces, staff, and reports.
- Platform administrator, if introduced: separate privileged access, MFA, and
  audited support access; no routine unrestricted browsing of customer records.
- Authorize every API request and SSE subscription server-side. Infer user and
  operator identity from the authenticated session, never from trusted body fields.
- Public availability must contain aggregate counts only. Other drivers must
  never receive owner names, contact details, or full registration numbers.

## Website requirements
- Login, password reset/account recovery, and authenticated navigation.
- Driver dashboard: registered vehicle, location selector, available space count,
  current space, arrival time, elapsed duration, and session history.
- Staff dashboard: searchable space grid, empty/occupied/out-of-service labels,
  vehicle registration/type/color, authorized owner details, arrival time, and
  confirmed check-in/check-out controls. Use text/icons as well as colors.
- Admin pages: locations, floors/zones, numbered spaces, compatible vehicle types,
  user/vehicle management, staff assignments, and searchable audit records.
- Responsive and keyboard-accessible UI with labeled forms and useful errors.
- Show loading, empty, disconnected, stale, permission-denied, and failed states.
- Do not display a successful parking action before server confirmation.
- Capacity totals exclude out-of-service spaces. Display occupied, available,
  out-of-service, and last-updated values consistently.

## Data model and invariants
- users: id, identity-provider reference, status, timestamps.
- vehicles: id, user_id, registration jurisdiction, normalized registration,
  vehicle type, make/model/color where needed, disabled_at, timestamps.
- locations and spaces: location/zone identifiers, unique space label per
  location, supported vehicle type, operational status, version.
- staff_assignments: user, location, role; enforce assignment on every operation.
- parking_sessions: user_id, vehicle_id, space_id, checked_in_at,
  checked_out_at, checked_in_by, checked_out_by, immutable registration snapshot.
- audit_events: actor, action, target, timestamp, request ID, and sanitized changes.
- outbox_events: event ID, aggregate ID/version, payload, publication metadata.
- idempotency_records: actor, operation, key, request hash, result, expiry.
- All references require foreign keys. Use UTC timestamps and display local time.
- Enforce one enabled vehicle per user and one active session per user, vehicle,
  and space with database uniqueness, not only an application pre-check.
- Normalize registration consistently; uniqueness includes jurisdiction. Do not
  assume a single country's plate format unless explicitly configured.
- Preserve session history on vehicle replacement. Never silently reassign an
  occupied space or delete an active vehicle/user/space.

### Illustrative PostgreSQL migration fragments
Adapt table/column names to the real schema; these are constraints, not a complete
schema or a runnable application.

```sql
CREATE UNIQUE INDEX one_enabled_vehicle_per_user
ON vehicles(user_id) WHERE disabled_at IS NULL;

CREATE UNIQUE INDEX unique_enabled_registration
ON vehicles(registration_jurisdiction, normalized_registration)
WHERE disabled_at IS NULL;

CREATE UNIQUE INDEX one_active_session_per_user
ON parking_sessions(user_id) WHERE checked_out_at IS NULL;

CREATE UNIQUE INDEX one_active_session_per_vehicle
ON parking_sessions(vehicle_id) WHERE checked_out_at IS NULL;

CREATE UNIQUE INDEX one_active_session_per_space
ON parking_sessions(space_id) WHERE checked_out_at IS NULL;
```

## Check-in/check-out correctness
- Check-in transaction: authenticate and authorize actor; lock user, vehicle,
  and target space in a consistent order; validate ownership, enabled status,
  vehicle compatibility and operational status; create active session; write
  audit and outbox events; commit. Concurrent attempts must have one winner.
- Vehicle replacement must lock the same user/vehicle records and reject an
  active session. Space maintenance must coordinate with the same space lock.
- Check-out transaction: lock active session and relevant records; verify actor
  and location; set exit timestamp once; write audit/outbox events; commit.
- Derive occupied/empty from active sessions instead of independently maintained
  flags that can disagree. Operational status is a separate attribute.
- Require idempotency keys for check-in/out. Retrying the same request returns
  the original result; reusing a key with a different body returns conflict.
- Translate uniqueness conflicts into HTTP 409 with a useful safe error.
- Publish only committed changes through a transactional outbox with retries.
- Administrative corrections require a reason and an audit trail.

## API outline
- GET /api/me; GET/PUT /api/me/vehicle
- GET /api/locations; GET /api/locations/:id/availability
- GET /api/me/parking-session; GET /api/me/parking-history
- GET /api/staff/locations/:id/spaces (authorized detailed occupancy)
- POST /api/staff/check-ins with vehicleId, spaceId, Idempotency-Key
- POST /api/staff/sessions/:id/check-out with Idempotency-Key
- GET /api/locations/:id/events (role-filtered realtime stream)
- Administrative location/space/staff endpoints with explicit authorization.
- Use schema validation, pagination, bounded filters, consistent errors, and
  request IDs. Write an OpenAPI contract and verify it against implementation.

## Realtime behavior
- Target: connected dashboards update within two seconds of a committed change
  under the agreed normal load; measure this in staging rather than claiming it.
- Subscribe with authenticated access; separate public aggregates, driver-own
  events, and staff details. Never broadcast sensitive data then hide it in CSS.
- Events carry event ID, location, resource version, and server timestamp.
- Close/re-authorize streams on logout, expiry, or permission revocation.
- Reconnect with backoff; replay a bounded event window or fetch a fresh snapshot
  when the cursor is too old. Ignore duplicate/out-of-order versions.
- Prevent snapshot/subscription races using a snapshot cursor and replay.
- Heartbeats and last-success time drive a visible stale indicator. Provide a
  bounded polling fallback. Never label disconnected data as live.
- Across multiple API instances, use a durable shared delivery mechanism or
  broker fed by the outbox; an in-process event emitter alone is insufficient.

## Security and privacy requirements
- Use OWASP ASVS Level 2 as a verification target; track actual evidence and
  exceptions. Do not claim certification or compliance from this document alone.
- Prefer a maintained authentication library/provider. Require verified accounts
  and MFA for privileged roles. No custom cryptography or default admin password.
- If storing passwords, use a maintained Argon2id implementation with reviewed
  parameters. Recovery tokens must be random, short-lived, single-use, and hashed
  at rest. Avoid account enumeration; rate-limit login and recovery endpoints.
- Use HTTPS; secure HttpOnly SameSite cookies, session rotation/revocation,
  inactivity/absolute timeouts, and CSRF protection for cookie-authenticated writes.
- Use parameterized SQL, strict input validation, safe output rendering, CSP,
  clickjacking protection, and explicit allowed origins. Never use wildcard
  credentialed CORS or put bearer tokens in URLs/localStorage.
- Enforce object-level authorization, least-privilege database/service accounts,
  bounded request sizes, connection limits, timeouts, and abuse controls.
- Keep production secrets in a secret manager; provide only placeholder values
  in .env.example. Never log tokens, passwords, or unnecessary personal data.
- Encrypt production storage/backups; restrict administrative access and audit
  personal-data reads/exports. Protect audit records from ordinary modification.
- Define retention/deletion periods with the operator before launch. Minimize
  collected data, document privacy notices and handling of data-subject requests.
- Verify applicable privacy/legal obligations for the deployment jurisdiction;
  do not assume this specification establishes legal compliance.
- Keep production data out of development, screenshots, and test fixtures.
- Verify backups through restore drills; revoke staff access promptly on removal.

## Required verification
- Unit tests: normalization, role policy, state transitions, capacity calculations.
- Database integration tests: simultaneous check-ins for the same space/user/
  vehicle, simultaneous vehicle registration/replacement, check-in vs maintenance,
  duplicate check-out, retries after timeout, and transaction rollback.
- Authorization tests: unauthenticated, wrong role/location/operator, guessed IDs,
  export access, SSE leakage, and permission revocation on existing streams.
- End-to-end: login -> register vehicle -> staff check-in -> both dashboards
  update -> check-out -> space becomes available -> history remains correct.
- Realtime: disconnect/reconnect, missed/duplicate/out-of-order events, server
  restart, multiple instances, and stale indicator/polling fallback.
- Security: session/CSRF behavior, injection/XSS, brute-force controls, secret and
  dependency scans, and independent review before commercial launch.
- Load test against agreed concurrent users, spaces, events/second, response-time
  targets, and failure recovery. Record measured results and test environment.
- Accessibility and mobile-browser checks for core driver/staff flows.

## Launch requirements and operations
- Separate development/staging/production; CI must run type checks, lint, tests,
  migrations on disposable databases, production build, and security scans.
- Deploy versioned artifacts with documented migration and rollback procedures.
  Test migration compatibility; avoid destructive schema changes during rollout.
- Implement health/readiness endpoints, structured redacted logs, error tracking,
  and metrics for API latency/errors, database saturation, outbox lag, stream
  connections, occupancy conflicts, failed logins, and stale clients.
- Document alert ownership, incident response, staff support, restore procedure,
  and agreed availability, recovery-time, and recovery-point targets.
- Pilot with staff using physical occupancy reconciliation. Investigate mismatches;
  software records alone cannot detect an unreported physical arrival/departure.
- Release only after acceptance tests, access review, restore drill, load results,
  privacy review, and operator sign-off are recorded. Keep unresolved blockers visible.

## Implementation sequence and agent behavior
1. Inspect only this parking project; summarize assumptions and selected stack.
2. Scaffold application, PostgreSQL migrations, configuration, and local README.
3. Implement authentication, roles, vehicle registration, and database constraints.
4. Implement transactional parking actions and concurrency/authorization tests.
5. Build driver/staff/admin pages with real API data and accessible states.
6. Implement durable realtime delivery and reconnect/privacy tests.
7. Add deployment, observability, security verification, and pilot runbook.
8. Integrate ANPR cameras, RFID readers/tags, occupancy sensors, and barrier gates.
   Select devices and review their protocols before implementation. Define failed
   reads, unauthorized entry, manual overrides, device outages, and physical
   occupancy reconciliation. Preserve authorization, idempotency, transaction
   invariants and audit trails; test duplicate and out-of-order device events.
- Deliver each phase as working code with meaningful tests. Clearly label mocks.
- Keep changes and tool output focused; search before reading large files.
- Read supporting documents only when needed and keep final summaries concise.
- Update README with exact runnable commands; never report unrun checks as passed.
- Do not deploy, purchase services, or transmit messages without authorization.

## Reference
- AGENTS.md: https://learn.chatgpt.com/docs/agent-configuration/agents-md
- Security verification: https://owasp.org/projects/asvs
