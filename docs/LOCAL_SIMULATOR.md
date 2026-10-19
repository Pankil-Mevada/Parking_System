# Local hardware simulator

This is a software device simulator connected to the real isolated parking API,
PostgreSQL, authorization provider and delivery relay. No Wokwi installation,
hardware purchase, public tunnel or hosted service is needed.

## Start

From this project, with the existing local Docker/identity setup and test/browser
dependencies installed:

```text
python scripts/test_phase34.py --simulator
```

Use the bundled Python executable if the Windows `py`/`python` launcher does not
work. The runner creates a fresh retained identity realm and case schema, adds
two synthetic driver vehicles and six bays, and performs real HTTP and Chromium
checks before reporting `SIMULATOR VERIFIED`. Open http://127.0.0.1:8766.

The synthetic cards are `DEMO-CARD-A` (AB123) and `DEMO-CARD-B` (SECOND).
The verified starting state is P02 occupied by card B, P03 showing a deliberate
sensor/API mismatch, and all other bays available in the API.

## Try it

1. Select card A and P01, then **Scan + confirm arrival**. The server confirms a
   real parking session in the isolated test schema before displaying success.
2. Select **Replay last event**. The same result returns without creating a
   second session. Choose **Confirm departure** to close the session and retain
   its history. Replaying departure also returns the original result.
3. Select `UNKNOWN-CARD`. Arrival is denied without a parking write.
4. Set the gate to Offline or Obstructed and apply it. New parking actions are
   blocked; existing sessions remain. Restore Normal to continue.
5. Select an empty bay and send **Sensor: occupied**. A reconciliation warning
   appears; the simulator does not invent a vehicle or parking session. Send a
   newer Empty reading to clear it. **Send older reading** demonstrates sequence
   protection after at least one reading exists.

Arrival/departure controls simulate a *confirmed passage*, using a synthetic
attendant's authenticated existing check-in/out API. Gate acknowledgements are
simulated. This is not a production device ingestion service or a firmware/circuit
emulator. ANPR and physical gate safety/accuracy are not tested here.

## Isolation, retained records and stopping

- Listens only on `127.0.0.1:8766`; Host/Origin checks and a per-process control key
  protect browser writes. Provider bearer tokens stay on the Python server.
- Main development parking records are not used. The simulator shares the retained
  test API services, so it holds the test-suite lock until stopped. Run other
  integration suites afterward, never concurrently against those test APIs.
- `.tools/simulator/RUN_ID/` retains the SQLite event ledger, manifest,
  `verification.json`, and desktop/mobile screenshots. Database schemas and identity
  realms remain. No reset/delete control is supplied.
- Ctrl+C in the startup terminal stops the simulator. Ask Codex to stop it if it
  was started from this chat. Restarting creates a new retained scenario; it does
  not resume the old case. Event replay within a running scenario uses its durable
  ledger and the backend's idempotency keys.
- A timed-out action is uncertain. Use **Replay last event** rather than making
  a fresh arrival event. A stale/unreachable backend is explicitly labelled.

## Verification on 19 October 2026

Five standalone device-state tests passed:

```text
python -m unittest discover -s tests -p test_device_simulator.py -v
```

Live retained run `7ea7a5eb-7637-4515-9cea-dab64724725c` passed six integration/browser
groups: known RFID and durable replay, wrong-content duplicate rejection, unknown
cards and gate faults without session writes, stale sensor rejection and physical
mismatch, departure/history and peer SSE, same-origin protection, plus real Chromium
controls and mobile overflow. Desktop/mobile screenshots were visually inspected.
This is focused simulator verification, not hardware or commercial-launch acceptance.
