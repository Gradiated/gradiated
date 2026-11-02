import concurrent.futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request


def unused_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class Admission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec('smg') is None:
            if os.environ.get('GRADIATED_REQUIRE_SGLANG') == '1':
                raise RuntimeError('Compiled official SMG package required')
            raise unittest.SkipTest('Run native admission checks with pinned SMG installed')

    def exercise(self, queue_timeout, body_bytes=0, through_proxy=False, upload_delay=0):
        if through_proxy and shutil.which('nginx') is None:
            if os.environ.get('GRADIATED_REQUIRE_SGLANG') == '1':
                raise RuntimeError('NGINX required for native rejection transport checks')
            self.skipTest('NGINX required for native rejection transport checks')
        total = 32 if through_proxy and queue_timeout == 60 and not upload_delay else 19
        rejected = total - 18

        release, sixteen = threading.Event(), threading.Event()
        seen, lock = [], threading.Lock()
        expected = b'data: {"choices":[{"index":0,"delta":{"content":"marker"},"finish_reason":null}]}\n\n'
        ending = b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        class Worker(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def send_json(self, value):
                body = json.dumps(value).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
            def do_GET(self):
                value = {'data': [{'id': 'synthetic'}]} if self.path == '/v1/models' else {
                    'model_path': 'synthetic', 'tokenizer_path': 'synthetic', 'served_model_name': 'synthetic',
                    'is_generation': True, 'is_embedding': False, 'context_length': 10000,
                    'dtype': 'bfloat16', 'model_type': 'synthetic', 'architectures': ['Synthetic'],
                    'max_total_num_tokens': 10000, 'tp_size': 1, 'dp_size': 1}
                self.send_json(value)
            def do_POST(self):
                if self.path.startswith('/health'):
                    return self.send_json({'status': 'ok'})
                if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
                    chunks = []
                    while True:
                        length = int(self.rfile.readline().split(b';', 1)[0], 16)
                        if not length:
                            self.rfile.readline(); break
                        chunks.append(self.rfile.read(length)); self.rfile.read(2)
                    body = b''.join(chunks)
                else:
                    body = self.rfile.read(int(self.headers['Content-Length']))
                payload = json.loads(body)
                with lock:
                    seen.append(payload)
                    if len(seen) == 16:
                        sixteen.set()
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                self.wfile.write(expected); self.wfile.flush()
                release.wait(30)
                self.wfile.write(ending); self.wfile.flush()
        backend = ThreadingHTTPServer(('127.0.0.1', 0), Worker)
        backend.daemon_threads = True
        thread = threading.Thread(target=backend.serve_forever, daemon=True)
        thread.start()
        front, metrics = unused_port(), unused_port()
        while metrics == front:
            metrics = unused_port()
        command = [sys.executable, '-m', 'smg.launch_router', '--worker-urls',
                   f'http://127.0.0.1:{backend.server_port}', '--policy', 'round_robin',
                   '--host', '127.0.0.1', '--port', str(front), '--prometheus-host', '127.0.0.1',
                   '--prometheus-port', str(metrics), '--max-concurrent-requests', '16', '--queue-size', '2',
                   '--queue-timeout-secs', str(queue_timeout), '--rate-limit-tokens-per-second', '0',
                   '--request-timeout-secs', '30', '--worker-startup-timeout-secs', '15', '--disable-retries']
        environment = {**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'NVIDIA_VISIBLE_DEVICES': '',
                       'OMP_NUM_THREADS': '4', 'HF_HUB_OFFLINE': '1', 'HF_ENDPOINT': 'http://127.0.0.1:1'}
        def request(index):
            body = json.dumps({'model': 'synthetic', 'messages': [{'role': 'user', 'content': 'marker' + 'x' * body_bytes}],
                               'stream': True, 'max_tokens': 1, 'cache_salt': f'synthetic-{index}'}).encode()
            headers = {'Content-Type': 'application/json'}
            if upload_delay and index >= 18:
                payload = body
                def slow_upload():
                    chunk = (len(payload) + 15) // 16
                    for offset in range(0, len(payload), chunk):
                        if offset:
                            time.sleep(upload_delay)
                        yield payload[offset:offset + chunk]
                headers['Content-Length'] = str(len(payload))
                body = slow_upload()
            req = urllib.request.Request(f'http://127.0.0.1:{client_port}/v1/chat/completions', data=body,
                                         headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=25) as response:
                    return response.status, response.read(), response.headers.get('Retry-After')
            except urllib.error.HTTPError as error:
                return error.code, error.read(), error.headers.get('Retry-After')
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryFile() as log:
            root = Path(directory)
            client_port = unused_port() if through_proxy else front
            proxy = None
            if through_proxy:
                for name in ('body', 'temp'):
                    (root / name).mkdir()
                user = 'user root;' if os.geteuid() == 0 else ''
                configuration = (f'{user} worker_processes 1; pid {root}/nginx.pid; '
                                 f'error_log {root}/nginx.log warn; events {{ worker_connections 1024; }} '
                                 f'http {{ access_log off; client_max_body_size 32M; '
                                 f'client_body_temp_path {root}/body; proxy_temp_path {root}/temp; '
                                 f'server {{ listen 127.0.0.1:{client_port}; location / {{ '
                                 f'proxy_pass http://127.0.0.1:{front}; proxy_http_version 1.1; '
                                 'proxy_set_header Connection ""; proxy_buffering off; '
                                 'proxy_request_buffering off; } } }')
                config = root / 'nginx.conf'
                config.write_text(configuration)
                subprocess.run(['nginx', '-t', '-q', '-c', str(config)], check=True,
                               stdout=log, stderr=subprocess.STDOUT)
                proxy = subprocess.Popen(['nginx', '-c', str(config), '-g', 'daemon off;'],
                                         stdout=log, stderr=subprocess.STDOUT)
            router = subprocess.Popen(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=total)
            jobs = []
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if router.poll() is not None:
                        log.seek(0)
                        self.fail('Native router startup failed: ' + log.read()[-3000:].decode())
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{front}/readiness', timeout=.5) as response:
                            if response.status == 200: break
                    except OSError: pass
                    time.sleep(.1)
                else: self.fail('Native router readiness deadline')
                jobs = [pool.submit(request, index) for index in range(16)]
                if not sixteen.wait(8):
                    early = [(job.result()[0] if job.done() else 'pending') for job in jobs]
                    log.seek(0)
                    self.fail(f'All16 frontend permits must reach backend; seen={len(seen)}, outcomes={early}; router=' + log.read()[-5000:].decode())
                jobs.extend(pool.submit(request, index) for index in range(16, total))
                until = time.monotonic() + (8 if upload_delay else 2 if queue_timeout == 1 or through_proxy else .5)
                while time.monotonic() < until: time.sleep(.05)
                with lock: self.assertEqual(len(seen), 16)
                early = [job.result() for job in jobs if job.done()]
                self.assertEqual(sorted(status for status, _, _ in early), [429, 503, 503] if queue_timeout == 1 else [429] * rejected)
                self.assertTrue(all(retry == '2' for _, _, retry in early))
            finally:
                release.set()
                pool.shutdown(wait=True)
                try:
                    results = [job.result() for job in jobs]
                finally:
                    router.terminate()
                    try: router.wait(timeout=5)
                    except subprocess.TimeoutExpired: router.kill(); router.wait(timeout=5)
                    backend.shutdown(); backend.server_close(); thread.join(timeout=2)
                    if proxy is not None:
                        proxy.terminate()
                        try: proxy.wait(timeout=5)
                        except subprocess.TimeoutExpired: proxy.kill(); proxy.wait(timeout=5)
            self.assertEqual(sorted(status for status, _, _ in results), [200] * 16 + [429, 503, 503] if queue_timeout == 1 else [200] * 18 + [429] * rejected)
            self.assertTrue(all(body == expected + ending for status, body, _ in results if status == 200))
            for status, body, retry in results:
                if status != 200:
                    self.assertEqual(retry, '2')
                    self.assertEqual(json.loads(body)['error']['code'],
                                     'admission_queue_full' if status == 429 else 'admission_queue_timeout')

    def test_compiled_front_limits16_plus2_and_preserves_stream(self):
        self.exercise(60)

    def test_compiled_front_queue_age_is503_before_stream(self):
        self.exercise(1)

    def test_proxy_preserves_native_queue_full_errors_for_large_uploads(self):
        for size in (26200, 1024 * 1024, 8 * 1024 * 1024):
            with self.subTest(body_bytes=size):
                self.exercise(60, body_bytes=size, through_proxy=True)

    def test_proxy_preserves_native_rejection_during_slow_maximum_upload(self):
        started = time.monotonic()
        self.exercise(60, body_bytes=31_999_000, through_proxy=True, upload_delay=.4)
        self.assertGreaterEqual(time.monotonic() - started, 6)

    def test_proxy_preserves_native_queue_expiry_errors(self):
        self.exercise(1, body_bytes=1024 * 1024, through_proxy=True)


if __name__ == '__main__':
    unittest.main()
