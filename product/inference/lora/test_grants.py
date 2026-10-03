import http.server
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from grants import api_url, host_identity, read_private, resolver


class HostCredentialTests(unittest.TestCase):
    def identity(self):
        return {
            "instance_id": "01980000-0000-7000-8000-000000000001",
            "nomad_node_id": "01980000-0000-7000-8000-000000000002",
            "token": "a" * 43,
        }

    def test_reads_existing_identity_and_rejects_invalid_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity.json"
            identity = self.identity()
            path.write_text(json.dumps(identity))
            self.assertEqual(host_identity(path), identity)
            for override in (
                {"token": "short"},
                {"instance_id": "bad"},
                {"nomad_node_id": "bad"},
            ):
                path.write_text(json.dumps({**identity, **override}))
                with self.assertRaises(ValueError):
                    host_identity(path)

    def test_private_requests_send_existing_host_identity(self):
        response = io.BytesIO(b'{"data": []}')
        response.status = 200
        response.isclosed = lambda: response.closed
        connection = mock.Mock()
        connection.getresponse.return_value = response
        with mock.patch("http.client.HTTPSConnection", return_value=connection):
            self.assertEqual(
                read_private("https://api.example/internal", self.identity()),
                {"data": []},
            )
        headers = connection.request.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer " + "a" * 43)
        self.assertEqual(
            headers["X-Gradiated-Instance-Id"], self.identity()["instance_id"]
        )
        self.assertEqual(
            headers["X-Gradiated-Nomad-Node-Id"], self.identity()["nomad_node_id"]
        )

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
        with self.assertRaises(TimeoutError):
            read_private(
                f"http://127.0.0.1:{server.server_port}/grant",
                self.identity(),
                deadline=started + 0.15,
            )
        self.assertLess(time.monotonic() - started, 0.4)


class ApiUrlTests(unittest.TestCase):
    def test_derives_paths_for_production_and_local_api(self):
        for base in (
            "https://api.example",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://[::1]:3001",
        ):
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
        resolve = resolver("https://api.example", {})
        with mock.patch("grants.read_private", return_value=grant) as read:
            self.assertEqual(resolve(name, "workspace"), grant)
            self.assertEqual(
                read.call_args.args[2],
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
