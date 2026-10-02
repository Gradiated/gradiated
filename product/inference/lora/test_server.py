import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

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
        self.header_delay = 0
        self.nonstream_delay = 0
        owner = self

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"upstream")

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                time.sleep(owner.header_delay)
                self.send_response(200)
                if not body.get("stream"):
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    time.sleep(owner.nonstream_delay)
                    try:
                        self.wfile.write(b'{"result":"done"}')
                    except OSError:
                        pass
                    return
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
            body = response.read()
            if path == "/metrics":
                self.assertTrue(body.startswith(b"upstream\n"))
                self.assertIn(b"gradiated_lora_loads_total 1\n", body)
                self.assertNotIn(self.name.encode(), body)
            else:
                self.assertEqual(body, b"upstream")

    def test_first_response_and_nonstream_body_allow_more_than_stream_idle_timeout(
        self,
    ):
        self.header_delay = self.nonstream_delay = 0.1
        with (
            mock.patch("server.STREAM_IDLE_TIMEOUT_SECONDS", 0.02),
            mock.patch("server.REQUEST_TIMEOUT_SECONDS", 1),
        ):
            connection = self.connect()
            connection.request(
                "POST",
                "/v1/chat/completions",
                json.dumps({"model": "base", "stream": False}),
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b'{"result":"done"}')

    def test_header_wait_is_still_bounded_by_request_deadline(self):
        self.header_delay = 0.2
        with mock.patch("server.REQUEST_TIMEOUT_SECONDS", 0.05):
            connection = self.connect()
            connection.request(
                "POST", "/v1/chat/completions", json.dumps({"model": "base"})
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 503)
            response.read()
        with self.manager.request("base"):
            pass

    def test_stalled_stream_closes_upstream_and_releases_active_reference(self):
        with mock.patch("server.STREAM_IDLE_TIMEOUT_SECONDS", 0.05):
            connection = self.connect()
            connection.request(
                "POST",
                "/v1/chat/completions",
                json.dumps({"model": self.name, "stream": True}),
                {"X-Gradiated-Workspace": self.spec["workspace_id"]},
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.readline(), b'data: {"delta":"first"}\n')
            response.read()
        deadline = time.monotonic() + 1
        while self.manager.entries[self.name]["active"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.manager.entries[self.name]["active"], 0)
        with self.manager.request("base"):
            pass

    def test_internal_prepare_requires_control_token_and_bounded_cold_admission(self):
        for authenticated, full, expected in (
            (False, False, 403),
            (True, False, 200),
            (True, True, 503),
        ):
            if full:
                self.manager.cold_requests.acquire()
                self.manager.cold_requests.acquire()
            try:
                headers = (
                    {"X-Gradiated-Adapter-Control": "synthetic-control-token"}
                    if authenticated
                    else {}
                )
                connection = self.connect()
                connection.request(
                    "POST",
                    "/internal/adapters/prepare",
                    json.dumps(
                        {"name": self.name, "workspace_id": self.spec["workspace_id"]}
                    ),
                    headers,
                )
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
            finally:
                if full:
                    self.manager.cold_requests.release()
                    self.manager.cold_requests.release()


if __name__ == "__main__":
    unittest.main()
