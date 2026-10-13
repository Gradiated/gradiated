import http.server
import io
import json
import threading
import time
import unittest
from unittest import mock

from grants import api_url, read_private, resolver


class PrivateControlTests(unittest.TestCase):
    def test_private_bridge_does_not_send_a_host_credential(self):
        response = io.BytesIO(b'{"data": []}')
        response.status = 200
        response.isclosed = lambda: response.closed
        connection = mock.Mock()
        connection.getresponse.return_value = response
        with mock.patch("http.client.HTTPConnection", return_value=connection):
            self.assertEqual(read_private("http://127.0.0.1:3004/api/internal/v1/task-versions/production"), {"data": []})
        headers = connection.request.call_args.kwargs["headers"]
        self.assertEqual(headers, {"Content-Type": "application/json"})

    def test_network_authentication_rejects_other_destinations_before_connecting(self):
        with mock.patch("http.client.HTTPSConnection") as connection:
            with self.assertRaises(ValueError):
                read_private("https://api.example/internal")
            connection.assert_not_called()

    def test_slow_grant_response_expires_shared_deadline(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", "12")
                self.end_headers()
                for value in b'{"data": []}':
                    try:
                        self.wfile.write(bytes([value]))
                        self.wfile.flush()
                    except OSError:
                        return
                    time.sleep(0.05)

            def log_message(self, *_):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        started = time.monotonic()
        with mock.patch("grants.validate_endpoint"), self.assertRaises(TimeoutError):
            read_private(
                f"http://127.0.0.1:{server.server_port}/grant",
                deadline=started + 0.15,
            )
        self.assertLess(time.monotonic() - started, 0.4)


class ApiUrlTests(unittest.TestCase):
    def test_derives_paths_for_production_and_local_api(self):
        for base in ("http://127.0.0.1:3004",):
            for path in ("adapter-downloads", "task-versions/production"):
                self.assertEqual(
                    api_url(base + "/", path), base + "/api/internal/v1/" + path
                )

    def test_rejects_remote_http_and_ambiguous_bases(self):
        for base in (
            "http://api.example",
            "https://user:password@api.example",
            "https://api.example?query=yes",
            "https://api.example#fragment",
            "file:///tmp/api",
            "",
        ):
            with self.assertRaises(ValueError):
                api_url(base, "adapter-downloads")


class VersionGrantTests(unittest.TestCase):
    def test_requests_exact_workspace_and_slug_and_rejects_mismatched_grants(self):
        name = "support/triage-日本語-20261002"
        grant = {"workspace_id": "workspace", "version": {"name": name}}
        resolve = resolver("http://127.0.0.1:3004")
        with mock.patch("grants.read_private", return_value=grant) as read:
            self.assertEqual(resolve(name, "workspace"), grant)
            self.assertEqual(
                read.call_args.args[1],
                {"workspace_id": "workspace", "version_name": name},
            )
        for bad in (
            {**grant, "workspace_id": "other"},
            {**grant, "version": {"name": "other"}},
        ):
            with (
                mock.patch("grants.read_private", return_value=bad),
                self.assertRaises(ValueError),
            ):
                resolve(name, "workspace")
