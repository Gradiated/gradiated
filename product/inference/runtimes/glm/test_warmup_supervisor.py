import http.server
import importlib.util
import json
import signal
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("warmup", Path(__file__).with_name("warmup-supervisor.py"))
warmup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(warmup)


class Runtime(http.server.BaseHTTPRequestHandler):
    body = b'data: {"choices":[{"delta":{"content":"ok"}}],"usage":{"prompt_tokens":100,"prompt_tokens_details":{"cached_tokens":0}}}\n\ndata: [DONE]\n\n'

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"test_metric 1\n")

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *_):
        pass


class WarmupTests(unittest.TestCase):
    def setUp(self):
        self.runtime = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Runtime)
        threading.Thread(target=self.runtime.serve_forever, daemon=True).start()
        self.supervisor = warmup.Supervisor([], f"http://127.0.0.1:{self.runtime.server_port}")
        self.supervisor.child = Mock()
        self.supervisor.child.poll.return_value = None

    def tearDown(self):
        self.runtime.shutdown()
        self.runtime.server_close()

    def test_gate_waits_for_all_probes_and_checks_child_health(self):
        calls = []
        def probe(*args):
            self.assertFalse(self.supervisor.ready())
            calls.append(args)
            return {"prompt_tokens": args[0], "elapsed_seconds": 0.001}
        self.supervisor.probe = probe
        self.assertFalse(self.supervisor.ready())
        self.supervisor.warmup()
        self.assertEqual(len(calls), 77)
        self.assertTrue(self.supervisor.ready())
        self.supervisor.child.poll.return_value = 1
        self.assertFalse(self.supervisor.ready())
        fresh = warmup.Supervisor([])
        fresh.child = Mock()
        fresh.child.poll.return_value = None
        self.assertFalse(fresh.ready())

    def test_all_cold_groups_precede_qualification(self):
        calls = []
        self.supervisor.probe_group = lambda *args: calls.append(args)
        self.supervisor.warmup()
        self.assertEqual([call[0] for call in calls],
                         ["cold_prompt"] * 5 + ["cold_concurrency"] * 5 +
                         ["qualify_mixed_prompt"] * 5 + ["qualify_concurrency"] * 5)
        for phase in ("cold_concurrency", "qualify_concurrency"):
            self.assertEqual([len(shapes) for name, shapes, _ in calls if name == phase],
                             [1, 2, 4, 8, 16])
        self.assertTrue(all(timeout == 25 for name, _, timeout in calls if name.startswith("qualify")))

    def test_synchronized_concurrency_group_completes(self):
        simultaneous = threading.Barrier(16)
        def probe(*_):
            simultaneous.wait(timeout=3)
            return {"prompt_tokens": 64, "elapsed_seconds": 0.001}
        self.supervisor.probe = probe
        self.supervisor.probe_group("test_concurrency", [32] * 16, 25)
        self.assertFalse(self.supervisor.qualified.is_set())

    def test_health_failure_after_qualification_closes_gate(self):
        self.supervisor.qualified.set()
        self.assertTrue(self.supervisor.ready())
        self.supervisor.runtime_url = "http://127.0.0.1:1"
        self.assertFalse(self.supervisor.ready())

    def test_probe_requires_done_output_and_rejects_sse_errors(self):
        self.supervisor.probe(32, 2)
        for body in (b'data: {"error":{"message":"failed"}}\n\ndata: [DONE]\n\n',
                     b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n',
                     b'data: [DONE]\n\n'):
            with patch.object(Runtime, "body", body), self.assertRaises(RuntimeError):
                self.supervisor.probe(32, 2)

    def test_probe_rejects_cached_or_missing_usage(self):
        valid = Runtime.body
        for body in (valid.replace(b'"cached_tokens":0', b'"cached_tokens":32'),
                     valid.replace(b'"usage":', b'"ignored_usage":')):
            with patch.object(Runtime, "body", body), self.assertRaises(RuntimeError):
                self.supervisor.probe(32, 2)

    def test_probe_requires_explicit_integer_zero_cache_count(self):
        for details in (None, {}, [], 0, {"cached_tokens": None},
                        {"cached_tokens": False}, {"cached_tokens": True},
                        {"cached_tokens": "0"}, {"cached_tokens": 0.0},
                        {"cached_tokens": -1}, {"cached_tokens": 1}):
            with self.subTest(details=details):
                event = {"choices": [{"delta": {"content": "ok"}}],
                         "usage": {"prompt_tokens": 100, "prompt_tokens_details": details}}
                body = b"data: " + json.dumps(event).encode() + b"\n\ndata: [DONE]\n\n"
                with patch.object(Runtime, "body", body), self.assertRaisesRegex(RuntimeError, "explicit zero"):
                    self.supervisor.probe(32, 2)
        missing = Runtime.body.replace(b',"prompt_tokens_details":{"cached_tokens":0}', b'')
        with patch.object(Runtime, "body", missing), self.assertRaisesRegex(RuntimeError, "explicit zero"):
            self.supervisor.probe(32, 2)
        self.assertEqual(self.supervisor.probe(32, 2)["prompt_tokens"], 100)

    def test_absolute_startup_deadline_stops_child(self):
        supervisor = warmup.Supervisor([sys.executable, "-c", "import time;time.sleep(60)"], timeout=0.1)
        supervisor.warmup = lambda: supervisor.stopping.wait(60)
        old_term, old_int = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
        try:
            self.assertEqual(supervisor.run(port=0), 1)
            self.assertIsNotNone(supervisor.child.poll())
        finally:
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGINT, old_int)

    def test_failure_never_opens_gate(self):
        self.supervisor.probe = Mock(side_effect=RuntimeError("synthetic failure"))
        with self.assertRaises(RuntimeError):
            self.supervisor.warmup()
        self.assertFalse(self.supervisor.ready())

    def test_health_endpoint_and_metrics_proxy(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), warmup.handler(self.supervisor))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(url + "/health", timeout=2)
            self.assertEqual(error.exception.code, 503)
            with urllib.request.urlopen(url + "/metrics", timeout=2) as response:
                self.assertEqual(response.read(), b"test_metric 1\n")
            self.supervisor.qualified.set()
            with urllib.request.urlopen(url + "/health", timeout=2) as response:
                self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            server.server_close()

    def test_shutdown_forwards_signal_and_closes_gate(self):
        child = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"], start_new_session=True)
        self.supervisor.child = child
        self.supervisor.qualified.set()
        try:
            self.supervisor.stop()
            self.assertEqual(child.wait(timeout=3), -signal.SIGTERM)
            self.assertFalse(self.supervisor.qualified.is_set())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()

    def test_failed_warmup_exits_and_reaps_child(self):
        supervisor = warmup.Supervisor([sys.executable, "-c", "import time;time.sleep(60)"])
        supervisor.warmup = Mock(side_effect=RuntimeError("synthetic failure"))
        old_term, old_int = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
        try:
            self.assertEqual(supervisor.run(port=0), 1)
            self.assertIsNotNone(supervisor.child.poll())
            self.assertFalse(supervisor.qualified.is_set())
        finally:
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGINT, old_int)


if __name__ == "__main__":
    unittest.main()
