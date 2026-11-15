import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from eu_law_cite import Client, CitationError, Identifier, bibtex
from eu_law_cite.core import fetch, validate_url
from eu_law_cite.markdown import check

FIXTURES = Path(__file__).parent / 'fixtures'


class CitationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / 'cache'
        self.network = patch('socket.socket', side_effect=AssertionError('Tests must not use network'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def client(self, fixture='celex', **kwargs):
        return Client(self.cache, transport=lambda url: (FIXTURES / (fixture + '.json')).read_bytes(), **kwargs)

    def test_recorded_identifiers_and_exports(self):
        for fixture, value in [('celex', 'CELEX:32016R0679'), ('ecli', 'ECLI:EU:C:2020:559'), ('eli', 'https://data.europa.eu/eli/reg/2016/679/oj')]:
            with self.subTest(fixture=fixture):
                item = self.client(fixture).resolve(value)
                self.assertTrue(item['title'])
                self.assertEqual(item['language'], 'en')
                self.assertTrue(item['URL'].startswith('https://'))
                self.assertIn('year = {20', bibtex(item))
                self.assertEqual(item['issued']['date-parts'][0], [2020, 7, 16] if fixture == 'ecli' else [2016, 4, 27])
                self.assertEqual(item['type'], 'legal_case' if fixture == 'ecli' else 'legislation')

    def test_offline_cache_and_miss(self):
        expected = self.client().resolve('32016R0679')
        client = Client(self.cache, offline=True, transport=lambda _: self.fail('Network called'))
        self.assertEqual(client.resolve('32016R0679'), expected)
        with self.assertRaises(CitationError) as error:
            client.resolve('32016R0679', 'it')
        self.assertEqual(error.exception.kind, 'unavailable')

    def test_expired_and_corrupt_cache(self):
        self.client().resolve('32016R0679')
        path = next(self.cache.glob('*.json'))
        path.write_text('invalid')
        self.assertIn('title', self.client().resolve('32016R0679'))
        with self.assertRaises(CitationError):
            Client(self.cache, ttl=-1, transport=lambda _: b'not JSON').resolve('32016R0679')

    def test_missing_not_confused_with_service_failure(self):
        with self.assertRaises(CitationError) as error:
            self.client('missing').resolve('39999R9999')
        self.assertEqual(error.exception.kind, 'not_found')
        with self.assertRaises(CitationError) as error:
            Client(self.cache, transport=lambda _: b'<html>challenge</html>').resolve('32016R0679')
        self.assertEqual(error.exception.kind, 'unavailable')

    def test_missing_language_not_nonexistent(self):
        data = {'results': {'bindings': [{'celex': {'value': '32016R0679'}}]}}
        with self.assertRaises(CitationError) as error:
            Client(self.cache, transport=lambda _: json.dumps(data)).resolve('32016R0679')
        self.assertEqual(error.exception.kind, 'unavailable')

    def test_identifiers_reject_injection_and_unsupported(self):
        for value in ['CELEX:bad', 'ECLI:EU:C:20:1', '32016R0679" } UNION {', 'https://evil.test/eli/reg/2016/679/oj']:
            with self.subTest(value=value), self.assertRaises(CitationError):
                Identifier(value)
        self.assertEqual(Identifier('celex:32016r0679').value, '32016R0679')
        self.assertEqual(Identifier('12016P/TXT').kind, 'celex')
        with self.assertRaises(CitationError) as error:
            Identifier('ECLI:IT:CASS:2020:123')
        self.assertEqual(error.exception.kind, 'unsupported')

    def test_bibtex_escaping(self):
        item = self.client().resolve('32016R0679')
        item['title'] = r'A & B {x} 10% _ # $ \input'
        output = bibtex(item)
        self.assertIn(r'\&', output)
        self.assertIn(r'\{x\}', output)
        self.assertIn(r'\textbackslash{}input', output)

    def test_markdown_reference_links_and_invalid_ids(self):
        path = Path(self.temp.name) / 'note.md'
        path.write_text('CELEX:broken\n\n[ref][target]\n\n[target]: missing.md\n\n```\nCELEX:ignore\n```\n')
        issues = check(path, self.client())
        self.assertEqual({x['kind'] for x in issues}, {'malformed', 'broken_link'})
        self.assertFalse(any(x['value'] == 'CELEX:ignore' for x in issues))

    def test_markdown_http_errors_and_offline(self):
        path = Path(self.temp.name) / 'note.md'
        path.write_text('[broken](https://example.org/gone)')
        def missing(_):
            raise CitationError('not_found', 'HTTP 404')
        self.assertEqual(check(path, Client(self.cache, transport=missing))[0]['kind'], 'broken_link')
        self.assertEqual(check(path, Client(self.cache, offline=True))[0]['kind'], 'unchecked_link')

    def test_url_safety_and_transport_errors(self):
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]):
            with self.assertRaises(CitationError) as error:
                validate_url('https://example.org')
            self.assertEqual(error.exception.kind, 'unsafe_link')
        for exception, kind in [(HTTPError('https://example.org', 404, 'gone', {}, None), 'not_found'), (HTTPError('https://example.org', 429, 'slow down', {}, None), 'unavailable'), (URLError('timeout'), 'unavailable')]:
            with patch('eu_law_cite.core.validate_url'), patch('eu_law_cite.core.build_opener') as opener:
                opener.return_value.open.side_effect = exception
                with self.assertRaises(CitationError) as error:
                    fetch('https://example.org')
                self.assertEqual(error.exception.kind, kind)

    def test_eli_paths_and_celex_suffix(self):
        self.assertEqual(Identifier('62018CJ0311_RES').kind, 'celex')
        self.assertEqual(Identifier('https://eur-lex.europa.eu/eli/reg/2016/679/oj/pol/pdf').value, 'http://data.europa.eu/eli/reg/2016/679/oj')
        for value in ['https://data.europa.eu/eli/reg/banana/oj', 'https://data.europa.eu/eli/../reg/2016/679/oj']:
            with self.subTest(value=value), self.assertRaises(CitationError):
                Identifier(value)

    def test_cli_offline_and_exit_status(self):
        import subprocess
        import sys
        self.client().resolve('32016R0679')
        prefix = [sys.executable, '-m', 'eu_law_cite', '--cache', str(self.cache), '--offline']
        result = subprocess.run([*prefix, 'cite', '32016R0679'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)[0]['language'], 'en')
        result = subprocess.run([*prefix, 'cite', 'CELEX:broken'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        result = subprocess.run([*prefix, 'cite', '39999R9999'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
