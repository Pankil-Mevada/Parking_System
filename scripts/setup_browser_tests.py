"""Install pinned browser testing tools locally; py scripts/setup_browser_tests.py."""
import os
import subprocess
import sys
from parking_tools import ROOT, cli

def main():
    subprocess.run([sys.executable,'-m','pip','install','--target',str(ROOT/'.tools/test-python'),'-r',str(ROOT/'requirements-browser.txt')],check=True)
    env=os.environ.copy()
    env['PYTHONPATH']=str(ROOT/'.tools/test-python')
    env['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.tools/browsers')
    subprocess.run([sys.executable,'-m','playwright','install','chromium'],env=env,check=True)

if __name__=='__main__': cli(main)
