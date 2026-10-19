import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from scan_secrets import findings, scan, main


class SecretScanTests(unittest.TestCase):
    def test_signatures_are_found_without_returning_values(self):
        samples = (
            b'-----BEGIN ' + b'PRIVATE KEY-----',
            b'ghp_' + b'A' * 36,
            b'github_pat_' + b'A' * 70,
            b'AKIA' + b'A' * 16,
            b'xoxb-' + b'A' * 24,
            b'postgresql://' + b'person:private@database/app',
        )
        for value in samples:
            with self.subTest(prefix=value[:4]):
                result = findings('fixture.txt', b'first line\n' + value)
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0][:2], ('fixture.txt', 2))
                self.assertNotIn(value.decode(), repr(result))

    def test_placeholders_and_environment_references_are_allowed(self):
        self.assertEqual(findings('example', b'password=REPLACE_ME\n${POSTGRES_PASSWORD}\nghp_short'), [])

    def test_cli_fails_on_findings_and_scanner_errors(self):
        output = StringIO()
        with patch('scan_secrets.scan', return_value=[('source.txt', 4, 'github-token')]), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertIn('value redacted', output.getvalue())
        error = StringIO()
        with patch('scan_secrets.scan', side_effect=OSError('private diagnostic')), redirect_stderr(error):
            self.assertEqual(main(), 2)
        self.assertNotIn('private diagnostic', error.getvalue())
        with patch('scan_secrets.scan', return_value=[]), redirect_stdout(StringIO()):
            self.assertEqual(main(), 0)

    def test_only_tracked_snapshot_is_read_and_new_edits_are_scanned(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', folder], check=True, capture_output=True)
            source = root / 'source.txt'
            source.write_text('safe')
            subprocess.run(['git', 'add', 'source.txt'], cwd=root, check=True, capture_output=True)
            (root / '.env').write_bytes(b'ghp_' + b'B' * 36)
            self.assertEqual(scan(root), [])
            source.write_bytes(b'ghp_' + b'C' * 36)
            self.assertEqual(scan(root), [('source.txt', 1, 'github-token')])


if __name__ == '__main__':
    unittest.main()
