"""Real HTTP/API and Chromium checks for the isolated local device simulator."""
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from parking_tools import ROOT


def verify(simulator, case, folder):
    base = 'http://127.0.0.1:8766'
    def get():
        with urllib.request.urlopen(base + '/api/state', timeout=15) as response:
            return json.load(response)
    key = get()['key']
    def event(action, identifier=None, **values):
        data = {'eventId': identifier or str(uuid.uuid4()), 'action': action, **values}
        req = urllib.request.Request(base + '/api/events', json.dumps(data).encode(), {
            'Content-Type': 'application/json', 'Origin': base, 'X-Simulator-Key': key})
        try:
            response = urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)
    def check(condition, message):
        if not condition:
            raise AssertionError(message)
    checks = []
    arrival = str(uuid.uuid4())
    check(event('arrive', arrival, bay='P01', tag='DEMO-CARD-A')[0] == 201, 'Known card arrival failed')
    check(event('arrive', arrival, bay='P01', tag='DEMO-CARD-A')[1]['replayed'], 'Duplicate event was not replayed')
    check(case.scalar('SELECT count(*) FROM parking_sessions') == 1, 'Duplicate arrival created another session')
    check(event('arrive', arrival, bay='P02', tag='DEMO-CARD-A')[0] == 409, 'Changed-body event ID was accepted')
    checks.append('RFID arrival, durable replay and changed-body conflict')
    check(event('arrive', bay='P02', tag='UNKNOWN-CARD')[0] == 403, 'Unknown card was accepted')
    for mode in ('offline', 'obstructed'):
        check(event('gate', mode=mode)[0] == 200, 'Gate mode failed')
        check(event('arrive', bay='P02', tag='DEMO-CARD-B')[0] == 409, 'Faulty gate accepted arrival')
    check(case.scalar('SELECT count(*) FROM parking_sessions') == 1, 'Denied action wrote a session')
    event('gate', mode='normal')
    checks.append('Unknown RFID, offline gate and obstructed gate deny without parking writes')
    event('sensor', bay='P03', occupied=True, sequence=10)
    event('sensor', bay='P03', occupied=False, sequence=9)
    state = get()
    bay = next(item for item in state['bays'] if item['label'] == 'P03')
    check(bay['mismatch'] and bay['sensor']['occupied'], 'Sensor ordering or reconciliation failed')
    check(case.scalar('SELECT count(*) FROM parking_sessions') == 1, 'Sensor fabricated a session')
    checks.append('Out-of-order sensors ignored; physical mismatch visible; sessions unchanged')
    departure = str(uuid.uuid4())
    check(event('depart', departure, bay='P01')[0] == 200, 'Departure failed')
    check(event('depart', departure, bay='P01')[1]['replayed'], 'Departure replay failed')
    check(case.scalar('SELECT count(*) FROM parking_sessions WHERE checked_out_at IS NOT NULL') == 1, 'History was lost')
    check(event('arrive', bay='P02', tag='DEMO-CARD-B')[0] == 201, 'Second driver failed')
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if case.feed(case.driver2, peer=True)[1]['events']:
            break
        time.sleep(.2)
    else:
        raise AssertionError('Peer realtime delivery missing')
    checks.append('Departure/history, second driver and real peer SSE delivery')
    request = urllib.request.Request(base + '/api/events', b'{}', {'Origin': 'http://unrelated.invalid'})
    try:
        urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        check(error.code == 403, 'Cross-origin write was not denied')
        error.close()
    else:
        raise AssertionError('Cross-origin write accepted')
    checks.append('Cross-origin controls denied')
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.tools/browsers')
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 980})
            page.goto(base)
            expect(page.locator('#connection')).to_contain_text('Connected', timeout=20000)
            expect(page.locator('.space')).to_have_count(6)
            page.locator('#tag').select_option(label='UNKNOWN-CARD')
            page.get_by_role('button', name='Scan + confirm arrival', exact=True).click()
            expect(page.locator('#result')).to_contain_text('Unknown RFID', timeout=20000)
            page.get_by_role('button', name='Replay last event', exact=True).click()
            expect(page.locator('#result')).to_contain_text('replayed', timeout=20000)
            page.screenshot(path=str(folder / 'desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            check(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow')
            page.screenshot(path=str(folder / 'mobile.png'), full_page=True)
        finally:
            browser.close()
    checks.append('Real Chromium controls, replay, six bays and mobile overflow check')
    (folder / 'verification.json').write_text(json.dumps({'passed': True, 'checks': checks,
        'realBackend': True, 'physicalHardwareTested': False}, indent=2) + '\n')
    for item in checks:
        print('PASS:', item, flush=True)
