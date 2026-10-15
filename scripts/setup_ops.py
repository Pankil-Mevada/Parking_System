"""Install checksum-pinned age and Grype into ignored project-local tools."""
import hashlib
import io
import json
import os
import tarfile
import urllib.request
import zipfile
from parking_tools import ROOT,cli

def main():
    config=json.loads((ROOT/'operations/tools.lock.json').read_text())
    platform='windows' if os.name=='nt' else 'linux'
    folder=ROOT/'.tools/ops';folder.mkdir(parents=True,exist_ok=True)
    for name,tool in config.items():
        asset=tool[platform];directory=folder/(name+'-'+tool['version']);directory.mkdir(exist_ok=True)
        executable=directory/(name+('.exe' if os.name=='nt' else ''))
        if executable.exists():print(name,tool['version'],'already installed');continue
        url=f"https://github.com/{tool['repository']}/releases/download/v{tool['version']}/{asset['asset']}"
        with urllib.request.urlopen(url,timeout=60) as response:data=response.read(150*1024*1024)
        if hashlib.sha256(data).hexdigest()!=asset['sha256']:raise RuntimeError(name+' download checksum mismatch; not installed')
        suffix='.exe' if os.name=='nt' else ''
        wanted={name+suffix}
        if name=='age':wanted.add('age-keygen'+suffix)
        if platform=='windows':
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for item in archive.infolist():
                    basename=item.filename.rsplit('/',1)[-1]
                    if basename in wanted:(directory/basename).write_bytes(archive.read(item))
        else:
            with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
                for item in archive.getmembers():
                    basename=item.name.rsplit('/',1)[-1]
                    if item.isfile() and basename in wanted:
                        (directory/basename).write_bytes(archive.extractfile(item).read());(directory/basename).chmod(0o700)
        if not executable.exists():raise RuntimeError(name+' executable missing from verified archive')
        print(name,tool['version'],'installed with SHA-256 verification')

if __name__=='__main__':cli(main)
