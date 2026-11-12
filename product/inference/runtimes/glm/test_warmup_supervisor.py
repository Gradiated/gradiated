import http.server
import importlib.util
import json
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

source = Path(__file__).with_name("warmup-supervisor.py")
if not source.exists():
    source = Path(__file__).parent.parent / "warmup-supervisor.py"
spec = importlib.util.spec_from_file_location("warmup", source)
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
        # 6 cold prompts + 34 cold concurrency + 3 cold mixed + 12 mixed prompts;
        # fast cold groups are not rerun at the qualification timeout.
        self.assertEqual(len(calls), 55)
        self.assertTrue(self.supervisor.ready())
        self.supervisor.child.poll.return_value = 1
        self.assertFalse(self.supervisor.ready())
        fresh = warmup.Supervisor([])
        fresh.child = Mock()
        fresh.child.poll.return_value = None
        self.assertFalse(fresh.ready())

    def test_all_cold_groups_precede_qualification(self):
        calls = []
        def group(*args):
            calls.append(args)
            return [{"prompt_tokens": words*2+50, "elapsed_seconds": .001} for words in args[1]]
        self.supervisor.probe_group = group
        self.supervisor.warmup()
        self.assertEqual([call[0] for call in calls],
                         ["cold_prompt"] * 6 + ["cold_concurrency"] * 6 + ["cold_mixed_prefills"] +
                         ["qualify_mixed_prompt"] * 6)
        self.assertEqual([len(shapes) for name, shapes, _ in calls if name == "cold_concurrency"],
                         [1, 2, 3, 4, 8, 16])
        self.assertEqual([shapes for name, shapes, _ in calls if name.endswith('mixed_prefills')],
                         [[8192, 8192, 32]])
        self.assertTrue(all(timeout == 180 for name, _, timeout in calls if name.startswith("cold")))
        self.assertEqual(self.supervisor.mode, "full")
        self.assertTrue(all(timeout == 25 for name, _, timeout in calls if name.startswith("qualify")))

    def test_qualification_respects_admission_caps(self):
        self.supervisor.max_queued_requests = 4
        self.supervisor.max_queued_tokens = 32768
        calls = []
        def group(phase, shapes, timeout):
            calls.append((phase, shapes))
            return [{'prompt_tokens': words*2+50, 'elapsed_seconds': .001} for words in shapes]
        self.supervisor.probe_group = group
        self.supervisor.warmup()
        self.assertTrue(self.supervisor.ready())
        for phase, shapes in calls:
            self.assertLessEqual(len(shapes), 4)
            if len(shapes) > 1:
                self.assertLessEqual(sum(words*2+82 for words in shapes), 32768)
        mixed = [shapes for phase, shapes in calls if phase == 'qualify_mixed_prompt']
        self.assertEqual(mixed[-1], [16384])
        self.assertEqual(mixed[0], [32, 32])

    def test_single_request_policy_still_qualifies_all_cold_shapes(self):
        self.supervisor.max_queued_requests = 1
        calls = []
        self.supervisor.probe = lambda words, *_: calls.append(words) or {'prompt_tokens': words*2+50, 'elapsed_seconds': .001}
        self.supervisor.warmup()
        self.assertTrue(all(words in calls for words in warmup.SHAPES))
        self.assertTrue(self.supervisor.ready())

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


