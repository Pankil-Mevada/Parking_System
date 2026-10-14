"""Start the local parking system: py scripts/start_dev.py."""
import argparse
import time
import urllib.error
import urllib.request

from parking_tools import ROOT, active_wsl, cli, docker, node_tools, pnpm, port_in_use, wsl


def main():
    parser = argparse.ArgumentParser(description='Start the parking frontend and WSL Docker backend.')
    parser.add_argument('--port', type=int, default=5173, help='Frontend port (default: 5173).')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a port from 1024 through 65535.')
    if port_in_use(args.port):
        print(f'Port {args.port} is already in use. If the parking page is running, open http://127.0.0.1:{args.port}.')
        print('To restart it, press Ctrl+C in its existing terminal first. No process was stopped.')
        return
    node_tools()
    if not (ROOT / '.env').is_file():
        raise RuntimeError('Local .env is missing. Follow README setup before starting.')
    with active_wsl():
        wsl(['systemctl', 'start', 'docker'])
        docker(['compose', 'up', '-d'])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=2) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError('The API did not become ready. Check: py scripts/docker_wsl.py compose logs api db')
        if not (ROOT / 'node_modules').is_dir():
            pnpm(['install', '--frozen-lockfile'])
        print(f'Open http://127.0.0.1:{args.port}. Keep this terminal open. Ctrl+C stops the frontend.', flush=True)
        pnpm(['dev', '--port', str(args.port)])


if __name__ == '__main__':
    cli(main)
