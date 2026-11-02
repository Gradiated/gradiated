import concurrent.futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import socket
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

    def exercise(self, queue_timeout):
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
                release.wait(15)
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
            body = json.dumps({'model': 'synthetic', 'messages': [{'role': 'user', 'content': 'marker'}],
                               'stream': True, 'max_tokens': 1, 'cache_salt': f'synthetic-{index}'}).encode()
            req = urllib.request.Request(f'http://127.0.0.1:{front}/v1/chat/completions', data=body,
                                         headers={'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=15) as response:
                    return response.status, response.read(), response.headers.get('Retry-After')
            except urllib.error.HTTPError as error:
                return error.code, error.read(), error.headers.get('Retry-After')
        with tempfile.TemporaryFile() as log:
            router = subprocess.Popen(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=19)
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
                jobs.extend(pool.submit(request, index) for index in range(16, 19))
                until = time.monotonic() + (2 if queue_timeout == 1 else .5)
                while time.monotonic() < until: time.sleep(.05)
                with lock: self.assertEqual(len(seen), 16)
                early = [job.result() for job in jobs if job.done()]
                self.assertEqual(sorted(status for status, _, _ in early), [429, 503, 503] if queue_timeout == 1 else [429])
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
            self.assertEqual(sorted(status for status, _, _ in results), [200] * 16 + [429, 503, 503] if queue_timeout == 1 else [200] * 18 + [429])
            self.assertTrue(all(body == expected + ending for status, body, _ in results if status == 200))

    def test_compiled_front_limits16_plus2_and_preserves_stream(self):
        self.exercise(60)

    def test_compiled_front_queue_age_is503_before_stream(self):
        self.exercise(1)


if __name__ == '__main__':
    unittest.main()
