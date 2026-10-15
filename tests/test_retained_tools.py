"""Safety checks for the local database viewer and private SMTP configuration."""
import sys
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'.tools/test-python'))
import view_database
from configure_smtp import gmail_settings
from retained_test_lock import retained_test_lock


class LocalTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=view_database.ThreadingHTTPServer(('127.0.0.1',0),view_database.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def test_dns_rebinding_host_is_denied(self):
        request=urllib.request.Request(self.url+'/api/catalog',headers={'Host':'attacker.example'})
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request)
        self.assertEqual(raised.exception.code,403); raised.exception.close()

    def test_cross_site_reads_are_denied(self):
        request=urllib.request.Request(self.url+'/api/catalog',headers={'Sec-Fetch-Site':'cross-site'})
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request)
        self.assertEqual(raised.exception.code,403); raised.exception.close()

    def test_viewer_has_no_write_route(self):
        request=urllib.request.Request(self.url+'/api/rows',data=b'{}',method='POST')
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request)
        self.assertEqual(raised.exception.code,501); raised.exception.close()

    def test_invalid_table_cannot_reach_postgres(self):
        with patch.object(view_database,'connection') as connection:
            with self.assertRaises(ValueError):
                view_database.rows('tests','public','users; DROP TABLE users',0)
            connection.assert_not_called()

    def test_database_rejects_writes_from_viewer_connection(self):
        # Actual PostgreSQL check. A failed write never commits a fixture.
        with view_database.connection('tests') as connection:
            with self.assertRaises(view_database.psycopg.errors.ReadOnlySqlTransaction):
                connection.execute('CREATE TABLE viewer_should_never_exist(id integer)')

    def test_smtp_sender_header_injection_is_rejected(self):
        with self.assertRaises(RuntimeError):
            gmail_settings('sender@gmail.com\r\nBcc:other@example.test','abcdefghijklmnop')

    def test_normal_account_password_is_not_accepted_as_app_password(self):
        with self.assertRaises(RuntimeError):
            gmail_settings('sender@gmail.com','my ordinary password 123')

    def test_concurrent_test_runs_are_denied(self):
        with retained_test_lock():
            with self.assertRaisesRegex(RuntimeError,'already running'):
                with retained_test_lock():
                    self.fail('Concurrent suite lock was accepted')


if __name__=='__main__':
    unittest.main()
