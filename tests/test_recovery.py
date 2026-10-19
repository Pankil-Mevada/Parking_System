"""Failure-path checks for the local cold recovery tool; no services required."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import recover_local as recovery


class RecoveryTests(unittest.TestCase):
    def test_source_services_restart_after_backup_failure(self):
        calls = []
        source = {'State': {'Running': False}, 'Mounts': [
            {'Destination': '/opt/keycloak/data', 'Type': 'volume', 'Name': 'original'}]}
        with patch.object(recovery, 'service', side_effect=['api', 'identity', 'db']), \
             patch.object(recovery, 'inspect', return_value=source), \
             patch.object(recovery, 'inventory', return_value={}), \
             patch.object(recovery, 'admin_token', return_value='synthetic'), \
             patch.object(recovery, 'backup', side_effect=RuntimeError('simulated failure')), \
             patch.object(recovery, 'docker', side_effect=lambda args, **kw: calls.append(args)):
            with self.assertRaisesRegex(RuntimeError, 'simulated failure'):
                recovery.checkpoint()
        self.assertEqual(calls[-2:], [['start', 'identity'], ['start', 'api']])
        self.assertFalse(any('rm' in call for call in calls))

    def test_rejects_corruption_and_paths_outside_backup_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / '.tools/backups/case'
            folder.mkdir(parents=True)
            for name in ('parking.dump.age', 'identity.tar.age', 'configuration.age'):
                (folder / name).write_bytes(b'encrypted fixture')
            record = {'format': 1, 'files': {name: recovery.checksum(folder / name)
                      for name in ('parking.dump.age', 'identity.tar.age', 'configuration.age')}}
            (folder / 'recovery.json').write_text(json.dumps(record))
            with patch.object(recovery, 'ROOT', root):
                self.assertEqual(recovery.validate(folder)[1], record)
                (folder / 'identity.tar.age').write_bytes(b'corrupted')
                with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                    recovery.validate(folder)
                with self.assertRaisesRegex(RuntimeError, 'retained local backup'):
                    recovery.validate(root)

    def test_invalid_restore_causes_no_mutation(self):
        with patch.object(recovery, 'validate', side_effect=RuntimeError('invalid checkpoint')), \
             patch.object(recovery, 'docker') as docker:
            with self.assertRaisesRegex(RuntimeError, 'invalid checkpoint'):
                recovery.drill('unused')
        docker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
