"""Run Docker commands in Ubuntu WSL: py scripts/docker_wsl.py compose ps."""
import sys
from parking_tools import cli, docker

if __name__ == '__main__':
    cli(lambda: docker(sys.argv[1:] or ['version']) and 0)
