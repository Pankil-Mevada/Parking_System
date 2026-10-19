"""Dedicated persistent Linux runner orchestration; no deployment or cleanup."""
import json
import os
import secrets
import subprocess
import sys
from parking_tools import ROOT,cli,docker,pnpm,node_tools,port_in_use

def python(*args):subprocess.run([sys.executable,*args],cwd=ROOT,check=True)

def main():
    if os.name=='nt':raise RuntimeError('CI orchestration targets the dedicated Linux runner; use documented local test commands on Windows.')
    python('scripts/scan_secrets.py')
    python('-m','unittest','discover','-s','tests','-p','test_secret_scan.py','-v')
    python('-m','unittest','discover','-s','tests','-p','test_recovery.py','-v')
    python('-m','unittest','discover','-s','tests','-p','test_device_simulator.py','-v')
    if port_in_use(5173):raise RuntimeError('Dedicated runner port 5173 is already in use. No unrelated process was stopped.')
    path=ROOT/'.env'
    if not path.exists():
        password=secrets.token_hex(32)
        path.write_text('POSTGRES_DB=parking\nPOSTGRES_USER=parking_owner\nPOSTGRES_PASSWORD='+password+'\nAPI_DATABASE_URL=host=db port=5432 dbname=parking user=parking_owner password='+password+'\n')
        os.chmod(path,0o600)
    python('scripts/setup_auth.py')
    pnpm(['install','--frozen-lockfile']);pnpm(['test']);pnpm(['build'])
    python('-m','compileall','-q','scripts','tests')
    python('-m','pip','install','--target',str(ROOT/'.tools/test-python'),'-r','requirements-test.txt')
    python('scripts/setup_browser_tests.py');python('scripts/setup_ops.py')
    docker(['compose','build','api']);docker(['compose','up','-d','db','identity','identity-gateway','mail'])
    python('scripts/configure_identity.py')
    migration=['compose','exec','-T','db','sh','-c','psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /workspace/database/migrate.sql']
    docker(migration);docker(migration);docker(['compose','up','-d','api'])
    node,entry,env=node_tools()
    frontend=subprocess.Popen([str(node),str(entry),'dev'],cwd=ROOT,env=env)
    try:
        from test_phase34 import wait
        wait('http://127.0.0.1:8080/api/ready');wait('http://127.0.0.1:5173/')
        python('scripts/test_system.py');python('scripts/test_phase34.py')
        python('scripts/test_phase34.py','--password-only','--test-name','test_36','--test-name','test_4')
        python('-m','unittest','discover','-s','tests','-p','test_operations.py')
        python('scripts/backup_database.py','--drill')
        python('scripts/scan_dependencies.py')
    finally:
        frontend.terminate();frontend.wait(timeout=10)
    print('Verification finished. Databases, realms, encrypted backups and reports retained on the dedicated runner.')

if __name__=='__main__':cli(main)
