import hashlib
import http.client
import http.server
import io
import json
import math
import socket
import ssl
import struct
import tarfile
import tempfile
import threading
import time
import unittest
import urllib.error
import uuid
from itertools import pairwise
from pathlib import Path
from unittest import mock

from artifacts import (
    download,
    extract,
    file_hash,
    has_fused_experts,
    materialize,
    strict_json,
    validate_tensors,
)
from fixtures import GRAD_SOURCE, adapter_files, archive, grad_bundle


class Response(io.BytesIO):
    status = 200

    def isclosed(self):
        return self.closed


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = archive()
        self.spec = {
            "version": {
                "id": str(uuid.uuid4()),
                "adapter": {
                    "rank": 2,
                    "size_bytes": len(self.payload),
                    "sha256": hashlib.sha256(self.payload).hexdigest(),
                },
            },
            "download": {"url": "https://bucket.s3.amazonaws.com/adapter"},
        }

    def test_extraction_and_hash_check_deadline_between_chunks(self):
        archive_path = self.root / "archive.tar.gz"
        archive_path.write_bytes(self.payload)
        output = self.root / "extracted"
        output.mkdir()
        with (
            mock.patch("artifacts.remaining", side_effect=[1, 1, TimeoutError]),
            self.assertRaises(TimeoutError),
        ):
            extract(archive_path, output, 1024 * 1024, deadline=1)
        with (
            mock.patch("artifacts.remaining", side_effect=[1, TimeoutError]),
            self.assertRaises(TimeoutError),
        ):
            file_hash(archive_path, deadline=1)

    def test_recovered_cache_timeout_keeps_existing_files(self):
        from fixtures import grant, settings

        spec = grant(self.payload)
        fetch = lambda spec, path, hosts: path.write_bytes(self.payload)
        path, *_ = materialize(
            spec, self.root, 1024 * 1024, set(), settings()["model_config"], fetch=fetch
        )
        with (
            mock.patch("artifacts.file_hash", side_effect=TimeoutError),
            self.assertRaises(TimeoutError),
        ):
            materialize(
                spec,
                self.root,
                1024 * 1024,
                set(),
                settings()["model_config"],
                fetch=fetch,
            )
        self.assertTrue((path / "adapter_model.safetensors").is_file())
        self.assertTrue((path / ".verified.json").is_file())

    def test_download_checks_actual_bytes_and_full_checksum(self):
        opener = mock.Mock()
        opener.getresponse.return_value = Response(self.payload)
        opener.getresponse.return_value.status = 200
        with mock.patch("http.client.HTTPSConnection", return_value=opener):
            download(self.spec, self.root / "archive", {"bucket.s3.amazonaws.com"})
        self.assertEqual((self.root / "archive").read_bytes(), self.payload)
        for payload in (self.payload + b"extra", b"x" * len(self.payload)):
            opener.getresponse.return_value = Response(payload)
            opener.getresponse.return_value.status = 200
            with (
                mock.patch("http.client.HTTPSConnection", return_value=opener),
                self.assertRaises(ValueError),
            ):
                download(self.spec, self.root / "bad", {"bucket.s3.amazonaws.com"})

    def test_download_accepts_a_server_closing_the_connection_after_its_body(self):
        payload = self.payload

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Connection", "close")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                self.close_connection = True

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
            with mock.patch("http.client.HTTPSConnection", return_value=connection):
                download(self.spec, self.root / "closed", {"bucket.s3.amazonaws.com"})
            self.assertEqual((self.root / "closed").read_bytes(), payload)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_download_reads_use_remaining_budget_and_reject_redirects(self):
        connection = mock.Mock()
        clock = [9.0]

        class SlowResponse(Response):
            status = 200

            def read1(self, size):
                clock[0] = 11.0
                return super().read1(size)

        connection.getresponse.return_value = SlowResponse(self.payload)
        with (
            mock.patch("http.client.HTTPSConnection", return_value=connection),
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
            self.assertRaises(TimeoutError),
        ):
            download(self.spec, self.root / "slow", {"bucket.s3.amazonaws.com"}, 10)
        self.assertTrue(
            all(
                call.args == (1.0,)
                for call in connection.sock.settimeout.call_args_list
            )
        )
        connection.close.assert_called_once()
        connection.getresponse.return_value = Response(b"")
        connection.getresponse.return_value.status = 302
        with (
            mock.patch(
                "http.client.HTTPSConnection", return_value=connection
            ) as connect,
            self.assertRaises(urllib.error.HTTPError),
        ):
            download(self.spec, self.root / "redirect", {"bucket.s3.amazonaws.com"})
        connect.assert_called_once()

    def test_slow_transfer_restarts_if_server_ignores_range(self):
        clock = [0.0]
        first, second = mock.Mock(), mock.Mock()
        payload = self.payload

        class SlowResponse(Response):
            def read1(self, size):
                clock[0] += 3
                return super().read1(min(size, 8))

        first.getresponse.return_value = SlowResponse(payload)
        second.getresponse.return_value = Response(payload)
        with (
            mock.patch(
                "http.client.HTTPSConnection", side_effect=[first, second]
            ) as connect,
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
            self.assertLogs("artifacts", level="WARNING") as logs,
        ):
            download(self.spec, self.root / "retry", {"bucket.s3.amazonaws.com"}, 60)
        self.assertEqual((self.root / "retry").read_bytes(), payload)
        self.assertEqual(connect.call_count, 2)
        first.close.assert_called_once()
        second.close.assert_called_once()
        self.assertEqual(
            second.request.call_args.kwargs["headers"],
            {"Range": f"bytes=8-{len(payload) - 1}"},
        )
        self.assertEqual(clock[0], 6)
        self.assertIn('"event": "lora_download_retry"', logs.output[0])
        self.assertNotIn("bucket.s3.amazonaws.com", logs.output[0])

    def test_progress_within_attempt_budget_is_not_restarted(self):
        clock = [0.0]
        payload = self.payload
        connection = mock.Mock()

        class SteadyResponse(Response):
            def isclosed(self):
                return self.tell() == len(payload)

            def read1(self, size):
                clock[0] += 2
                return super().read1((len(payload) + 1) // 2)

        connection.getresponse.return_value = SteadyResponse(payload)
        with (
            mock.patch(
                "http.client.HTTPSConnection", return_value=connection
            ) as connect,
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
        ):
            download(self.spec, self.root / "steady", {"bucket.s3.amazonaws.com"}, 60)
        self.assertEqual((self.root / "steady").read_bytes(), payload)
        self.assertEqual(clock[0], 4)
        connect.assert_called_once()

    def test_slow_transfer_resumes_partial_bytes_with_a_valid_range(self):
        clock = [0.0]
        payload = self.payload

        class SlowResponse(Response):
            def read1(self, size):
                clock[0] += 3
                return super().read1(min(size, 8))

        class PartialResponse(Response):
            status = 206

            def getheader(self, name):
                return f"bytes 8-{len(payload) - 1}/{len(payload)}"

        first, second = mock.Mock(), mock.Mock()
        first.getresponse.return_value = SlowResponse(payload)
        second.getresponse.return_value = PartialResponse(payload[8:])
        with (
            mock.patch("http.client.HTTPSConnection", side_effect=[first, second]),
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
            self.assertLogs("artifacts", level="WARNING"),
        ):
            download(self.spec, self.root / "resumed", {"bucket.s3.amazonaws.com"}, 60)
        self.assertEqual((self.root / "resumed").read_bytes(), payload)
        self.assertEqual(
            second.request.call_args.kwargs["headers"],
            {"Range": f"bytes=8-{len(payload) - 1}"},
        )

    def test_resumed_transfer_rejects_wrong_ranges_and_corrupt_bytes(self):
        payload = self.payload
        for header, body in (
            (None, payload[8:]),
            (f"bytes 0-{len(payload) - 1}/{len(payload)}", payload[8:]),
            (f"bytes 8-{len(payload) - 2}/{len(payload)}", payload[8:]),
            (f"bytes 8-{len(payload) - 1}/{len(payload) + 1}", payload[8:]),
            (
                f"bytes 8-{len(payload) - 1}/{len(payload)}",
                payload[8:-1] + bytes([payload[-1] ^ 1]),
            ),
        ):
            with self.subTest(header=header):
                clock = [0.0]

                class SlowResponse(Response):
                    def read1(self, size, clock=clock):
                        clock[0] += 3
                        return super().read1(min(size, 8))

                class PartialResponse(Response):
                    status = 206

                    def getheader(self, name, header=header):
                        return header

                first, second = mock.Mock(), mock.Mock()
                first.getresponse.return_value = SlowResponse(payload)
                second.getresponse.return_value = PartialResponse(body)
                with (
                    mock.patch(
                        "http.client.HTTPSConnection", side_effect=[first, second]
                    ) as connect,
                    mock.patch(
                        "artifacts.time.monotonic",
                        side_effect=lambda clock=clock: clock[0],
                    ),
                    self.assertLogs("artifacts", level="WARNING"),
                    self.assertRaises(ValueError),
                ):
                    download(
                        self.spec,
                        self.root / "invalid-range",
                        {"bucket.s3.amazonaws.com"},
                        60,
                    )
                self.assertEqual(connect.call_count, 2)
                first.close.assert_called_once()
                second.close.assert_called_once()

    def test_connect_timeout_cannot_resume_a_previous_destination(self):
        destination = self.root / "previous"
        destination.write_bytes(b"previous artifact")
        first, second = mock.Mock(), mock.Mock()
        first.connect.side_effect = TimeoutError()
        second.getresponse.return_value = Response(self.payload)
        with (
            mock.patch("http.client.HTTPSConnection", side_effect=[first, second]),
            self.assertLogs("artifacts", level="WARNING"),
        ):
            download(self.spec, destination, {"bucket.s3.amazonaws.com"})
        self.assertEqual(second.request.call_args.kwargs["headers"], {})
        self.assertEqual(destination.read_bytes(), self.payload)

    def test_large_download_uses_concurrent_non_overlapping_ranges(self):
        payload = hashlib.shake_256(b"parallel-download").digest(8 * 1024 * 1024 + 97)
        self.spec["version"]["adapter"].update(
            size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()
        )
        requests = []
        barrier = threading.Barrier(8)

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                header = self.headers["Range"]
                requests.append(header)
                start, end = map(int, header.removeprefix("bytes=").split("-"))
                barrier.wait(timeout=5)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
                self.send_header("Content-Length", str(end - start + 1))
                self.end_headers()
                self.wfile.write(payload[start : end + 1])

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with mock.patch(
                "http.client.HTTPSConnection",
                side_effect=lambda *_args, **_kwargs: http.client.HTTPConnection(
                    "127.0.0.1", server.server_port
                ),
            ):
                download(self.spec, self.root / "parallel", {"bucket.s3.amazonaws.com"})
            self.assertEqual((self.root / "parallel").read_bytes(), payload)
            ranges = sorted(
                tuple(map(int, value.removeprefix("bytes=").split("-")))
                for value in requests
            )
            self.assertEqual(len(ranges), 8)
            self.assertEqual(ranges[0][0], 0)
            self.assertEqual(ranges[-1][1], len(payload) - 1)
            for previous, following in pairwise(ranges):
                self.assertEqual(previous[1] + 1, following[0])
            self.assertTrue(
                all(end - start + 1 <= 2 * 1024 * 1024 for start, end in ranges)
            )
            self.assertEqual({path.name for path in self.root.iterdir()}, {"parallel"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_large_archive_never_adds_queued_ranges(self):
        size = 128 * 1024 * 1024 + 97
        self.spec["version"]["adapter"]["size_bytes"] = size
        bounds = []
        barrier = threading.Barrier(8)
        deadline = time.monotonic() + 60

        def part(_url, _destination, start, end, total, shared_deadline):
            self.assertEqual(total, size)
            self.assertEqual(shared_deadline, deadline)
            bounds.append((start, end))
            barrier.wait(timeout=5)

        with (
            mock.patch("artifacts._download_part", side_effect=part),
            mock.patch(
                "artifacts.file_hash",
                return_value=self.spec["version"]["adapter"]["sha256"],
            ),
        ):
            download(
                self.spec, self.root / "large", {"bucket.s3.amazonaws.com"}, deadline
            )
        self.assertEqual(len(bounds), 8)
        bounds.sort()
        self.assertEqual(bounds[0][0], 0)
        self.assertEqual(bounds[-1][1], size - 1)
        for previous, following in pairwise(bounds):
            self.assertEqual(previous[1] + 1, following[0])

    def test_large_download_rejects_invalid_ranges_and_missing_or_corrupt_bytes(self):
        payload = hashlib.shake_256(b"invalid-range").digest(8 * 1024 * 1024 + 9)
        self.spec["version"]["adapter"].update(
            size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()
        )
        for defect in ("ignored", "offset", "short", "oversized", "corrupt"):
            with self.subTest(defect=defect):
                connections = []

                def connect(*_args, connections=connections, defect=defect, **_kwargs):
                    connection = mock.Mock()
                    connections.append(connection)
                    bounds = []

                    def request(_method, _path, headers):
                        bounds.extend(
                            map(int, headers["Range"].removeprefix("bytes=").split("-"))
                        )

                    def response():
                        start, end = bounds
                        data = payload[start : end + 1]
                        if start:
                            if defect == "short":
                                data = data[:-1]
                            elif defect == "oversized":
                                data += b"x"
                            elif defect == "corrupt":
                                data = bytes([data[0] ^ 1]) + data[1:]
                        result = Response(data)
                        result.status = 200 if start and defect == "ignored" else 206
                        result.getheader = lambda _name: (
                            f"bytes {start + (1 if start and defect == 'offset' else 0)}-{end}/{len(payload)}"
                        )
                        return result

                    connection.request.side_effect = request
                    connection.getresponse.side_effect = response
                    return connection

                with (
                    mock.patch("http.client.HTTPSConnection", side_effect=connect),
                    mock.patch("artifacts.time.sleep"),
                    self.assertRaises(
                        ConnectionError if defect == "short" else ValueError
                    ),
                ):
                    download(
                        self.spec,
                        self.root / "invalid-part",
                        {"bucket.s3.amazonaws.com"},
                    )
                self.assertGreaterEqual(len(connections), 2)
                self.assertLessEqual(len(connections), 96 if defect == "short" else 8)
                for connection in connections:
                    connection.request.assert_called_once()
                    connection.close.assert_called_once()

    def test_immediate_connect_timeouts_have_a_bounded_attempt_count(self):
        connections = [mock.Mock() for _ in range(12)]
        for connection in connections:
            connection.connect.side_effect = TimeoutError()
        with (
            mock.patch(
                "http.client.HTTPSConnection", side_effect=connections
            ) as connect,
            self.assertLogs("artifacts", level="WARNING") as logs,
            self.assertRaises(TimeoutError),
        ):
            download(
                self.spec, self.root / "connect-timeouts", {"bucket.s3.amazonaws.com"}
            )
        self.assertEqual(connect.call_count, 12)
        self.assertEqual(len(logs.records), 11)
        for connection in connections:
            connection.close.assert_called_once()

    def test_connection_failure_resumes_written_bytes(self):
        for error in (
            ConnectionResetError,
            BrokenPipeError,
            http.client.RemoteDisconnected,
            ssl.SSLEOFError,
        ):
            with self.subTest(error=error):
                first, second = mock.Mock(), mock.Mock()

                class ResetResponse(Response):
                    failure = error

                    def read1(self, size):
                        if self.tell() >= 8:
                            raise self.failure(
                                "transport closed https://private.invalid/?secret"
                            )
                        return super().read1(min(size, 8))

                first.getresponse.return_value = ResetResponse(self.payload)
                response = Response(self.payload[8:])
                response.status = 206
                response.getheader = lambda _: (
                    f"bytes 8-{len(self.payload) - 1}/{len(self.payload)}"
                )
                second.getresponse.return_value = response
                with (
                    mock.patch(
                        "http.client.HTTPSConnection", side_effect=[first, second]
                    ),
                    mock.patch("artifacts.time.sleep") as pause,
                    self.assertLogs("artifacts", level="WARNING") as logs,
                ):
                    download(
                        self.spec,
                        self.root / "reset-resumed",
                        {"bucket.s3.amazonaws.com"},
                    )
                self.assertEqual(
                    (self.root / "reset-resumed").read_bytes(), self.payload
                )
                self.assertEqual(
                    second.request.call_args.kwargs["headers"],
                    {"Range": f"bytes=8-{len(self.payload) - 1}"},
                )
                pause.assert_called_once_with(1)
                self.assertIn('"reason": "connection"', logs.output[0])
                self.assertNotIn("private.invalid", logs.output[0])
                first.close.assert_called_once()
                second.close.assert_called_once()

    def test_tls_eof_during_connect_recovers(self):
        first, second = mock.Mock(), mock.Mock()
        first.connect.side_effect = ssl.SSLEOFError("TLS connection closed")
        second.getresponse.return_value = Response(self.payload)
        with (
            mock.patch("http.client.HTTPSConnection", side_effect=[first, second]),
            mock.patch("artifacts.time.sleep") as pause,
            self.assertLogs("artifacts", level="WARNING") as logs,
        ):
            download(
                self.spec, self.root / "tls-recovered", {"bucket.s3.amazonaws.com"}
            )
        self.assertEqual((self.root / "tls-recovered").read_bytes(), self.payload)
        self.assertIn('"reason": "connection"', logs.output[0])
        pause.assert_called_once_with(1)
        first.close.assert_called_once()
        second.close.assert_called_once()

    def test_tls_certificate_and_protocol_failures_do_not_retry(self):
        for error in (ssl.SSLCertVerificationError, ssl.SSLError):
            with self.subTest(error=error):
                connection = mock.Mock()
                connection.connect.side_effect = error("TLS validation failed")
                with (
                    mock.patch(
                        "http.client.HTTPSConnection", return_value=connection
                    ) as connect,
                    mock.patch("artifacts.time.sleep") as pause,
                    self.assertRaises(error),
                ):
                    download(
                        self.spec, self.root / "tls-failed", {"bucket.s3.amazonaws.com"}
                    )
                connect.assert_called_once()
                pause.assert_not_called()
                connection.close.assert_called_once()

    def test_persistent_connection_failures_have_bounded_attempts(self):
        connections = [mock.Mock() for _ in range(12)]
        for connection in connections:
            connection.connect.side_effect = ConnectionResetError("connection reset")
        with (
            mock.patch(
                "http.client.HTTPSConnection", side_effect=connections
            ) as connect,
            mock.patch("artifacts.time.sleep") as pause,
            self.assertLogs("artifacts", level="WARNING") as logs,
            self.assertRaises(ConnectionResetError),
        ):
            download(self.spec, self.root / "reset-failed", {"bucket.s3.amazonaws.com"})
        self.assertEqual(connect.call_count, 12)
        self.assertEqual(pause.call_count, 11)
        self.assertEqual(len(logs.records), 11)
        for connection in connections:
            connection.close.assert_called_once()

    def test_connection_failure_cannot_extend_expired_deadline(self):
        clock = [0.0]
        connection = mock.Mock()

        def fail():
            clock[0] = 61
            raise ConnectionResetError("connection reset")

        connection.connect.side_effect = fail
        with (
            mock.patch(
                "http.client.HTTPSConnection", return_value=connection
            ) as connect,
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
            mock.patch("artifacts.time.sleep") as pause,
            self.assertRaises(ConnectionResetError),
        ):
            download(
                self.spec, self.root / "reset-expired", {"bucket.s3.amazonaws.com"}, 60
            )
        connect.assert_called_once()
        pause.assert_not_called()
        connection.close.assert_called_once()

    def test_real_http_clean_mid_body_disconnect_resumes(self):
        payload = self.payload
        attempts = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                attempts.append(self.headers.get("Range"))
                if len(attempts) == 1:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload[:8])
                    self.wfile.flush()
                    self.close_connection = True
                    return
                self.send_response(206)
                self.send_header(
                    "Content-Range", f"bytes 8-{len(payload) - 1}/{len(payload)}"
                )
                self.send_header("Content-Length", str(len(payload) - 8))
                self.end_headers()
                self.wfile.write(payload[8:])

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (
                mock.patch(
                    "http.client.HTTPSConnection",
                    side_effect=lambda *args, **kwargs: http.client.HTTPConnection(
                        "127.0.0.1", server.server_port, timeout=kwargs["timeout"]
                    ),
                ),
                mock.patch("artifacts.time.sleep") as pause,
                self.assertLogs("artifacts", level="WARNING"),
            ):
                download(self.spec, self.root / "real-eof", {"bucket.s3.amazonaws.com"})
            self.assertEqual((self.root / "real-eof").read_bytes(), payload)
            self.assertEqual(attempts, [None, f"bytes=8-{len(payload) - 1}"])
            pause.assert_called_once_with(1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_real_http_disconnect_before_headers_recovers(self):
        payload = self.payload
        attempts = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                attempts.append(self.path)
                if len(attempts) == 1:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    self.close_connection = True
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (
                mock.patch(
                    "http.client.HTTPSConnection",
                    side_effect=lambda *args, **kwargs: http.client.HTTPConnection(
                        "127.0.0.1", server.server_port, timeout=kwargs["timeout"]
                    ),
                ),
                mock.patch("artifacts.time.sleep"),
                self.assertLogs("artifacts", level="WARNING"),
            ):
                download(
                    self.spec, self.root / "real-reset", {"bucket.s3.amazonaws.com"}
                )
            self.assertEqual((self.root / "real-reset").read_bytes(), payload)
            self.assertEqual(len(attempts), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_dns_failure_recovers_without_exposing_the_artifact_url(self):
        first, second = mock.Mock(), mock.Mock()
        first.connect.side_effect = socket.gaierror(socket.EAI_AGAIN, "DNS unavailable")
        second.getresponse.return_value = Response(self.payload)
        with (
            mock.patch("http.client.HTTPSConnection", side_effect=[first, second]),
            mock.patch("artifacts.time.sleep") as pause,
            self.assertLogs("artifacts", level="WARNING") as logs,
        ):
            download(
                self.spec, self.root / "dns-recovered", {"bucket.s3.amazonaws.com"}
            )
        self.assertEqual((self.root / "dns-recovered").read_bytes(), self.payload)
        pause.assert_called_once_with(1)
        self.assertIn('"reason": "dns"', logs.output[0])
        self.assertNotIn("bucket.s3.amazonaws.com", logs.output[0])
        first.close.assert_called_once()
        second.close.assert_called_once()

    def test_persistent_dns_failure_has_a_bounded_attempt_count(self):
        connections = [mock.Mock() for _ in range(12)]
        for connection in connections:
            connection.connect.side_effect = socket.gaierror(
                socket.EAI_AGAIN, "DNS unavailable"
            )
        with (
            mock.patch(
                "http.client.HTTPSConnection", side_effect=connections
            ) as connect,
            mock.patch("artifacts.time.sleep") as pause,
            self.assertLogs("artifacts", level="WARNING") as logs,
            self.assertRaises(socket.gaierror),
        ):
            download(self.spec, self.root / "dns-failed", {"bucket.s3.amazonaws.com"})
        self.assertEqual(connect.call_count, 12)
        self.assertEqual(pause.call_count, 11)
        self.assertEqual(len(logs.records), 11)
        for connection in connections:
            connection.close.assert_called_once()

    def test_dns_failure_does_not_extend_an_expired_deadline(self):
        clock = [0.0]
        connection = mock.Mock()

        def fail():
            clock[0] = 61
            raise socket.gaierror(socket.EAI_AGAIN, "DNS unavailable")

        connection.connect.side_effect = fail
        with (
            mock.patch(
                "http.client.HTTPSConnection", return_value=connection
            ) as connect,
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
            mock.patch("artifacts.time.sleep") as pause,
            self.assertRaises(socket.gaierror),
        ):
            download(
                self.spec, self.root / "dns-expired", {"bucket.s3.amazonaws.com"}, 60
            )
        connect.assert_called_once()
        pause.assert_not_called()
        connection.close.assert_called_once()

    def test_dns_failure_after_partial_transfer_keeps_the_written_prefix(self):
        clock = [0.0]
        first, second, third = mock.Mock(), mock.Mock(), mock.Mock()

        class SlowResponse(Response):
            def read1(self, size):
                clock[0] += 3
                return super().read1(min(size, 8))

        first.getresponse.return_value = SlowResponse(self.payload)
        second.connect.side_effect = socket.gaierror(
            socket.EAI_AGAIN, "DNS unavailable"
        )
        response = Response(self.payload[8:])
        response.status = 206
        response.getheader = lambda _: (
            f"bytes 8-{len(self.payload) - 1}/{len(self.payload)}"
        )
        third.getresponse.return_value = response
        with (
            mock.patch(
                "http.client.HTTPSConnection", side_effect=[first, second, third]
            ),
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
            mock.patch("artifacts.time.sleep"),
            self.assertLogs("artifacts", level="WARNING"),
        ):
            download(
                self.spec, self.root / "dns-resumed", {"bucket.s3.amazonaws.com"}, 60
            )
        self.assertEqual((self.root / "dns-resumed").read_bytes(), self.payload)
        second.request.assert_not_called()
        self.assertEqual(
            third.request.call_args.kwargs["headers"],
            {"Range": f"bytes=8-{len(self.payload) - 1}"},
        )

    def test_multiple_attempt_timeouts_resume_written_bytes(self):
        clock = [0.0]
        payload = self.payload

        class PartialResponse(Response):
            def __init__(self, offset, slow):
                super().__init__(payload[offset:])
                self.offset, self.slow = offset, slow
                self.status = 206 if offset else 200

            def getheader(self, _name):
                return f"bytes {self.offset}-{len(payload) - 1}/{len(payload)}"

            def read1(self, size):
                if self.slow:
                    clock[0] += 3
                    size = min(size, 8)
                return super().read1(size)

        connections = [mock.Mock() for _ in range(4)]
        for index, connection in enumerate(connections):
            connection.getresponse.return_value = PartialResponse(index * 8, index < 3)
        with (
            mock.patch(
                "http.client.HTTPSConnection", side_effect=connections
            ) as connect,
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
            self.assertLogs("artifacts", level="WARNING") as logs,
        ):
            download(
                self.spec,
                self.root / "resumed-repeatedly",
                {"bucket.s3.amazonaws.com"},
                60,
            )
        self.assertEqual((self.root / "resumed-repeatedly").read_bytes(), payload)
        self.assertEqual(connect.call_count, 4)
        self.assertEqual(clock[0], 18)
        self.assertEqual(len(logs.records), 3)
        for index, connection in enumerate(connections):
            self.assertEqual(
                connection.request.call_args.kwargs["headers"],
                {"Range": f"bytes={index * 8}-{len(payload) - 1}"} if index else {},
            )
            connection.close.assert_called_once()

    def test_retry_still_stops_at_the_original_deadline(self):
        clock = [0.0]

        class SlowResponse(Response):
            def read1(self, size):
                clock[0] += 21
                return super().read1(min(size, 8))

        first, second = mock.Mock(), mock.Mock()
        first.getresponse.return_value = SlowResponse(self.payload)
        second.getresponse.return_value = SlowResponse(self.payload)
        with (
            mock.patch(
                "http.client.HTTPSConnection", side_effect=[first, second]
            ) as connect,
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
            self.assertLogs("artifacts", level="WARNING"),
            self.assertRaises(TimeoutError),
        ):
            download(self.spec, self.root / "expired", {"bucket.s3.amazonaws.com"}, 40)
        self.assertEqual(clock[0], 42)
        self.assertEqual(connect.call_count, 2)
        first.close.assert_called_once()
        second.close.assert_called_once()

    def test_denied_and_failed_http_responses_are_not_retried(self):
        for status in (403, 500):
            connection = mock.Mock()
            connection.getresponse.return_value = Response(b"")
            connection.getresponse.return_value.status = status
            with (
                mock.patch(
                    "http.client.HTTPSConnection", return_value=connection
                ) as connect,
                self.assertRaises(urllib.error.HTTPError),
            ):
                download(self.spec, self.root / "denied", {"bucket.s3.amazonaws.com"})
            connect.assert_called_once()
            connection.close.assert_called_once()

    def test_untrusted_download_destinations_are_rejected_before_network_access(self):
        for url in (
            "http://bucket.s3.amazonaws.com/adapter",
            "https://evil.example/adapter",
            "https://user:password@bucket.s3.amazonaws.com/adapter",
            "https://bucket.s3.amazonaws.com:8443/adapter",
            "https://bucket.s3.amazonaws.com.evil.example/adapter",
        ):
            self.spec["download"]["url"] = url
            with (
                mock.patch("http.client.HTTPSConnection") as opener,
                self.assertRaises(ValueError),
            ):
                download(self.spec, self.root / "bad", {"bucket.s3.amazonaws.com"})
            opener.assert_not_called()

    def test_json_rejects_duplicate_keys_and_nonfinite_values(self):
        for value in ('{"r":2,"r":4}', '{"alpha":NaN}', '{"alpha":1e999}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                strict_json(value)
        with self.assertRaises(TypeError):
            strict_json("[]")

    def write_experts(self, fused, missing=False, dtype="BF16"):
        config = {
            "peft_type": "LORA",
            "r": 2,
            "lora_alpha": 4,
            "target_modules": ["q_proj", "gate_proj"],
        }
        (self.root / "adapter_config.json").write_text(json.dumps(config))
        tensors, payload = {}, bytearray()
        for layer in range(2):
            indices = [None] if layer == 0 or fused else range(2 if missing else 3)
            for expert in indices:
                module = (
                    "self_attn.q_proj"
                    if layer == 0
                    else (
                        "mlp.experts.gate_proj"
                        if fused
                        else f"mlp.experts.{expert}.gate_proj"
                    )
                )
                for side, shape in (("A", [2, 4]), ("B", [4, 2])):
                    if layer == 1 and fused:
                        shape = [3, *shape]
                    size = (4 if dtype == "F32" else 2) * math.prod(shape)
                    tensors[
                        f"base_model.model.layers.{layer}.{module}.lora_{side}.weight"
                    ] = {
                        "dtype": dtype,
                        "shape": shape,
                        "data_offsets": [len(payload), len(payload) + size],
                    }
                    payload.extend(bytes(size))
        header = json.dumps(tensors).encode()
        (self.root / "adapter_model.safetensors").write_bytes(
            struct.pack("<Q", len(header)) + header + payload
        )

    def test_dense_and_sparse_layers_accept_complete_2d_and_3d_expert_tensors(self):
        for fused in (False, True):
            self.write_experts(fused)
            self.assertGreater(
                validate_tensors(
                    self.root,
                    self.spec,
                    {"text_config": {"num_hidden_layers": 2, "n_routed_experts": 3}},
                ),
                0,
            )
            self.assertEqual(has_fused_experts(self.root), fused)
        self.write_experts(False, missing=True)
        with self.assertRaises(ValueError):
            validate_tensors(
                self.root, self.spec, {"num_hidden_layers": 2, "n_routed_experts": 3}
            )

    def test_extraction_reserves_space_before_writing_payloads(self):
        archive_path = self.root / "archive"
        archive_path.write_bytes(self.payload)
        output = self.root / "adapter"
        output.mkdir()
        reservations = []
        extract(archive_path, output, 1024 * 1024, reserve=reservations.append)
        self.assertEqual(
            reservations[-1], sum(item.stat().st_size for item in output.iterdir())
        )
        self.assertEqual(len(reservations), 2)

    def test_float32_tensors_use_four_byte_accounting(self):
        self.write_experts(True)
        half = validate_tensors(
            self.root, self.spec, {"num_hidden_layers": 2, "n_routed_experts": 3}
        )
        self.write_experts(True, dtype="F32")
        full = validate_tensors(
            self.root, self.spec, {"num_hidden_layers": 2, "n_routed_experts": 3}
        )
        self.assertEqual(full, 2 * half)

    def write_head(self, shapes=None, target="lm_head", prefix="base_model.model.lm_head"):
        config = {"peft_type": "LORA", "r": 2, "lora_alpha": 4,
                  "target_modules": [target]}
        (self.root / "adapter_config.json").write_text(json.dumps(config))
        tensors, payload = {}, bytearray()
        for side, shape in (shapes or {"A": [2, 4], "B": [7, 2]}).items():
            size = 4 * math.prod(shape)
            tensors[f"{prefix}.lora_{side}.weight"] = {
                "dtype": "F32", "shape": shape,
                "data_offsets": [len(payload), len(payload) + size],
            }
            payload.extend(bytes(size))
        header = json.dumps(tensors).encode()
        (self.root / "adapter_model.safetensors").write_bytes(
            struct.pack("<Q", len(header)) + header + payload
        )

    def test_top_level_head_requires_declared_and_host_allowed_target(self):
        model = {"num_hidden_layers": 2, "hidden_size": 4, "vocab_size": 7}
        self.write_head()
        for allowed in (None, [], ["q_proj"], "not_lm_head"):
            with self.subTest(allowed=allowed), self.assertRaises(ValueError):
                validate_tensors(self.root, self.spec, model,
                                 allowed_target_modules=allowed)
        self.assertEqual(validate_tensors(self.root, self.spec, model,
                                         allowed_target_modules=["lm_head"]), 88)
        self.write_head(prefix="lm_head")
        self.assertEqual(validate_tensors(self.root, self.spec, {"text_config": model},
                                         allowed_target_modules=["lm_head"]), 88)
        self.write_head(target="q_proj")
        with self.assertRaises(ValueError):
            validate_tensors(self.root, self.spec, model,
                             allowed_target_modules=["lm_head"])

    def test_head_host_allowlist_is_rechecked_on_cached_artifacts(self):
        self.write_head()
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as bundle:
            for name in ("adapter_config.json", "adapter_model.safetensors"):
                body = (self.root / name).read_bytes()
                member = tarfile.TarInfo(name)
                member.size = len(body)
                bundle.addfile(member, io.BytesIO(body))
        payload = data.getvalue()
        self.spec["version"]["adapter"].update(
            sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload)
        )
        cache = self.root / "cache"
        cache.mkdir()
        model = {"num_hidden_layers": 2, "hidden_size": 4, "vocab_size": 7}
        fetch = mock.Mock(side_effect=lambda spec, path, hosts: path.write_bytes(payload))
        materialize(self.spec, cache, 1024 * 1024, set(), model, fetch=fetch,
                    allowed_target_modules=["lm_head"])
        materialize(self.spec, cache, 1024 * 1024, set(), model, fetch=fetch,
                    allowed_target_modules=["lm_head"])
        self.assertEqual(fetch.call_count, 1)
        with self.assertRaises(ValueError):
            materialize(self.spec, cache, 1024 * 1024, set(), model, fetch=fetch,
                        allowed_target_modules=["q_proj"])

    def test_head_rejects_transposed_or_rank_stabilized_parameterization(self):
        model = {"num_hidden_layers": 2, "hidden_size": 4, "vocab_size": 7}
        for key in ("fan_in_fan_out", "use_rslora"):
            self.write_head()
            path = self.root / "adapter_config.json"
            config = json.loads(path.read_text())
            path.write_text(json.dumps({**config, key: True}))
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_tensors(self.root, self.spec, model,
                                 allowed_target_modules=["lm_head"])

    def test_head_rejects_wrong_shapes_global_names_and_missing_pairs(self):
        model = {"text_config": {"num_hidden_layers": 2, "hidden_size": 4,
                                 "vocab_size": 7}}
        cases = [
            ({"A": [2, 5], "B": [7, 2]}, "base_model.model.lm_head"),
            ({"A": [2, 4], "B": [8, 2]}, "base_model.model.lm_head"),
            ({"A": [3, 4], "B": [7, 3]}, "base_model.model.lm_head"),
            ({"A": [1, 2, 4], "B": [1, 7, 2]}, "base_model.model.lm_head"),
            ({"A": [2, 4]}, "base_model.model.lm_head"),
            ({"B": [7, 2]}, "base_model.model.lm_head"),
            (None, "base_model.model.layers.0.lm_head"),
            (None, "base_model.model.embed_tokens"),
            (None, "base_model.model.unknown.lm_head"),
        ]
        for shapes, prefix in cases:
            with self.subTest(shapes=shapes, prefix=prefix):
                self.write_head(shapes=shapes, prefix=prefix)
                with self.assertRaises(ValueError):
                    validate_tensors(self.root, self.spec, model,
                                     allowed_target_modules=["lm_head"])
        self.write_head()
        for dimensions in ({}, {"hidden_size": True, "vocab_size": 7},
                           {"hidden_size": 4, "vocab_size": 0}):
            with self.subTest(dimensions=dimensions), self.assertRaises(ValueError):
                validate_tensors(self.root, self.spec,
                                 {"num_hidden_layers": 2, **dimensions},
                                 allowed_target_modules=["lm_head"])

    def test_header_length_is_bounded_before_reading(self):
        self.write_experts(True)
        weights = self.root / "adapter_model.safetensors"
        for prefix in (b"", struct.pack("<Q", 100_000_001)):
            weights.write_bytes(prefix)
            with self.assertRaises(ValueError):
                has_fused_experts(self.root)
            with self.assertRaises(ValueError):
                validate_tensors(self.root, self.spec, {"num_hidden_layers": 2})


class GradBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def spec(self, payload):
        return {
            "version": {
                "id": str(uuid.uuid4()),
                "adapter": {
                    "rank": 2,
                    "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "source": GRAD_SOURCE,
                },
            },
            "download": {"url": "https://bucket.s3.amazonaws.com/adapter"},
        }

    def materialize(self, payload, spec=None):
        def fetch(_spec, path, _hosts):
            path.write_bytes(payload)

        return materialize(
            spec or self.spec(payload),
            self.root,
            1024 * 1024,
            set(),
            {"num_hidden_layers": 2},
            fetch=fetch,
        )

    def test_a_grad_bundle_loads_and_drops_its_envelope(self):
        payload = grad_bundle(adapter_files(), extra={"eval_report.json": b"{}"}, manifest={
            "eval_report_sha256": hashlib.sha256(b"{}").hexdigest()
        })

        spec = self.spec(payload)
        directory, _disk, _tensors = self.materialize(payload, spec)

        self.assertEqual(
            {path.name for path in directory.iterdir()},
            {"archive.tar.gz", "adapter_config.json", "adapter_model.safetensors", ".verified.json"},
        )
        again, _disk, _tensors = self.materialize(b"", spec)
        self.assertEqual(again, directory)

    def test_grad_bundles_must_match_their_manifest(self):
        files = adapter_files()
        cases = [
            grad_bundle(files, manifest={"files": {"adapter_config.json": "0" * 64}}),
            grad_bundle(files, manifest={"format_version": 2}),
            grad_bundle(files, adapter_format="cartridge"),
            grad_bundle(files, manifest={"kind": "checkpoint"}),
            grad_bundle(files, extra={"eval_report.json": b"{}"}),
            grad_bundle(files, extra={"trainer_state/optimizer.pt": b"x"}),
            grad_bundle({"adapter_config.json": files["adapter_config.json"]}),
        ]
        for payload in cases:
            with self.assertRaises(ValueError):
                self.materialize(payload)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_a_legacy_archive_needs_no_manifest_and_a_grad_bundle_does(self):
        output = self.root / "out"
        output.mkdir()
        legacy = self.root / "legacy.tar.gz"
        legacy.write_bytes(archive())
        with self.assertRaisesRegex(ValueError, "Missing adapter files"):
            extract(legacy, output, 1024 * 1024, grad=True)



if __name__ == "__main__":
    unittest.main()