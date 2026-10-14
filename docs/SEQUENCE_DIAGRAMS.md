# Execution sequence diagrams

Sections marked **Current** describe runnable code. Sections marked **Planned**
are required designs for later phases, not existing endpoints or test evidence.

## Current: local startup

```mermaid
sequenceDiagram
  actor Developer
  participant Python as start_dev.py
  participant WSL as Ubuntu and Docker
  participant DB as PostgreSQL container
  participant API as C++ container
  participant Vite as Frontend process
  Developer->>Python: py scripts/start_dev.py
  Python->>Python: Check port, Node/pnpm and .env
  alt Port already listening
    Python-->>Developer: Explain existing listener; exit
  else Port free
    Python->>WSL: Hold foreground process and start Docker
    Python->>WSL: compose up -d
    WSL->>DB: Start; wait for health
    WSL->>API: Start API
    Python->>API: Poll /api/ready with bounded wait
    API->>DB: Check migration ledger
    DB-->>API: Migration status
    API-->>Python: Ready or failure
    Python->>Vite: Install if needed; pnpm dev
    Vite-->>Developer: Local URL; keep terminal open
  end
```

Startup expects migrations already applied using README setup commands. Readiness
failure stops startup; it does not silently migrate a production database.

## Current: availability snapshot and failed refresh

```mermaid
sequenceDiagram
  actor User
  participant UI as TypeScript browser
  participant Vite as Development proxy
  participant API as Availability handler
  participant DB as PostgreSQL
  User->>UI: Open page or refresh
  UI->>UI: Loading state; five-second abort timer
  UI->>Vite: GET /api/locations
  Vite->>API: Forward /api request
  API->>DB: Aggregate spaces and active sessions
  alt Query succeeds
    DB-->>API: Aggregate rows only
    API-->>UI: Counts and UTC timestamp, no-store
    UI->>UI: Validate schema/counts; save snapshot
    UI-->>User: Render totals, locations and last updated time
  else Database error, timeout or invalid response
    API-->>UI: 503 if DB query fails
    UI->>UI: Retain previous snapshot if present
    UI-->>User: Disconnected or stale message; allow retry
  end
```

Filtering selects from the loaded snapshot without another API request. An empty
location list produces an explicit empty state. Browser abort stops waiting;
it is not a database transaction cancellation guarantee.

## Current: sample vehicle animation

```mermaid
sequenceDiagram
  actor User
  participant UI as Browser sample bay
  User->>UI: Preview arrival
  UI->>UI: Set sample occupied; animate; change label/buttons
  UI-->>User: Sample vehicle parked
  User->>UI: Preview departure
  UI->>UI: Set sample empty; animate; change label/buttons
  Note over User,UI: No API write, database change or actual parking confirmation
```

## Current: migration, seed and database test isolation

```mermaid
sequenceDiagram
  actor Developer
  participant PSQL as psql scripts
  participant DB as PostgreSQL
  Developer->>PSQL: Run migrate.sql
  PSQL->>DB: BEGIN; transaction advisory lock
  PSQL->>DB: Create/read migration ledger
  alt Migration 001 absent
    PSQL->>DB: Apply schema and record version
  else Already applied
    PSQL->>DB: Skip migration 001
  end
  PSQL->>DB: COMMIT
  Developer->>PSQL: Run seed.sql
  PSQL->>DB: Insert synthetic location/zone/spaces repeat-safely
  Developer->>PSQL: Run constraints.sql
  PSQL->>DB: BEGIN; create temporary test entities
  PSQL->>DB: Exercise unique conflicts and immutable history
  PSQL->>DB: ROLLBACK test records
  Note over Developer,DB: Test vehicles are not persistent demo data
```

Migration errors stop psql and roll back the migration transaction. This is forward
migration infrastructure; an automated down migration is not implemented.

## Current: build and verification

```mermaid
sequenceDiagram
  actor Developer
  participant Runner as test_system.py
  participant Node as Node and pnpm
  participant HTTP as Running website and API
  participant DB as PostgreSQL
  Developer->>Runner: Run explained six-group test command
  Runner->>HTTP: Website and proxy smoke check
  Runner->>Node: Static scaffold checks
  Runner->>Node: TypeScript check and Vite production build
  Runner->>HTTP: API health/readiness/response assertions
  Runner->>DB: SQL constraint checks inside rollback transaction
  Runner->>Runner: Python launcher regressions
  Runner-->>Developer: PASS per group; stop on first failure
```

The C++ image build is separate: Docker builds pinned framework sources, compiles
the application, then copies the executable to a non-root runtime stage. These
tests do not perform authenticated parking end-to-end flows.

