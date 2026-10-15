"""Bounded local API read load; authenticated heartbeats may update telemetry."""
import argparse
import concurrent.futures
from datetime import datetime,timezone
import json
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from parking_tools import ROOT,cli

def measure(url,concurrency=20,duration=10,token=None,location=None):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.port not in (8080,18080,18081) or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:raise RuntimeError('Load tests are restricted to the local parking API.')
    if not 1<=concurrency<=500 or not 1<=duration<=120:raise RuntimeError('Bounded load requires 1–500 workers and 1–120 seconds.')
    paths=['/api/health','/api/ready','/api/locations']
    if token:
        if not location:raise RuntimeError('Authenticated load requires a location.')
        uuid.UUID(location);paths=['/api/me/dashboard',f'/api/locations/{location}/dashboard',f'/api/locations/{location}/events?after=0']
    ready=threading.Barrier(concurrency+1)
    started=0.;deadline=0.
    lock=threading.Lock();inflight=0;peak=0
    def worker(index):
        nonlocal inflight,peak
        samples=[];counter=index
        ready.wait(timeout=60)
        while time.monotonic()<deadline:
            begin=time.monotonic();code=0
            with lock:
                inflight+=1;peak=max(peak,inflight)
            try:
                headers={'Authorization':'Bearer '+token} if token else {}
                with urllib.request.urlopen(urllib.request.Request(url.rstrip('/')+paths[counter%len(paths)],headers=headers),timeout=5) as response:
                    response.read(1024*1024);code=response.status
            except urllib.error.HTTPError as error:code=error.code;error.close()
            except (OSError,TimeoutError):pass
            finally:
                with lock:inflight-=1
            samples.append((time.monotonic()-begin,code));counter+=1
            time.sleep(.1)
        return samples
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures=[pool.submit(worker,index) for index in range(concurrency)]
        # Release all virtual clients together; thread startup is outside the measurement.
        started=time.monotonic();deadline=started+duration
        ready.wait(timeout=60)
        samples=[sample for future in futures for sample in future.result()]
    elapsed=time.monotonic()-started;values=sorted(sample[0] for sample in samples);failures=sum(not 200<=sample[1]<300 for sample in samples)
    def percentile(p):return round(values[min(len(values)-1,math.ceil(len(values)*p)-1)]*1000,3) if values else None
    result = {'timestamp':datetime.now(timezone.utc).isoformat(),'scope':'local provisional baseline; not agreed staging capacity','scenario':'authenticated dashboard/SSE reads' if token else 'public API reads','concurrency':concurrency,'requestedSeconds':duration,'elapsedSeconds':round(elapsed,3),'requests':len(samples),'errors':failures,'errorRate':failures/len(samples) if samples else 1,'requestsPerSecond':round(len(samples)/elapsed,2),'p50Ms':percentile(.5),'p95Ms':percentile(.95),'p99Ms':percentile(.99),'statusCounts':{str(status):sum(code==status for _,code in samples) for status in set(code for _,code in samples)},'businessWritesPerformed':False,'telemetryWritesPossible':bool(token)}
    result['peakInFlightRequests']=peak
    result['thinkTimeMs']=100
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8080');parser.add_argument('--concurrency',type=int,default=20);parser.add_argument('--seconds',type=int,default=10);parser.add_argument('--location');args=parser.parse_args()
    result=measure(args.url,args.concurrency,args.seconds,os.environ.get('PARKING_LOAD_TOKEN'),args.location)
    folder=ROOT/'.tools/load-results';folder.mkdir(parents=True,exist_ok=True);path=folder/(str(uuid.uuid4())+'.json');path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));print('Retained report:',path)
    if result['errors']:raise RuntimeError('Local load produced errors; inspect the report, do not claim a passing capacity target.')

if __name__=='__main__':cli(main)
