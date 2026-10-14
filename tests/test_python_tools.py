"""Regression checks for Python launchers; no additional Python packages required."""
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from parking_tools import pnpm


@unittest.skipUnless(os.name == 'nt', 'These regressions target the Windows launcher.')
class WindowsToolTests(unittest.TestCase):
    def test_build_runs_without_node_or_pnpm_on_path(self):
        clean_path = str(Path(os.environ['SystemRoot']) / 'System32')
        with patch.dict(os.environ, {'PATH': clean_path}):
            self.assertIsNone(shutil.which('node.exe'))
            self.assertIsNone(shutil.which('pnpm.cmd'))
            try:
                pnpm(['build'], capture_output=True, text=True)
            except subprocess.CalledProcessError as error:
                self.fail(f'Clean-PATH frontend build failed:\n{error.stdout}\n{error.stderr}')
            self.assertEqual(os.environ['PATH'], clean_path)

    def test_node_child_runs_without_node_on_path(self):
        clean_path = str(Path(os.environ['SystemRoot']) / 'System32')
        with patch.dict(os.environ, {'PATH': clean_path}):
            result = pnpm(['exec', 'node', '--version'], capture_output=True, text=True)
            self.assertRegex(result.stdout.strip(), r'^v\d+\.\d+\.\d+$')
            self.assertEqual(os.environ['PATH'], clean_path)

    def test_single_argument_is_forwarded(self):
        result = pnpm(['--version'], capture_output=True, text=True)
        self.assertRegex(result.stdout.strip(), r'^\d+\.\d+\.\d+$')

    def test_duplicate_start_does_not_launch_another_server(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            result = subprocess.run([
                sys.executable, str(ROOT / 'scripts/start_dev.py'), '--port', str(port)
            ], cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('already in use', result.stdout)


if __name__ == '__main__':
    unittest.main()
