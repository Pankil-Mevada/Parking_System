"""Local native API launcher; imports auth configuration and binds loopback."""
import argparse
import os
import re
import subprocess
from parking_tools import ROOT,cli,port_in_use
from identity_admin import environment

def configured_environment():
    env=environment()|os.environ
    env['API_DATABASE_URL']=re.sub(r'(^|\s)host=db(?=\s|$)',r'\1host=127.0.0.1',env.get('API_DATABASE_URL',''))
    defaults={'OIDC_INTERNAL_URL':'http://127.0.0.1:8180','OIDC_REALM':'parking','OIDC_ISSUER':'http://127.0.0.1:8180/realms/parking','APP_ORIGIN':'http://127.0.0.1:5173','API_LISTEN_HOST':'127.0.0.1'}
    for name,value in defaults.items():env.setdefault(name,value)
    for name in ['API_DATABASE_URL','OIDC_CLIENT_SECRET',*defaults]:
        if not env.get(name) or 'REPLACE_WITH_' in env[name]:raise RuntimeError(name+' is missing; no credentials printed')
    return env

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
    env=configured_environment()
    if args.check_only:print('Native environment is complete; secrets not printed. Executable/build not verified.');return
    path=ROOT/'build/native-windows/Release/parking_api.exe'
    if not path.exists():raise RuntimeError('Native executable missing. MSVC Build Tools and scripts/build-native.ps1 are required.')
    if port_in_use(8080):raise RuntimeError('Port 8080 already in use. No process was stopped.')
    subprocess.run([str(path)],cwd=ROOT,env=env,check=True)

if __name__=='__main__':cli(main)
