"""Explain and run phase 1-2 checks: py scripts/test_system.py."""
import sys
from parking_tools import ROOT, cli, docker, pnpm
import subprocess
import json
import urllib.error
import urllib.request


def check_website():
    try:
        with urllib.request.urlopen('http://127.0.0.1:5173/', timeout=5) as response:
            page = response.read(1024 * 1024).decode('utf-8')
        if '<title>Vehicle Parking System</title>' not in page:
            raise RuntimeError('Port 5173 is serving a different page. Check the frontend terminal.')
        with urllib.request.urlopen('http://127.0.0.1:5173/api/locations', timeout=5) as response:
            snapshot = json.load(response)
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get('locations'), list):
            raise RuntimeError('The frontend API proxy did not return parking availability.')
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise RuntimeError("The website or its API proxy is not reachable. Run 'py scripts/start_dev.py' in another terminal and keep it open, then retry these tests.") from error


def main():
    checks = [
        ('Website running', 'Checks the actual page on port 5173 and its connection to the API. This test does not start the website.', check_website),
        ('Project scaffold', 'Checks selected source rules, safe page rendering and migration setup. These are basic code checks, not security certification.', lambda: pnpm(['test'])),
        ('Frontend build', 'Checks that TypeScript is valid and the website can be packaged. It does not visually inspect the page.', lambda: pnpm(['build'])),
        ('Running API', 'Checks that the server/database are ready, public responses contain only allowed fields, and available + occupied equals operational capacity.', lambda: pnpm(['test:api'])),
        ('Database parking rules', 'Uses temporary test records to check uniqueness, occupied-space conflicts and preserved history. All test records are rolled back.', lambda: docker([
            'compose', 'exec', '-T', 'db', 'sh', '-c',
            'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /workspace/database/tests/constraints.sql'
        ])),
        ('Python launcher tools', 'Checks that Node and the full build work without global Node/pnpm on PATH, arguments are forwarded correctly, and duplicate starts are handled.', lambda: subprocess.run([
            sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_python_tools.py', '-v'
        ], cwd=ROOT, check=True)),
    ]
    for number, (name, explanation, run) in enumerate(checks, 1):
        print(f'\n[{number}/{len(checks)}] {name}\n{explanation}', flush=True)
        run()
        print(f'PASS: {name}', flush=True)
    print('\nAll phase 1-2 checks passed. Keep the startup terminal open to keep the website available.')
    print('These tests do not start the website. Run py scripts/test_phase34.py for authentication, parking concurrency and rollback checks. Realtime remains a later phase.')


if __name__ == '__main__':
    cli(main)
