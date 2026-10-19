"""Provision through the guarded retained-test runner, verify, then serve locally."""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

from parking_tools import ROOT, port_in_use

sys.path.insert(0, str(ROOT / 'tests'))
from test_phase34 import Phase34, api
from device_simulator import Simulator, server
from identity_flow import login


class Fixtures(Phase34):
    def test_simulator(self):
        pass


def main():
    if port_in_use(8766):
        raise RuntimeError('Port 8766 is occupied. Existing simulator/process was not stopped.')
    Fixtures.setUpClass()
    case = Fixtures('test_simulator')
    case.setUp()
    folder = ROOT / '.tools/simulator' / case.run_id
    folder.mkdir(parents=True)
    httpd = None
    record = {'runId': case.run_id, 'simulation': True, 'retained': True, 'status': 'preparing',
              'url': 'http://127.0.0.1:8766', 'realHardwareConnected': False}
    try:
        case.db.execute('UPDATE locations SET name=%s WHERE id=%s', ('SIMULATION — One building', case.location))
        identifiers = list(case.spaces[:2]) + [str(uuid.uuid4()) for _ in range(4)]
        bays = {f'P{i+1:02}': identifier for i, identifier in enumerate(identifiers)}
        for index, (label, identifier) in enumerate(bays.items()):
            if index < 2:
                case.db.execute('UPDATE spaces SET label=%s WHERE id=%s', (label, identifier))
            else:
                case.db.execute("INSERT INTO spaces(id,location_id,label,supported_vehicle_type) VALUES(%s,%s,%s,'car')",
                                (identifier, case.location, label))
        access = {'token': case.staff, 'time': time.monotonic()}
        def call(path, method='GET', body=None, key=None):
            # Tokens remain server-side. Renew via the real isolated provider.
            if time.monotonic() - access['time'] > 900:
                access.update(token=login(case.identities[0])['access_token'], time=time.monotonic())
            return api(access['token'], path, method, body, key)
        simulator = Simulator(folder / 'events.sqlite3', call, case.location, bays,
                              {'DEMO-CARD-A': case.v1, 'DEMO-CARD-B': case.v2})
        httpd = server(simulator)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        record.update(status='testing', locationId=case.location,
                      schema=('run_' + case.run_id.replace('-', '')[:12] + '_test_simulator'))
        manifest = folder / 'manifest.json'
        manifest.write_text(json.dumps(record, indent=2) + '\n')
        from simulator_journey import verify
        verify(simulator, case, folder)
        record['status'] = 'running_verified'
        manifest.write_text(json.dumps(record, indent=2) + '\n')
        print('SIMULATOR VERIFIED — open http://127.0.0.1:8766', flush=True)
        print('Synthetic data only. Two registered cards, six bays. P02 is parked; P03 has a sensor mismatch.', flush=True)
        print('Ctrl+C stops the UI; all fixtures and event records remain. Other suites are locked while this runs.', flush=True)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        record['status'] = 'stopped'
    except Exception:
        record['status'] = 'verification_failed'
        raise
    finally:
        (folder / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
        if httpd:
            httpd.shutdown()
            httpd.server_close()
        case.doCleanups()


if __name__ == '__main__':
    main()
