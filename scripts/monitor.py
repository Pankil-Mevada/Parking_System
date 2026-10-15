"""One local health/metrics inspection. Does not send messages externally."""
import json
import urllib.request
from identity_admin import environment
from parking_tools import cli

def inspect():
    token=environment().get('OPS_METRICS_TOKEN','')
    if len(token)<32:raise RuntimeError('Run py scripts/setup_auth.py to configure the private metrics token.')
    result={'ready':False,'alerts':[],'thresholds':'provisional local thresholds; operator must approve'}
    try:
        with urllib.request.urlopen('http://127.0.0.1:8080/api/ready',timeout=5) as response:result['ready']=response.status==200
        request=urllib.request.Request('http://127.0.0.1:8080/internal/metrics',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(request,timeout=5) as response:raw=response.read(1024*1024).decode()
        values={line.split()[0]:float(line.split()[1]) for line in raw.splitlines() if line and not line.startswith('#') and '{' not in line}
        result['metrics']=values
        if values.get('parking_outbox_lag_seconds',0)>5:result['alerts'].append('outbox lag exceeds 5 seconds')
        if values.get('parking_db_connections',0)/max(1,values.get('parking_db_max_connections',1))>.8:result['alerts'].append('database connections exceed 80%')
        if values.get('parking_stream_clients_stale',0):result['alerts'].append('recent dashboard clients have stale heartbeats')
    except OSError:result['alerts'].append('API readiness or private metrics unavailable')
    if not result['ready']:result['alerts'].append('API not ready')
    return result

def main():
    result=inspect();print(json.dumps(result,indent=2))
    if result['alerts']:raise RuntimeError('Local monitor reports alerts; inspect the runbook.')

if __name__=='__main__':cli(main)
