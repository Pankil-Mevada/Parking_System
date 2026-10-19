"""Encrypted local PostgreSQL backup and retained, isolated restore drill.

Keycloak development H2 is deliberately outside this PostgreSQL-only drill.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from parking_tools import ROOT, cli, docker
from ops_tools import tool, postgres

COMPOSE=['compose','-f','compose.yaml','-f','compose.operations.yaml','--profile','operations']

def key():
    folder=ROOT/'.tools/backup-keys';folder.mkdir(parents=True,exist_ok=True)
    path=folder/'parking.agekey'
    if not path.exists():
        subprocess.run([tool('age-keygen'),'-o',str(path)],check=True,capture_output=True)
        os.chmod(path,0o600)
    recipient=subprocess.run([tool('age-keygen'),'-y',str(path)],check=True,capture_output=True,text=True).stdout.strip()
    return path,recipient

def backup():
    _,recipient=key();folder=ROOT/'.tools/backups'/str(uuid.uuid4());folder.mkdir(parents=True)
    target=folder/'parking.dump.age'
    with postgres() as connection:
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        snapshot=connection.execute('SELECT pg_export_snapshot()').fetchone()[0]
        tables=connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
        from psycopg import sql
        counts={name:connection.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(name))).fetchone()[0] for name, in tables}
        process=subprocess.Popen([tool('age'),'-r',recipient,'-o',str(target)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            docker(['compose','exec','-T','db','sh','-c','exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl --snapshot "$1"','sh',snapshot],stdout=process.stdin)
        finally:
            process.stdin.close();process.stdin=None
        _,error=process.communicate(timeout=60)
        if process.returncode:raise RuntimeError('Backup encryption failed; incomplete output retained for inspection.')
    manifest={'createdAt':datetime.now(timezone.utc).isoformat(),'scope':'parking PostgreSQL only; identity H2 excluded','cipherSha256':hashlib.file_digest(target.open('rb'),'sha256').hexdigest(),'tableCounts':counts}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Encrypted backup retained:',folder)
    return folder

def restore(folder):
    folder=Path(folder).resolve();root=(ROOT/'.tools/backups').resolve()
    if not folder.is_relative_to(root):raise RuntimeError('Restore input must be a retained local backup directory.')
    manifest=json.loads((folder/'manifest.json').read_text());cipher=folder/'parking.dump.age'
    with cipher.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    if digest!=manifest['cipherSha256']:raise RuntimeError('Backup checksum mismatch.')
    started=time.monotonic();name='restore_'+uuid.uuid4().hex
    docker(COMPOSE+['up','-d','--wait','restore-db'])
    docker(COMPOSE+['exec','-T','restore-db','createdb','-U','parking_restore',name])
    private,_=key()
    process=subprocess.Popen([tool('age'),'-d','-i',str(private),str(cipher)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:docker(COMPOSE+['exec','-T','restore-db','pg_restore','--exit-on-error','--no-owner','--no-acl','-U','parking_restore','-d',name],stdin=process.stdout)
    finally:
        process.stdout.close();process.stdout=None
    _,error=process.communicate(timeout=60)
    if process.returncode:raise RuntimeError('Backup decryption failed; restore database retained.')
    queries=[]
    for table in manifest['tableCounts']:
        # Quote both the SQL identifier and the separate JSON name literal.
        quoted='"'+table.replace('"','""')+'"'
        literal="'"+table.replace("'","''")+"'"
        queries.append("SELECT json_build_object('table',"+literal+",'count',count(*)) FROM "+quoted+';')
    if queries:
        # A single invocation avoids starting WSL once per table on Windows.
        result=docker(COMPOSE+['exec','-T','restore-db','psql','-X','-At','-v','ON_ERROR_STOP=1','-U','parking_restore','-d',name,'-c','\n'.join(queries)],capture_output=True,text=True)
        rows=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        actual={row['table']:row['count'] for row in rows}
        if actual!=manifest['tableCounts']:raise RuntimeError('Restored table counts differ from the checkpoint.')
    report={'database':name,'verifiedTableCounts':True,'elapsedSeconds':round(time.monotonic()-started,3),'identityRestored':False,'retained':True}
    path=folder/('restore-'+name+'.json');path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--restore');parser.add_argument('--drill',action='store_true');args=parser.parse_args()
    if args.restore:restore(args.restore)
    else:
        folder=backup()
        if args.drill:restore(folder)

if __name__=='__main__':cli(main)
