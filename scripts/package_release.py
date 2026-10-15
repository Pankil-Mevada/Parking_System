"""Create a retained versioned review bundle; never deploy or push an image."""
import hashlib
import json
import shutil
import subprocess
import uuid
from datetime import datetime,timezone
from parking_tools import ROOT,cli,docker,pnpm

def main():
    pnpm(['build']);docker(['compose','build','api'])
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
    dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip())
    version=commit[:12]+('-working-'+uuid.uuid4().hex[:8] if dirty else '')
    folder=ROOT/'.tools/releases'/version;folder.mkdir(parents=True,exist_ok=False)
    image=docker(['image','inspect','vehicle-parking-system-api:latest','--format','{{.Id}}'],capture_output=True,text=True).stdout.strip()
    with (folder/'api-image.tar').open('wb') as output:docker(['image','save',image],stdout=output)
    shutil.copytree(ROOT/'dist',folder/'frontend');shutil.copytree(ROOT/'database/migrations',folder/'migrations')
    shutil.copy2(ROOT/'operations/launch-gates.json',folder/'launch-gates.json')
    files={str(path.relative_to(folder)).replace('\\','/'):hashlib.file_digest(path.open('rb'),'sha256').hexdigest() for path in folder.rglob('*') if path.is_file()}
    manifest={'version':version,'baseCommit':commit,'workingTreeChangesIncluded':dirty,'createdAt':datetime.now(timezone.utc).isoformat(),'apiImageId':image,'files':files,'productionDeploymentApproved':False}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Review bundle retained:',folder)
    print('No deployment performed. Check launch gates before promoting an immutable bundle.')

if __name__=='__main__':cli(main)
