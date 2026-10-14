"""Shared local-development tooling. Python standard library only; no PowerShell."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import shutil
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies'


def node_tools() -> tuple[Path, Path, dict[str, str]]:
    node = Path(shutil.which('node.exe') or shutil.which('node') or RUNTIME / 'node/bin/node.exe')
    pnpm_command = shutil.which('pnpm.cmd')
    candidates = [RUNTIME / 'node/node_modules/pnpm/bin/pnpm.mjs']
    if pnpm_command:
        folder = Path(pnpm_command).parent
        candidates.extend(folder / f'node_modules/pnpm/bin/pnpm.{extension}' for extension in ('cjs', 'mjs'))
    if not node.is_file():
        raise RuntimeError('Node.js is missing. Install Node.js 24 LTS or restore the bundled Codex runtime.')
    pnpm = next((candidate for candidate in candidates if candidate.is_file()), None)
    if pnpm is None:
        raise RuntimeError('pnpm is missing. Install pnpm 11.25.0 or restore the bundled Codex runtime.')
    env = os.environ.copy()
    env['PATH'] = str(node.parent) + os.pathsep + env.get('PATH', '')
    return node, pnpm, env


def pnpm(arguments: list[str], **options) -> subprocess.CompletedProcess:
    node, entry, env = node_tools()
    # Invoke JavaScript directly, avoiding .cmd files and shell quoting entirely.
    return subprocess.run([str(node), str(entry), *arguments], cwd=ROOT, env=env, check=True, **options)


def wsl(arguments: list[str], **options) -> subprocess.CompletedProcess:
    executable = shutil.which('wsl.exe')
    if not executable:
        raise RuntimeError('Ubuntu WSL is required. See README for local setup.')
    return subprocess.run([executable, '-d', 'Ubuntu', '-u', 'root', '--exec', *arguments], check=True, **options)


def docker(arguments: list[str], **options) -> subprocess.CompletedProcess:
    path = wsl(['wslpath', '-u', ROOT.as_posix()], capture_output=True, text=True).stdout.strip()
    executable = shutil.which('wsl.exe')
    return subprocess.run([
        executable, '-d', 'Ubuntu', '-u', 'root', '--cd', path, '--exec',
        'env', '-u', 'DOCKER_HOST', '-u', 'DOCKER_CONTEXT',
        'docker', '--host', 'unix:///var/run/docker.sock', *arguments
    ], check=True, **options)


@contextlib.contextmanager
def active_wsl():
    """A foreground WSL process keeps Ubuntu alive while this context is active."""
    executable = shutil.which('wsl.exe')
    if not executable:
        raise RuntimeError('Ubuntu WSL is required. See README for local setup.')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    process = subprocess.Popen([executable, '-d', 'Ubuntu', '--exec', 'sleep', 'infinity'], creationflags=flags)
    try:
        yield
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def cli(action) -> None:
    try:
        result = action()
        raise SystemExit(result or 0)
    except KeyboardInterrupt:
        print('\nStopped. Your database files have not been deleted.')
        raise SystemExit(0)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}')
        raise SystemExit(1)
