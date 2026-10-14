"""Run frontend tools: py scripts/pnpm.py build. Supplies Node to child processes."""
import sys
from parking_tools import cli, pnpm

if __name__ == '__main__':
    cli(lambda: pnpm(sys.argv[1:] or ['--version']) and 0)
