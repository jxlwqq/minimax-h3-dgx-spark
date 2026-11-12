import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('models', ROOT / 'docker/download_models.py')
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)
DATA = b'model-weights\x00' * 300
ENTRY = {'path': 'vae/test.safetensors', 'group': 'fl2va', 'size': len(DATA),
         'sha256': hashlib.sha256(DATA).hexdigest()}


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / 'test.safetensors'
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                owner.requests.append(self.headers.get('Range'))
                offset = int(self.headers.get('Range', 'bytes=0-')[6:].split('-')[0])
                mode = self.path.strip('/')
                if mode == 'ignore':
                    offset = 0
                body = (b'x' * len(DATA) if mode == 'corrupt' else DATA)[offset:]
                code = 206 if offset else 200
                self.send_response(code)
                if code == 206:
                    start = offset + 1 if mode == 'bad-range' else offset
                    self.send_header('Content-Range', f'bytes {start}-{len(DATA)-1}/{len(DATA)}')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if mode == 'interrupt' and len(owner.requests) == 1:
                    body = body[:1000]
                self.wfile.write(body)
                self.close_connection = True

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.addCleanup(patch.stopall)
        patch.object(models.time, 'sleep').start()
        patch('sys.stdout', new=io.StringIO()).start()
        patch('sys.stderr', new=io.StringIO()).start()

    def download(self, mode='normal'):
        models.download_file(self.url + '/' + mode, self.destination, ENTRY)

    def test_full_download(self):
        self.download()
        self.assertEqual(self.destination.read_bytes(), DATA)
        self.assertFalse(self.destination.with_suffix('.safetensors.part').exists())

    def test_resumes_partial_file(self):
        self.destination.with_suffix('.safetensors.part').write_bytes(DATA[:123])
        self.download()
        self.assertEqual(self.requests, ['bytes=123-'])
        self.assertEqual(self.destination.read_bytes(), DATA)

    def test_restarts_if_server_ignores_range(self):
        self.destination.with_suffix('.safetensors.part').write_bytes(DATA[:123])
        self.download('ignore')
        self.assertEqual(self.destination.read_bytes(), DATA)

    def test_interrupted_transfer_resumes(self):
        self.download('interrupt')
        self.assertEqual(self.requests, [None, 'bytes=1000-'])
        self.assertEqual(self.destination.read_bytes(), DATA)

    def test_corrupt_download_does_not_replace_installed_file(self):
        self.destination.write_bytes(b'existing-file')
        with self.assertRaises(ValueError):
            self.download('corrupt')
        self.assertEqual(self.destination.read_bytes(), b'existing-file')
        self.assertEqual(len(self.requests), 3)

    def test_rejects_invalid_content_range(self):
        partial = self.destination.with_suffix('.safetensors.part')
        partial.write_bytes(DATA[:123])
        with self.assertRaisesRegex(ValueError, 'Content-Range'):
            self.download('bad-range')
        self.assertEqual(partial.read_bytes(), DATA[:123])
        self.assertFalse(self.destination.exists())

    def test_offline_validation_detects_same_size_corruption(self):
        self.destination.write_bytes(b'x' * len(DATA))
        self.assertFalse(models.valid_file(self.destination, ENTRY))
        self.destination.write_bytes(DATA)
        self.assertTrue(models.valid_file(self.destination, ENTRY))

    def test_existing_valid_model_needs_no_network(self):
        manifest = Path(self.temp.name) / 'manifest.json'
        manifest.write_text(json.dumps({'files': [ENTRY]}))
        installed = Path(self.temp.name) / ENTRY['path']
        installed.parent.mkdir()
        installed.write_bytes(DATA)
        with patch.object(models, 'MANIFEST', manifest), patch.object(models, 'urlopen', side_effect=AssertionError('network used')), patch('sys.argv', ['models', '--model-root', self.temp.name]):
            self.assertEqual(models.main(), 0)

    def test_verify_is_offline_and_reports_missing_or_corrupt_models(self):
        manifest = Path(self.temp.name) / 'manifest.json'
        manifest.write_text(json.dumps({'files': [ENTRY]}))
        with patch.object(models, 'MANIFEST', manifest), patch.object(models, 'urlopen', side_effect=AssertionError('network used')), patch('sys.argv', ['models', '--verify', '--model-root', self.temp.name]):
            self.assertEqual(models.main(), 1)


if __name__ == '__main__':
    unittest.main()
