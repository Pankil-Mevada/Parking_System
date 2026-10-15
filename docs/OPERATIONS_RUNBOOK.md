# Local pilot and release runbook

No production deployment is authorized. Use the phase 7 commands in `PHASE_7.md`.

## Triage

1. Run `py scripts/monitor.py`. Check readiness, outbox lag and database connections.
2. Inspect `py scripts/docker_wsl.py compose logs --tail 100 api db` locally.
   API request IDs connect failures to sanitized request logs. Do not publish logs
   or identity-provider administrative output containing account information.
3. If readiness fails, confirm database availability and migration ledger. Do not
   delete volumes or bypass constraints. If the identity provider fails, parking
   writes must remain unavailable until authentication recovers.
4. For outbox lag, verify database locks and relay recovery before considering a
   restart. Restarting the API preserves committed outbox/delivery records.
5. For stale dashboards, verify connectivity and reconnection/snapshot behavior.
   Staff must reconcile physical occupancy before correcting a software record.
6. Revoke removed staff assignments immediately, then verify their next request
   and event batch fail. Privileged access requires verified identity and MFA.

## Backup recovery

`py scripts/backup_database.py --drill` creates a new encrypted snapshot and a
separate retained restore database. To repeat restoration of an existing snapshot:

```text
py scripts/backup_database.py --restore .tools/backups/REPLACE_WITH_BACKUP_ID
```

Never overwrite the live database during a drill. Keep the age private key at
`.tools/backup-keys/parking.agekey` confidential and recoverable separately from
backups. Production backup recipients, key rotation, off-site storage, identity
database restore and an agreed RTO/RPO must be tested before launch. Losing the
key prevents decryption. Current local table-count verification does not prove
all application workflows after a disaster.

## Release and rollback

Create a review bundle using `py scripts/package_release.py`. Verify its manifest
hashes and image ID before use. Record exact source/version, migration ledger,
test reports, accepted scan results, environment and operator approval. Never
substitute a mutable latest tag for an approved artifact during production promotion.

There is no production rollout command yet: TLS, identity persistence, secret
manager and staging acceptance are unfinished. Before a future authorized rollout,
take and verify backups, apply additive migrations using the owner account, deploy
the approved image, and check readiness and parking/realtime acceptance. If code
fails, return to the prior approved image only after proving its compatibility
with the migrated schema in staging. Migration 004 is additive; no destructive
down migration is supplied. Do not drop tables to roll back code. A database restore
requires an explicitly approved outage/data-loss decision and separate procedure.

## Staff pilot

For each floor, physically compare every space with the staff grid. Record arrival,
confirmed check-in, both dashboard updates, confirmed departure, check-out and
retained history. Test disconnected clients and conflicting requests. Investigate
mismatches; the software cannot sense unreported physical arrivals or departures.
Record pilot dates, responsible staff, issues and operator sign-off. Do not collect
extra personal information for pilot reports. Alerts/incident escalation stay
unassigned until the operator names responsible people.
