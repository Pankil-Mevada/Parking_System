# Inspect the database, retain tests and configure real email

Owner choice on 2026-10-15: keep Mailpit for now. Normal verification/recovery can
use real recipient addresses, but messages appear only in the local Mailpit UI.
The Gmail setup below is optional and is not currently activated.

Current owner instruction: retain databases and committed test records until the
owner explicitly asks for deletion. Automated cleanup must not remove databases,
case schemas, provider realms or their volumes. This supersedes the earlier
disposable-test cleanup policy.

## See the database

```powershell
py -m pip install --target .tools/test-python -r requirements-test.txt
py scripts/view_database.py --start
```

Keep that terminal open, then open http://127.0.0.1:8090.

- **Development → public:** normal application users, vehicles, locations, spaces,
  sessions, staff assignments, audit events, outbox and idempotency records.
- **Retained tests → run_… schema:** the committed records from one named test case.
  Select a table such as `vehicles`, `spaces`, `parking_sessions` or `audit_events`.
- A session with `checked_out_at = NULL` is active. A vehicle with `disabled_at = NULL`
  is enabled. Space operational status is separate from parking occupancy.
- Empty normal user/session tables are expected until someone registers/checks in;
  the normal seed contains only a location, zone and six spaces.

The viewer provides pagination, refresh and table/schema selection. It binds only
to loopback, rejects cross-site/foreign-host requests, and uses read-only PostgreSQL
transactions. It has no delete, update or arbitrary-SQL endpoint. It is a trusted
local-computer-owner inspection tool, not a public role-based administrator page.
It can show owner details; do not expose its port to other computers. Login secrets
and SMTP credentials belong to Keycloak and are not shown in the parking tables.

## Retained test behavior

```powershell
py scripts/test_phase34.py
# Optional smaller run:
py scripts/test_phase34.py --test-name test_03_two_vehicles
```

PostgreSQL test data is stored in the named `retained_test_data` volume, not tmpfs.
Captured Mailpit emails also use the persistent `mail_data` volume. The existing
19 messages were backed up and preserved when enabling that storage.
Every run creates a unique `parking-tests-…` identity realm; every case creates a
unique `run_…` database schema containing the full constrained schema and fixtures.
Later cases/runs do not truncate or delete earlier cases. The test API is restarted
between cases so both its connection pool and write connections use the right
case schema. A process lock prevents concurrent suites from changing that routing.
This deliberately takes longer than the earlier cleanup-based suite.

Run metadata is retained locally in `.tools/test-runs/*.json`; run environment files
contain the test realm name, not passwords. Test users have synthetic addresses and
random credentials; inspect/reset their identity credentials through local provider
administration if necessary. Do not treat them as normal customer accounts.

Intentional transaction rollback still leaves no committed row—that is the expected
parking correctness behavior. Tests exercising role removal or logout still perform
those business operations. No database or earlier case is deleted as test cleanup.
The older scaffold SQL constraint test also intentionally rolls back its transaction.

The viewer and tests have no automatic database-delete function. Stop containers
when needed without removing their volumes. Avoid `down -v`, volume pruning or schema
cleanup. A future admin/user deletion workflow needs explicit authorization and must
preserve required parking history/audit records; it is not implemented by this viewer.

Verified on 2026-10-14: all 28 integration cases passed with retained schemas
(193.777 seconds). A subsequent single-case run passed and preserved all 28 earlier
schemas, their competing-space session history and both provider realms. Eight
local-tool safety tests passed, including PostgreSQL rejecting writes from the
viewer connection, cross-site/foreign-host denial and concurrent-suite exclusion.
The browser viewer was checked against the six actual development spaces.

## Real Gmail delivery

The chosen sender address is stored privately as `SMTP_SENDER` in ignored `.env`.
Recipient accounts can be Gmail, Outlook, Yahoo or another valid email provider.
The current configuration helper is specifically for the selected Gmail sender.

1. Sign into the Google account that owns the sender address.
2. Enable 2-Step Verification and create an app password named `Parking_System`.
   See [Google's app-password instructions](https://support.google.com/mail/answer/185833).
3. In your own interactive terminal, run:

   ```powershell
   py scripts/configure_smtp.py
   ```

4. Enter the app password at the hidden prompt. Do not paste it in chat, put it in
   source files, or use the normal Google account password.
5. The helper checks Gmail authentication over STARTTLS, then configures the normal
   `parking` realm. The app password is held in memory and stored by the local identity
   service; it is never printed or written to Git. The command sends no email itself.
6. Register your own real email address on the website, or request verification/
   password recovery, to exercise actual delivery.

Settings: `smtp.gmail.com`, port 587, authentication and STARTTLS enabled. Account
policies can prevent app passwords; Google controls their availability. If SMTP
authentication fails, the helper leaves the existing provider mail settings unchanged.

The Gmail app password has not been provided, so real delivery is not yet enabled
or verified. Until that command succeeds, normal development mail still goes to
Mailpit at http://127.0.0.1:8025. Automated synthetic test realms always use Mailpit,
even after normal users switch to Gmail; tests must not email synthetic addresses.

Because this is a local server, verification links point to `127.0.0.1`. Open them
on the computer running the application. Public HTTPS URLs and production SMTP/
secret management remain deployment work. Provider data/backups can contain SMTP
credentials after configuration; keep them private and out of Git.
