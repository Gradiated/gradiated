import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fixtures import archive, grant, settings
from manager import CapacityError, Manager
from server import create_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.payload = archive()
        self.spec = grant(self.payload)
        self.name = f"ft-{self.spec['version']['id']}-{self.spec['version']['adapter']['sha256']}"
        self.manager = Manager(
            settings(),
            self.temp.name,
            1,
            set(),
            fetch=lambda spec, path, hosts: path.write_bytes(self.payload),
        )
        self.manager.engine = lambda *_args: None
        self.manager.register(self.spec)
        self.manager.prepare(self.name)
        self.emitting = threading.Event()
        self.release = threading.Event()
        owner = self

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"upstream")

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b'data: {"delta":"first"}\n\n')
                self.wfile.flush()
                owner.emitting.set()
                owner.release.wait(5)
                try:
                    self.wfile.write(b"data: " + b"x" * (4 * 1024 * 1024) + b"\n\n")
                    self.wfile.flush()
                except OSError:
                    pass

        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        self.upstream.daemon_threads = True
        self.manager.engine_port = self.upstream.server_port
        self.front = create_server(self.manager, 0, "synthetic-control-token")
        for server in (self.upstream, self.front):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        self.addCleanup(self.release.set)

    def connect(self):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.front.server_port, timeout=5
        )
        self.addCleanup(connection.close)
        return connection

    def test_stream_flushes_before_completion_and_cancel_releases_reference(self):
        connection = self.connect()
        connection.request(
            "POST",
            "/v1/chat/completions",
            json.dumps({"model": self.name, "messages": [], "stream": True}),
            {
                "Content-Type": "application/json",
                "X-Gradiated-Workspace": self.spec["workspace_id"],
            },
        )
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.readline(), b'data: {"delta":"first"}\n')
        self.assertTrue(self.emitting.wait(2))
        self.assertEqual(self.manager.entries[self.name]["active"], 1)
        with self.assertRaises(CapacityError):
            self.manager.remove(self.name)
        response.close()
        connection.close()
        self.release.set()
        deadline = time.monotonic() + 5
        while self.manager.entries[self.name]["active"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.manager.entries[self.name]["active"], 0)
        with self.manager.request("base"):
            pass

    def test_cached_adapter_still_requires_workspace_identity(self):
        for workspace in (None, "01980000-0000-7000-8000-000000000002"):
            connection = self.connect()
            headers = {"Content-Type": "application/json"}
            if workspace:
                headers["X-Gradiated-Workspace"] = workspace
            connection.request(
                "POST",
                "/v1/chat/completions",
                json.dumps({"model": self.name}),
                headers,
            )
            response = connection.getresponse()
            self.assertIn(response.status, (400, 503))
            response.read()
            self.assertFalse(self.emitting.is_set())

    def test_health_is_not_ready_during_startup_or_uncertain_engine_state(self):
        for ready, failed, expected in (
            (False, False, 503),
            (True, False, 200),
            (True, True, 503),
        ):
            self.manager.ready, self.manager.failed = ready, failed
            connection = self.connect()
            connection.request("GET", "/health")
            response = connection.getresponse()
            self.assertEqual(response.status, expected)
            response.read()

    def test_metrics_and_model_discovery_still_reach_the_base_engine(self):
        for path in ("/metrics", "/v1/models"):
            connection = self.connect()
            connection.request("GET", path)
            response = connection.getresponse()
            self.assertEqual(response.read(), b"upstream")


if __name__ == "__main__":
    unittest.main()
