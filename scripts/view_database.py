"""Local owner-only, read-only PostgreSQL browser: py scripts/view_database.py --start."""
import argparse
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlparse
from identity_admin import environment
from parking_tools import ROOT, active_wsl, cli, docker, wsl

sys.path.insert(0,str(ROOT/'.tools/test-python'))
try:
    import psycopg
    from psycopg import sql
except ImportError:
    raise SystemExit('Install the local viewer driver: py -m pip install --target .tools/test-python -r requirements-test.txt')

ASSETS=Path(__file__).resolve().parent/'database_viewer'


def connection(database):
    env=environment()
    if database=='development':
        options={'port':5432,'dbname':env['POSTGRES_DB'],'user':env['POSTGRES_USER']}
    elif database=='tests':
        options={'port':15432,'dbname':'parking_test','user':'parking_test'}
    else:
        raise ValueError('Unknown database')
    conn=psycopg.connect(host='127.0.0.1',password=env['POSTGRES_PASSWORD'],connect_timeout=3,**options)
    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
    conn.execute("SET LOCAL statement_timeout='3s'")
    return conn


def schemas(conn):
    return [row[0] for row in conn.execute("SELECT nspname FROM pg_namespace WHERE nspname='public' OR nspname LIKE 'run\\_%' ESCAPE '\\' ORDER BY nspname")]


def tables(conn,schema):
    return [row[0] for row in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name",(schema,))]


def catalog():
    result=[]
    for name in ('development','tests'):
        item={'id':name,'label':'Development parking database' if name=='development' else 'Retained test database'}
        try:
            with connection(name) as conn:
                item['schemas']=schemas(conn)
        except psycopg.Error:
            item['schemas']=[]
            item['error']='Database is not running. Start this viewer with --start.'
        result.append(item)
    return {'databases':result}


def rows(database,schema,table,page):
    if not re.fullmatch(r'[a-zA-Z0-9_]{1,63}',schema) or not re.fullmatch(r'[a-zA-Z0-9_]{1,63}',table):
        raise ValueError('Invalid schema or table')
    if not 0<=page<=10000:
        raise ValueError('Invalid page')
    with connection(database) as conn:
        if schema not in schemas(conn) or table not in tables(conn,schema):
            raise ValueError('Unknown schema or table')
        target=sql.Identifier(schema,table)
        count=conn.execute(sql.SQL('SELECT count(*) FROM {}').format(target)).fetchone()[0]
        cursor=conn.execute(sql.SQL('SELECT * FROM {} LIMIT 100 OFFSET %s').format(target),(page*100,))
        columns=[column.name for column in cursor.description]
        return {'columns':columns,'rows':cursor.fetchall(),'total':count,'page':page,'pageSize':100}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def send(self,status,body,content_type='application/json'):
        data=json.dumps(body,default=str).encode() if content_type=='application/json' else body
        self.send_response(status)
        self.send_header('Content-Type',content_type+'; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        port=self.server.server_port
        if self.headers.get('Host') not in (f'127.0.0.1:{port}',f'localhost:{port}') or self.headers.get('Sec-Fetch-Site')=='cross-site':
            self.send(403,{'error':'Local owner access only'})
            return
        path=urlparse(self.path)
        query={key:values[-1] for key,values in parse_qs(path.query).items()}
        try:
            assets={'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
            if path.path in assets:
                name,kind=assets[path.path]
                self.send(200,(ASSETS/name).read_bytes(),kind)
            elif path.path=='/api/catalog':
                self.send(200,catalog())
            elif path.path=='/api/tables':
                with connection(query.get('database','development')) as conn:
                    schema=query.get('schema','public')
                    if schema not in schemas(conn):
                        raise ValueError('Unknown schema')
                    self.send(200,{'tables':tables(conn,schema)})
            elif path.path=='/api/rows':
                self.send(200,rows(query.get('database','development'),query.get('schema','public'),query.get('table','locations'),int(query.get('page','0'))))
            else:
                self.send(404,{'error':'Not found'})
        except (ValueError,KeyError):
            self.send(400,{'error':'Invalid selection'})
        except psycopg.Error:
            self.send(503,{'error':'Database unavailable or query failed'})


def main():
    parser=argparse.ArgumentParser(description='Read-only developer database viewer. Local machine owner access; do not expose publicly.')
    parser.add_argument('--port',type=int,default=8090)
    parser.add_argument('--start',action='store_true',help='Start WSL Docker and existing parking/test database containers.')
    args=parser.parse_args()
    if not 1024<=args.port<=65535:
        parser.error('Choose port 1024–65535')
    with active_wsl() if args.start else nullcontext():
        if args.start:
            wsl(['systemctl','start','docker'])
            docker(['compose','up','-d','db'])
            runs=sorted((ROOT/'.tools/test-runs').glob('*.env'),key=lambda path:path.stat().st_mtime)
            if runs:
                docker(['compose','--env-file','.env','--env-file',runs[-1].relative_to(ROOT).as_posix(),
                        '-f','compose.yaml','-f','compose.test.yaml','--profile','phase34','up','-d','test-db'])
        server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
        print(f'Read-only local database viewer: http://127.0.0.1:{args.port}',flush=True)
        print('Keep this terminal open. No delete/write actions are provided.',flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()


if __name__=='__main__':
    cli(main)
