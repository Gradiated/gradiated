import http.server
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

launcher, fixture = map(Path, sys.argv[1:3])


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("Liveness fixture deadline exceeded")
        time.sleep(0.05)


class LivenessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.root.chmod(0o777)
        shutil.copy2(fixture, self.root / "entrypoint")
        (self.root / "base-id").write_text("test-base-v1\n")
        self.mode = "ready"
        self.requests = []
        self.release_hangs = threading.Event()
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                mode = owner.mode
                if mode == "hang":
                    owner.release_hangs.wait(40)
                try:
                    self.send_response(200 if mode == "ready" else 503)
                    self.end_headers()
                    self.wfile.write(b"health\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                if self.path == "/health":
                    owner.requests.append(mode)

            def log_message(self, *_):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.process = None
        self.job = None
        self.allocation = None
        self.log = (self.root / "launcher.log").open("w")

    def tearDown(self):
        self.release_hangs.set()
        try:
            if self.job:
                subprocess.run(
                    ["nomad", "job", "stop", "-detach", self.job],
                    capture_output=True,
                    timeout=15,
                    check=True,
                )
            if self.allocation and all(
                (self.root / name).exists()
                for name in ["leader", "ordinary", "detached"]
            ):
                self.assert_tree_gone()
            if self.job:
                subprocess.run(
                    ["nomad", "job", "stop", "-purge", self.job],
                    capture_output=True,
                    timeout=15,
                    check=True,
                )
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=10)
        finally:
            self.server.shutdown()
            self.thread.join(timeout=5)
            self.server.server_close()
            self.log.close()
            self.directory.cleanup()

    def environment(self, timeout=1800):
        return {
            "RUNTIME_PORT": str(self.server.server_port),
            "RUNTIME_STARTUP_TIMEOUT_SECONDS": str(timeout),
        }

    def start(self, timeout=1800):
        self.process = subprocess.Popen(
            [str(launcher), str(self.root), "--", str(self.root), "stubborn"],
            env={**os.environ, **self.environment(timeout)},
            stdout=self.log,
            stderr=self.log,
        )
        wait_for(lambda: (self.root / "ready").exists())

    def assert_tree_gone(self):
        for name in ["leader", "ordinary", "detached"]:
            pid = int((self.root / name).read_text())
            wait_for(lambda pid=pid: not Path(f"/proc/{pid}").exists())

    def test_startup_then_consecutive_failures(self):
        self.mode = "fail"
        self.start(timeout=1800)
        wait_for(lambda: self.requests.count("fail") >= 2)
        self.assertIsNone(self.process.poll())
        self.mode = "ready"
        wait_for(lambda: "ready" in self.requests)
        self.requests.clear()
        self.mode = "fail"
        wait_for(lambda: self.requests.count("fail") == 2)
        self.mode = "ready"
        wait_for(lambda: "ready" in self.requests)
        self.assertIsNone(self.process.poll())
        self.mode = "fail"
        started = time.monotonic()
        self.assertEqual(self.process.wait(timeout=18), 137)
        self.assertLess(time.monotonic() - started, 18)
        self.assert_tree_gone()

    def test_startup_timeout(self):
        self.mode = "fail"
        self.start(timeout=1)
        self.assertEqual(self.process.wait(timeout=10), 137)
        self.assert_tree_gone()

    def test_hung_health_response(self):
        self.start()
        wait_for(lambda: "ready" in self.requests)
        self.mode = "hang"
        started = time.monotonic()
        self.assertEqual(self.process.wait(timeout=21), 137)
        self.assertLess(time.monotonic() - started, 21)
        self.assert_tree_gone()

    def test_normal_shutdown_keeps_grace(self):
        self.start()
        wait_for(lambda: "ready" in self.requests)
        self.process.send_signal(signal.SIGTERM)
        time.sleep(2)
        self.assertIsNone(self.process.poll())
        self.assertTrue(
            Path(f"/proc/{int((self.root / 'detached').read_text())}").exists()
        )
        self.process.kill()
        self.process.wait(timeout=10)
        self.assert_tree_gone()

    def test_invalid_configuration(self):
        for values in [
            {"RUNTIME_PORT": "0"},
            {"RUNTIME_PORT": "65536"},
            {"RUNTIME_PORT": "1x"},
            {"RUNTIME_STARTUP_TIMEOUT_SECONDS": "0"},
            {"RUNTIME_STARTUP_TIMEOUT_SECONDS": "-1"},
            {"RUNTIME_STARTUP_TIMEOUT_SECONDS": "86401"},
        ]:
            with self.subTest(values=values):
                result = subprocess.run(
                    [str(launcher), str(self.root)],
                    env={**os.environ, **self.environment(), **values},
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=5,
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn("Invalid RUNTIME_", result.stderr)
                self.assertFalse((self.root / "ready").exists())



if __name__ == "__main__":
    if os.environ.get("GRADIATED_TEST_CONTAINER") != "1":
        raise SystemExit("Run through tests/Dockerfile")
    unittest.main(argv=[sys.argv[0], *sys.argv[3:]])
