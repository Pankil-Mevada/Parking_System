"""Report acceptance gates; never infer approval from missing evidence."""
import json
from parking_tools import ROOT, cli

def blockers(config):
    missing=[name for name,accepted in config['gates'].items() if accepted is not True]
    for name in ('loadTargetConcurrentUsers','alertOwner','incidentOwner','availabilityTarget','recoveryTimeTargetSeconds','recoveryPointTargetSeconds'):
        if not config.get(name):missing.append(name)
    if not config['jurisdiction'].get('state'):missing.append('operatingState')
    return missing

def main():
    config=json.loads((ROOT/'operations/launch-gates.json').read_text())
    pending=blockers(config)
    print('Operating country:',config['jurisdiction']['country'])
    print('Launch status:', 'BLOCKED' if pending else 'Acceptance recorded; deployment still requires authorization')
    for item in pending:print('PENDING:',item)
    if pending:raise RuntimeError('Launch gates remain pending. This does not prevent local development.')

if __name__=='__main__':cli(main)
