import json
from pathlib import Path
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from launch_check import blockers
from load_test import measure
from identity_admin import environment
from parking_tools import ROOT

class OperationsTests(unittest.TestCase):
    def test_missing_acceptance_stays_blocked(self):
        config=json.loads((ROOT/'operations/launch-gates.json').read_text())
        self.assertIn('operatorSignOff',blockers(config))
        self.assertEqual(config['jurisdiction']['country'],'India')

    def test_load_cannot_target_remote_or_unrelated_services(self):
        for target in ('https://example.com','http://127.0.0.1:8180','http://a:b@localhost:8080','http://127.0.0.1:8080/api'):
            with self.subTest(target=target),self.assertRaises(RuntimeError):measure(target,1,1)

    def test_metrics_require_dedicated_credential(self):
        for headers in ({},{'Authorization':'Bearer wrong'}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080/internal/metrics',headers=headers),timeout=5)
            self.assertEqual(error.exception.code,403)
            error.exception.close()

    def test_metrics_and_safe_response_headers(self):
        # Histogram series appear after traffic; make the check independent of
        # whether a user visited the freshly restarted API already.
        with urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=5) as response:self.assertEqual(response.status,200)
        token=environment()['OPS_METRICS_TOKEN']
        request=urllib.request.Request('http://127.0.0.1:8080/internal/metrics',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(request,timeout=5) as response:
            body=response.read().decode()
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertTrue(response.headers['X-Request-ID'])
        self.assertIn('parking_outbox_lag_seconds',body)
        self.assertIn('parking_http_duration_seconds_bucket',body)
        self.assertNotIn(token,body)
        for private in ('email=','registration=','user_id=','session_id='):self.assertNotIn(private,body)

if __name__=='__main__':unittest.main(verbosity=2)
