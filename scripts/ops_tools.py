import json
import os
import sys
from pathlib import Path
from parking_tools import ROOT

def tool(name):
    versions=json.loads((ROOT/'operations/tools.lock.json').read_text())
    package='age' if name=='age-keygen' else name
    path=ROOT/'.tools/ops'/(package+'-'+versions[package]['version'])/(name+('.exe' if os.name=='nt' else ''))
    if not path.is_file():raise RuntimeError('Missing operational tools. Run: py scripts/setup_ops.py')
    return str(path)

def postgres():
    sys.path.insert(0,str(ROOT/'.tools/test-python'))
    import psycopg
    from identity_admin import environment
    env=environment()
    return psycopg.connect(host='127.0.0.1',port=5432,dbname=env['POSTGRES_DB'],user=env['POSTGRES_USER'],password=env['POSTGRES_PASSWORD'])
