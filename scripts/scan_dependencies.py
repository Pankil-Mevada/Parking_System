"""Scan the built API archive with pinned Grype; retain JSON evidence locally."""
from datetime import datetime,timezone
import json
import subprocess
import os
import uuid
from parking_tools import ROOT,cli,docker,pnpm
from ops_tools import tool

def main():
    folder=ROOT/'.tools/security-results'/str(uuid.uuid4());folder.mkdir(parents=True)
    archive=folder/'api-image.tar'
    with archive.open('wb') as output:docker(['image','save','vehicle-parking-system-api:latest'],stdout=output)
    env=os.environ.copy();env['GRYPE_DB_CACHE_DIR']=str(ROOT/'.tools/grype-db')
    with (folder/'grype.json').open('w',encoding='utf-8') as output:
        result=subprocess.run([tool('grype'),'docker-archive:'+str(archive),'-o','json','--fail-on','high'],stdout=output,env=env)
    npm_status=0
    try:
        with (folder/'pnpm-audit.json').open('w',encoding='utf-8') as output:pnpm(['audit','--json'],stdout=output)
    except subprocess.CalledProcessError as error:npm_status=error.returncode
    summary={'time':datetime.now(timezone.utc).isoformat(),'grypeExitCode':result.returncode,'pnpmAuditExitCode':npm_status,'scope':'built API image and lockfile dependencies; not independent application security review'}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('Retained dependency reports:',folder)
    if result.returncode or npm_status:raise RuntimeError('Dependency scanning reported vulnerabilities or could not complete; inspect retained results.')

if __name__=='__main__':cli(main)
