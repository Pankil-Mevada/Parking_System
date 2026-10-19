"""Device state and retry semantics, independent of any running services."""
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from device_simulator import Simulator


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.calls = []
        self.sim = Simulator(Path(self.folder.name) / 'events.sqlite3', self.call,
                             'location', {'P01': 'space'}, {'CARD': 'vehicle'})
        self.addCleanup(self.sim.db.close)

    def call(self, *args):
        self.calls.append(args)
        return 201, {'session': {'id': 'synthetic'}}

    def event(self, action, **fields):
        return self.sim.event({'eventId': str(uuid.uuid4()), 'action': action, **fields})

    def test_replay_survives_reopening_ledger_and_changed_body_conflicts(self):
        payload = {'eventId': str(uuid.uuid4()), 'action': 'arrive', 'bay': 'P01', 'tag': 'CARD'}
        self.assertEqual(self.sim.event(payload)[0], 201)
        other = Simulator(Path(self.folder.name) / 'events.sqlite3', self.call,
                          'location', {'P01': 'space'}, {'CARD': 'vehicle'})
        try:
            self.assertTrue(other.event(payload)[1]['replayed'])
            self.assertEqual(other.event(dict(payload, tag='OTHER'))[0], 409)
            self.assertEqual(len(self.calls), 1)
        finally:
            other.db.close()

    def test_unknown_tags_and_gate_faults_never_call_parking_api(self):
        self.assertEqual(self.event('arrive', bay='P01', tag='UNKNOWN')[0], 403)
        for mode in ('offline', 'obstructed'):
            self.event('gate', mode=mode)
            self.assertEqual(self.event('arrive', bay='P01', tag='CARD')[0], 409)
        self.assertEqual(self.calls, [])

    def test_sensor_ordering_does_not_create_parking_sessions(self):
        self.event('sensor', bay='P01', occupied=True, sequence=10)
        self.event('sensor', bay='P01', occupied=False, sequence=9)
        self.assertEqual(self.sim.state()['sensors']['P01'], {'occupied': True, 'sequence': 10})
        self.assertEqual(self.calls, [])

    def test_uncertain_api_result_retries_same_backend_idempotency_key(self):
        payload = {'eventId': str(uuid.uuid4()), 'action': 'arrive', 'bay': 'P01', 'tag': 'CARD'}
        self.sim.call = lambda *args: (503, {})
        self.assertEqual(self.sim.event(payload)[0], 503)
        self.event('gate', mode='offline')
        self.sim.call = self.call
        self.assertEqual(self.sim.event(payload)[0], 201)
        self.assertEqual(self.calls[0][-1], payload['eventId'])

    def test_malformed_events_are_rejected(self):
        for payload in ([], {}, {'eventId': None}, {'eventId': str(uuid.uuid4()), 'action': 'sensor',
                                                  'bay': 'P01', 'occupied': True, 'sequence': True}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.sim.event(payload)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
