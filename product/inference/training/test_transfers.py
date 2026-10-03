import http.client
import io
import logging
import socket
import ssl
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from transfers import read_body, transfer


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.body = b"verified artifact" * 32
        self.mode = "normal"
        self.requests = []
        self.connections = 0
        self.faults = []
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                test.requests.append(("GET", None))
                first = len(test.requests) == 1
                status = (
                    {"http": 503, "denied": 403, "redirect": 302}.get(test.mode, 200)
                    if first
                    else 200
                )
                self.send_response(status)
                self.send_header(
                    "Content-Length", str(len(test.body) if status == 200 else 0)
                )
                if status == 302:
                    self.send_header("Location", "https://unexpected.example/artifact")
                self.end_headers()
                if status == 200:
                    self.wfile.write(
                        test.body[:100]
                        if test.mode == "truncated" and first
                        else test.body
                    )
                self.close_connection = True

            def do_PUT(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                test.requests.append(("PUT", body))
                self.send_response(503 if len(test.requests) == 1 else 200)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.directory = tempfile.TemporaryDirectory()
        self.destination = Path(self.directory.name) / "artifact"
        self.url = "https://artifacts.example/artifact?signature=fixture-only"

        def connect_fault():
            self.connections += 1
            if self.faults:
                raise self.faults.pop(0)

        def connection(host, port=None, timeout=None):
            client = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=timeout
            )
            original_connect = client.connect

            def connect():
                connect_fault()
                original_connect()

            client.connect = connect
            return client

        self.patches = [
            patch("transfers.http.client.HTTPSConnection", side_effect=connection),
            patch("transfers.time.sleep"),
        ]
        for mocked in self.patches:
            mocked.start()

    def tearDown(self):
        for mocked in reversed(self.patches):
            mocked.stop()
        self.server.shutdown()
        self.server.server_close()
        self.directory.cleanup()

    def test_dns_failure_retries_without_logging_the_signed_url(self):
        self.faults = [socket.gaierror(-3, "temporary DNS failure")]
        with self.assertLogs("transfers", logging.WARNING) as logs:
            transfer(self.url, destination=self.destination)
        self.assertEqual(self.destination.read_bytes(), self.body)
        self.assertEqual(self.connections, 2)
        self.assertIn('"reason": "dns"', " ".join(logs.output))
        self.assertNotIn("signature", " ".join(logs.output))

    def test_truncated_body_is_retried_from_zero(self):
        self.mode = "truncated"
        transfer(self.url, destination=self.destination)
        self.assertEqual(self.destination.read_bytes(), self.body)
        self.assertEqual(len(self.requests), 2)

    def test_http_service_failure_retries(self):
        self.mode = "http"
        transfer(self.url, destination=self.destination)
        self.assertEqual(self.destination.read_bytes(), self.body)
        self.assertEqual(len(self.requests), 2)

    def test_auth_errors_and_redirects_fail_immediately(self):
        for mode, status in [("denied", 403), ("redirect", 302)]:
            with self.subTest(mode=mode):
                self.mode = mode
                self.requests.clear()
                self.connections = 0
                with self.assertRaises(urllib.error.HTTPError) as error:
                    transfer(self.url, destination=self.destination)
                self.assertEqual(error.exception.code, status)
                self.assertEqual(self.connections, 1)

    def test_upload_retry_sends_identical_bytes(self):
        self.destination.write_bytes(self.body)
        transfer(self.url, upload=self.destination)
        self.assertEqual(self.requests, [("PUT", self.body), ("PUT", self.body)])

    def test_persistent_connection_failure_is_limited_to_three_attempts(self):
        self.faults = [ConnectionResetError("reset") for _ in range(3)]
        with self.assertRaises(OSError):
            transfer(self.url, destination=self.destination)
        self.assertEqual(self.connections, 3)

    def test_tls_eof_retries_but_certificate_failure_does_not(self):
        self.faults = [ssl.SSLEOFError("TLS EOF")]
        transfer(self.url, destination=self.destination)
        self.assertEqual(self.connections, 2)
        self.connections = 0
        self.faults = [ssl.SSLCertVerificationError("certificate invalid")]
        with self.assertRaises(OSError):
            transfer(self.url, destination=self.destination)
        self.assertEqual(self.connections, 1)
        self.connections = 0
        self.faults = [ssl.SSLError("invalid TLS protocol")]
        with self.assertRaises(OSError):
            transfer(self.url, destination=self.destination)
        self.assertEqual(self.connections, 1)

    def test_expired_shared_deadline_prevents_network_work(self):
        clock = iter([0, 121])
        with (
            patch("transfers.time.monotonic", side_effect=lambda: next(clock, 121)),
            self.assertRaises(TimeoutError),
        ):
            transfer(self.url, destination=self.destination)
        self.assertEqual(self.connections, 0)

    def test_late_body_bytes_cannot_extend_the_shared_deadline(self):
        clock = [0]
        target = io.BytesIO()
        response = Mock()
        response.getheader.return_value = "4"
        response.isclosed.return_value = False

        def late_read(size):
            clock[0] = 121
            return b"late"

        response.read1.side_effect = late_read
        with (
            patch("transfers.time.monotonic", side_effect=lambda: clock[0]),
            self.assertRaises(TimeoutError),
        ):
            read_body(response, Mock(), target, 120)
        self.assertEqual(target.getvalue(), b"")

    def test_rejects_http_and_credential_urls(self):
        for url in [
            "http://artifacts.example/a",
            "https://user:password@artifacts.example/a",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                transfer(url, destination=self.destination)
        self.assertEqual(self.connections, 0)


if __name__ == "__main__":
    unittest.main()
