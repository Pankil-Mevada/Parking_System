"""Local synthetic-device adapter. Parking truth stays in the authenticated API."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import uuid


class Simulator:
    def __init__(self, path, call, location, bays, tags):
        self.call, self.location, self.bays, self.tags = call, location, bays, tags
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, hash TEXT NOT NULL, context TEXT NOT NULL, result TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
        self.db.execute('INSERT OR IGNORE INTO state VALUES(1,?)', (json.dumps({'gate': 'normal', 'sensors': {}}),))
        self.db.commit()

    def state(self):
        return json.loads(self.db.execute('SELECT value FROM state WHERE id=1').fetchone()[0])

    def save(self, state):
        self.db.execute('UPDATE state SET value=? WHERE id=1', (json.dumps(state),))
        self.db.commit()

    def snapshot(self):
        with self.lock:
            code, body = self.call(f'/api/staff/locations/{self.location}/spaces')
            if code != 200:
                raise RuntimeError('Isolated API unavailable or permission expired; no live snapshot.')
            state = self.state()
            by_id = {row['id']: row for row in body['spaces']}
            bays = []
            for label, identifier in self.bays.items():
                row = by_id[identifier]
                sensor = state['sensors'].get(label)
                occupied = bool(row['session_id'])
                bays.append({'label': label, 'occupied': occupied, 'sensor': sensor,
                             'mismatch': sensor is not None and sensor['occupied'] != occupied,
                             'plate': row['registration_snapshot']})
            events = [json.loads(row[0]) for row in self.db.execute(
                'SELECT result FROM events WHERE result IS NOT NULL ORDER BY rowid DESC LIMIT 15')]
            return {'simulation': True, 'gate': state['gate'], 'bays': bays,
                    'tags': list(self.tags), 'events': events}

    def event(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'eventId', 'action', 'bay', 'tag', 'occupied', 'sequence', 'mode'}:
            raise ValueError('Invalid event fields.')
        if not isinstance(payload.get('eventId'), str):
            raise ValueError('Event ID must be a UUID string.')
        identifier = str(uuid.UUID(payload['eventId']))
        action = payload.get('action')
        if action not in ('arrive', 'depart', 'sensor', 'gate'):
            raise ValueError('Unknown simulation action.')
        if action != 'gate' and payload.get('bay') not in self.bays:
            raise ValueError('Select a configured simulation bay.')
        if action == 'arrive' and not isinstance(payload.get('tag'), str):
            raise ValueError('A card identifier is required.')
        if action == 'sensor' and (type(payload.get('occupied')) is not bool or
                                   type(payload.get('sequence')) is not int or not 1 <= payload['sequence'] <= 1000000000):
            raise ValueError('Sensor requires occupied boolean and positive sequence.')
        if action == 'gate' and payload.get('mode') not in ('normal', 'offline', 'obstructed'):
            raise ValueError('Invalid gate mode.')
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.lock:
            row = self.db.execute('SELECT hash,context,result FROM events WHERE id=?', (identifier,)).fetchone()
            if row and row[0] != digest:
                return 409, {'message': 'Event ID reused with different content.', 'eventId': identifier}
            if row and row[2]:
                result = json.loads(row[2])
                return result['status'], dict(result, replayed=True)
            context = json.loads(row[1]) if row else {}
            if not row:
                self.db.execute('INSERT INTO events VALUES(?,?,?,NULL)', (identifier, digest, '{}'))
                self.db.commit()
            state = self.state()
            code, message = 200, ''
            bay = payload.get('bay')
            if action == 'gate':
                state['gate'] = payload['mode']
                message = 'Simulated gate mode: ' + state['gate']
            elif action == 'sensor':
                previous = state['sensors'].get(bay, {}).get('sequence', 0)
                if payload['sequence'] <= previous:
                    message = 'Older sensor reading ignored.'
                else:
                    state['sensors'][bay] = {'occupied': payload['occupied'], 'sequence': payload['sequence']}
                    message = 'Sensor recorded; parking session unchanged.'
            elif action == 'arrive' and payload['tag'] not in self.tags:
                code, message = 403, 'Unknown RFID card denied.'
            elif state['gate'] != 'normal' and not context.get('passageConfirmed'):
                code, message = 409, 'Gate ' + state['gate'] + '; parking action blocked.'
            else:
                context['passageConfirmed'] = True
                self.db.execute('UPDATE events SET context=? WHERE id=?', (json.dumps(context), identifier))
                self.db.commit()
                if action == 'arrive':
                    code, body = self.call('/api/staff/check-ins', 'POST', {
                        'vehicleId': self.tags[payload['tag']], 'spaceId': self.bays[bay]}, identifier)
                else:
                    if 'session' not in context:
                        status, body = self.call(f'/api/staff/locations/{self.location}/spaces')
                        if status != 200:
                            return 503, {'message': 'API unavailable. Retry this event ID.', 'eventId': identifier}
                        context['session'] = next((item['session_id'] for item in body['spaces']
                                                   if item['id'] == self.bays[bay]), None)
                        self.db.execute('UPDATE events SET context=? WHERE id=?', (json.dumps(context), identifier))
                        self.db.commit()
                    if not context['session']:
                        code, body = 409, {'error': 'No active session in this bay.'}
                    else:
                        code, body = self.call('/api/staff/sessions/' + context['session'] + '/check-out', 'POST', {}, identifier)
                if code >= 500:
                    return 503, {'message': 'API result uncertain. Retry this event ID.', 'eventId': identifier}
                if code in (200, 201):
                    previous = state['sensors'].get(bay, {}).get('sequence', 0)
                    state['sensors'][bay] = {'occupied': action == 'arrive', 'sequence': previous + 1}
                    message = ('Arrival' if action == 'arrive' else 'Departure') + ' confirmed by real API; simulated gate passage acknowledged.'
                else:
                    # No response bodies/tokens are copied into simulator history.
                    message = 'Parking API rejected action: ' + str(body.get('error', code))
            result = {'eventId': identifier, 'action': action, 'bay': bay, 'status': code,
                      'message': message, 'replayed': False}
            # Commit local sensor state and completion together. A crash before
            # completion leaves a pending event that retries the API's same key.
            self.db.execute('UPDATE state SET value=? WHERE id=1', (json.dumps(state),))
            self.db.execute('UPDATE events SET result=? WHERE id=?', (json.dumps(result), identifier))
            self.db.commit()
            return code, result


def server(simulator, port=8766):
    nonce = secrets.token_urlsafe(32)
    folder = Path(__file__).resolve().parent / 'simulator_ui'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def send(self, code, body, content_type='application/json'):
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.valid_host() or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.send(403, {'message': 'Local simulator access only.'})
            if self.path == '/api/state':
                try:
                    return self.send(200, dict(simulator.snapshot(), key=nonce))
                except (RuntimeError, OSError, KeyError):
                    return self.send(503, {'message': 'Isolated API unavailable. Data is stale.'})
            assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
            if self.path not in assets:
                return self.send(404, {'message': 'Not found.'})
            filename, mime = assets[self.path]
            self.send(200, (folder / filename).read_text(encoding='utf-8'), mime)

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if not self.valid_host() or self.headers.get('Origin') != origin or self.headers.get('X-Simulator-Key') != nonce:
                return self.send(403, {'message': 'Same-origin simulator controls required.'})
            if self.path != '/api/events':
                return self.send(404, {'message': 'Not found.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError('Event body must be 1–4096 bytes.')
                payload = json.loads(self.rfile.read(length))
                code, body = simulator.event(payload)
                self.send(code, body)
            except (ValueError, TypeError):
                self.send(400, {'message': 'Invalid event. Use the provided controls.'})
            except (OSError, RuntimeError, KeyError):
                self.send(503, {'message': 'API result uncertain. Retry the same event.'})
    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    httpd.daemon_threads = True
    return httpd