real_inventory = warmup.gpu_inventory
GPUS = [("GPU-a", "NVIDIA B200", "580.1")]


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.records = Path(self.directory.name) / "records"
        inventory = patch.object(warmup, "gpu_inventory", return_value=GPUS)
        inventory.start()
        self.addCleanup(inventory.stop)
        self.slow = {}
        self.failing = set()
        self.calls = []

    def supervisor(self, record_dir=True, identity=True):
        supervisor = warmup.Supervisor([], record_dir=self.records if record_dir else None,
                                       identity={"bundle": "a" * 64, "config": {"front": 1}} if identity else None)
        supervisor.health = lambda: True
        def group(phase, shapes, timeout):
            self.calls.append((phase, len(shapes), timeout))
            if phase in self.failing:
                raise RuntimeError("synthetic failure")
            elapsed = self.slow.get((phase, len(shapes)), .01)
            return [{"prompt_tokens": words * 2 + 50, "elapsed_seconds": elapsed} for words in shapes]
        supervisor.probe_group = group
        return supervisor

    def qualified(self, **options):
        supervisor = self.supervisor(**options)
        supervisor.warmup()
        self.assertTrue(supervisor.qualified.is_set())
        return supervisor

    def record_files(self):
        return sorted(self.records.glob("*.json")) if self.records.exists() else []

    def test_full_pass_writes_record_then_short_pass_uses_it(self):
        first = self.qualified()
        self.assertEqual(first.mode, "full")
        [path] = self.record_files()
        record = json.loads(path.read_text())
        self.assertEqual(path.stem, first.record_key())
        self.assertEqual(record["version"], warmup.RECORD_VERSION)
        self.assertEqual(set(record["prompt_bounds"]), {str(words) for words in warmup.SHAPES})
        self.assertIn("concurrency:16", record["latency"])
        self.assertIn("mixed_prompt:16384", record["latency"])
        self.assertEqual(list(self.records.glob(".*.tmp")), [])
        self.calls.clear()
        second = self.qualified()
        self.assertEqual(second.mode, "short")
        self.assertTrue(self.calls)
        self.assertTrue(all(phase.startswith("qualify") and timeout == 25 for phase, _, timeout in self.calls))
        self.assertEqual(len(self.calls), 6 + 1 + 6)

    def test_short_failure_falls_back_to_full_and_rewrites_record(self):
        self.qualified()
        [path] = self.record_files()
        before = json.loads(path.read_text())["qualified_at"]
        # The full pass reruns no fast concurrency group, so only the short pass fails.
        self.failing = {"qualify_concurrency"}
        supervisor = self.supervisor()
        supervisor.warmup()
        self.assertEqual(supervisor.mode, "short_to_full")
        self.assertIn("cold_prompt", [phase for phase, _, _ in self.calls[-60:]])
        self.assertGreaterEqual(json.loads(path.read_text())["qualified_at"], before)

    def test_short_slowdown_falls_back_to_full(self):
        self.qualified()
        self.slow = {("qualify_mixed_prompt", 2): 5.0}
        supervisor = self.qualified()
        self.assertEqual(supervisor.mode, "short_to_full")
        self.calls.clear()
        # The rewritten record holds the slower latency, so the next start is short again.
        self.assertEqual(self.qualified().mode, "short")

    def test_invalid_records_run_full(self):
        def rewrite(change):
            [path] = self.record_files()
            record = json.loads(path.read_text())
            change(record)
            path.write_text(json.dumps(record))
        self.qualified()
        for name, change in [
                ("expired", lambda record: record.update(qualified_at=record["qualified_at"] - 8 * 24 * 3600)),
                ("future", lambda record: record.update(qualified_at=record["qualified_at"] + 3600)),
                ("wrong key", lambda record: record.update(key="0" * 64)),
                ("version", lambda record: record.update(version=0)),
                ("bounds", lambda record: record["prompt_bounds"].pop("32")),
                ("latency", lambda record: record.update(latency={"concurrency:1": "fast"}))]:
            with self.subTest(name):
                rewrite(change)
                self.assertEqual(self.qualified().mode, "full")
        [path] = self.record_files()
        path.write_text("{not json")
        self.assertEqual(self.qualified().mode, "full")
        self.assertEqual(self.qualified().mode, "short")

    def test_record_missing_a_group_falls_back_to_full(self):
        self.qualified()
        [path] = self.record_files()
        record = json.loads(path.read_text())
        del record["latency"]["concurrency:16"]
        path.write_text(json.dumps(record))
        self.assertEqual(self.qualified().mode, "short_to_full")

    def test_changed_settings_or_gpus_change_the_key(self):
        supervisor = self.supervisor()
        key = supervisor.record_key()
        self.assertRegex(key, "^[0-9a-f]{64}$")
        supervisor.max_queued_requests = 4
        self.assertNotEqual(supervisor.record_key(), key)
        with patch.object(warmup, "gpu_inventory", return_value=[("GPU-b", "NVIDIA B200", "580.1")]):
            self.assertNotEqual(self.supervisor().record_key(), key)

    def test_without_record_dir_or_identity_runs_full_and_records_nothing(self):
        for options in ({"record_dir": False}, {"identity": False}):
            with self.subTest(options):
                self.assertEqual(self.qualified(**options).mode, "full")
                self.assertEqual(self.record_files(), [])
        with patch.object(warmup, "gpu_inventory", return_value=None):
            self.assertIsNone(self.supervisor().record_key())
            self.assertEqual(self.qualified().mode, "full")
            self.assertEqual(self.record_files(), [])

    def test_gpu_inventory_requires_every_visible_device(self):
        output = "GPU-a, NVIDIA B200, 580.1\nGPU-b, NVIDIA B200, 580.1\n"
        completed = subprocess.CompletedProcess([], 0, stdout=output)
        with patch.object(warmup.subprocess, "run", return_value=completed):
            self.assertEqual(real_inventory("GPU-b"), [("GPU-b", "NVIDIA B200", "580.1")])
            self.assertIsNone(real_inventory("GPU-c"))
            self.assertIsNone(real_inventory(""))
        for error in (FileNotFoundError(), subprocess.CalledProcessError(9, "nvidia-smi"),
                      subprocess.TimeoutExpired("nvidia-smi", 30)):
            with self.subTest(error=error), patch.object(warmup.subprocess, "run", side_effect=error):
                self.assertIsNone(real_inventory("GPU-a"))

    def test_shutdown_during_short_pass_is_not_swallowed(self):
        self.qualified()
        supervisor = self.supervisor()
        def group(phase, shapes, timeout):
            self.calls.append((phase, len(shapes), timeout))
            supervisor.stopping.set()
            raise RuntimeError("connection reset by shutdown")
        supervisor.probe_group = group
        self.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "shutdown"):
            supervisor.warmup()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(supervisor.qualified.is_set())
        self.assertIsNone(supervisor.mode)

    def test_slow_cold_group_is_rerun_at_qualification_timeout(self):
        self.slow = {("cold_concurrency", 16): 30.0, ("cold_mixed_prefills", 3): 26.0}
        self.qualified(record_dir=False)
        qualify = [(phase, count) for phase, count, timeout in self.calls if phase.startswith("qualify")]
        self.assertIn(("qualify_concurrency", 16), qualify)
        self.assertIn(("qualify_mixed_prefills", 3), qualify)
        self.assertEqual([count for phase, count in qualify if phase == "qualify_concurrency"], [16])


if __name__ == "__main__":
    unittest.main()