## Planned: login and vehicle registration (phase 3)

```mermaid
sequenceDiagram
  actor Driver
  participant UI as Authenticated UI
  participant Auth as Maintained authentication integration
  participant API as Vehicle service and policy
  participant DB as PostgreSQL
  Driver->>UI: Login or account recovery
  UI->>Auth: Authentication flow
  Auth-->>UI: Verified session with secure cookie
  Driver->>UI: Submit own vehicle
  UI->>API: Vehicle request with session and CSRF protection
  API->>API: Resolve actor; validate and normalize input
  API->>DB: BEGIN; lock user and existing vehicle consistently
  API->>DB: Reject replacement if an active session exists
  API->>DB: Register/replace vehicle; write audit
  alt Enabled vehicle or registration conflict
    API->>DB: ROLLBACK
    API-->>UI: Safe 409 conflict
  else Valid registration
    API->>DB: COMMIT
    API-->>UI: Confirmed vehicle result
  end
```

The authentication library/provider and detailed recovery contract remain to be
selected. Privileged roles require MFA; session expiry/revocation is server-side.

## Planned: staff check-in and concurrent conflicts (phase 4)

```mermaid
sequenceDiagram
  actor Staff
  participant API as Parking service
  participant DB as PostgreSQL
  Staff->>API: POST check-in with Idempotency-Key
  API->>API: Authenticate, authorize location, validate body
  API->>DB: BEGIN; serialize actor/operation/key
  alt Same key and same request already committed
    DB-->>API: Stored original result
    API-->>Staff: Return original result
  else Key reused with different request hash
    API->>DB: ROLLBACK
    API-->>Staff: 409 conflict
  else New request
    API->>DB: Lock user, vehicle and space in consistent order
    API->>DB: Validate ownership, enabled status, compatibility and availability
    API->>DB: Insert active session and immutable snapshot
    API->>DB: Write audit, versioned outbox and idempotency result
    alt Valid transaction
      API->>DB: COMMIT
      API-->>Staff: Confirmed success
    else Validation or uniqueness conflict
      API->>DB: ROLLBACK
      API-->>Staff: Safe error or 409
    end
  end
```

Two actors targeting the same space must have one winner. Locks coordinate checks;
partial unique indexes remain the final backstop. Lock acquisition order across
check-in, checkout, maintenance and replacement must be specified consistently
before implementation and tested for competing operations.

## Planned: checkout, replacement and maintenance (phase 4)

```mermaid
sequenceDiagram
  actor Staff
  participant API as Parking service
  participant DB as PostgreSQL
  Staff->>API: Checkout session with Idempotency-Key
  API->>API: Authenticate and verify location scope
  API->>DB: BEGIN; coordinate relevant locks and idempotency
  API->>DB: Lock/revalidate active session and related records
  API->>DB: Set checkout once; preserve arrival snapshot
  API->>DB: Write audit, outbox, resource version and stored result
  API->>DB: COMMIT
  API-->>Staff: Confirmed checkout
  Note over API,DB: Duplicate checkout cannot change the recorded exit
  Note over API,DB: Replacement locks same user/vehicle; reject while active
  Note over API,DB: Maintenance locks same space; reject unsafe occupied transition
```

Retries must distinguish a recorded success from a new conflicting request.
Administrative corrections need a reason and audited workflow; current history
triggers intentionally do not provide a general correction API.

## Planned: durable realtime, replay and privacy (phase 6)

```mermaid
sequenceDiagram
  participant Write as Parking transaction
  participant DB as PostgreSQL
  participant Relay as Durable outbox relay
  participant SSE as Authorized stream service
  participant UI as Dashboard
  Write->>DB: COMMIT session, audit and outbox together
  Relay->>DB: Read committed pending events
  Relay->>SSE: Deliver through shared durable mechanism
  SSE->>SSE: Apply role/location/owner projection
  SSE-->>UI: Event ID, resource version and timestamp
  UI->>UI: Ignore duplicate or older versions
  Relay->>DB: Record publication; retry failures
  UI->>SSE: Reconnect with cursor and authenticated session
  SSE->>SSE: Re-authorize; bounded replay or request fresh snapshot
  SSE-->>UI: Replay or snapshot cursor reset
  Note over SSE,UI: Expiry, logout or revoked permission closes access
  Note over SSE,UI: Heartbeat loss shows stale; bounded polling fallback
```

Publication can be at least once; consumers must handle duplicates. Snapshot and
subscription need a shared cursor/replay contract to avoid lost updates. No relay,
broker, SSE subscription or two-second latency measurement exists at this checkpoint.
