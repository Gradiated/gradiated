import hashlib
import http.client
import http.server
import threading
import io
import json
import math
import struct
import tempfile
import unittest
import uuid
import urllib.error
from pathlib import Path
from unittest import mock

from artifacts import (
    download,
    extract,
    file_hash,
    materialize,
    has_fused_experts,
    strict_json,
    validate_tensors,
)
from fixtures import archive


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
        with mock.patch("artifacts.remaining", side_effect=[1, 1, TimeoutError]):
            with self.assertRaises(TimeoutError):
                extract(archive_path, output, 1024 * 1024, deadline=1)
        with mock.patch("artifacts.remaining", side_effect=[1, TimeoutError]):
            with self.assertRaises(TimeoutError):
                file_hash(archive_path, deadline=1)

    def test_recovered_cache_timeout_keeps_existing_files(self):
        from fixtures import grant, settings

        spec = grant(self.payload)
        fetch = lambda spec, path, hosts: path.write_bytes(self.payload)
        path, *_ = materialize(
            spec, self.root, 1024 * 1024, set(), settings()["model_config"], fetch=fetch
        )
        with mock.patch("artifacts.file_hash", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
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
        for payload in (
            self.payload[:-1],
            self.payload + b"extra",
            b"x" * len(self.payload),
        ):
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
                clock[0] += 11
                return super().read1(min(size, 8))

        first.getresponse.return_value = SlowResponse(payload)
        second.getresponse.return_value = Response(payload)
        with (
            mock.patch("http.client.HTTPSConnection", side_effect=[first, second]) as connect,
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
            self.assertLogs("artifacts", level="WARNING") as logs,
        ):
            download(self.spec, self.root / "retry", {"bucket.s3.amazonaws.com"}, 60)
        self.assertEqual((self.root / "retry").read_bytes(), payload)
        self.assertEqual(connect.call_count, 2)
        first.close.assert_called_once()
        second.close.assert_called_once()
        self.assertEqual(second.request.call_args.kwargs["headers"], {"Range": f"bytes=8-{len(payload) - 1}"})
        self.assertEqual(clock[0], 22)
        self.assertIn('"event": "lora_download_retry"', logs.output[0])
        self.assertNotIn("bucket.s3.amazonaws.com", logs.output[0])

    def test_slow_transfer_that_can_finish_is_not_restarted(self):
        clock = [0.0]
        payload = self.payload
        connection = mock.Mock()

        class SteadyResponse(Response):
            def isclosed(self):
                return self.tell() == len(payload)

            def read1(self, size):
                clock[0] += 21
                return super().read1((len(payload) + 1) // 2)

        connection.getresponse.return_value = SteadyResponse(payload)
        with (
            mock.patch("http.client.HTTPSConnection", return_value=connection) as connect,
            mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
        ):
            download(self.spec, self.root / "steady", {"bucket.s3.amazonaws.com"}, 60)
        self.assertEqual((self.root / "steady").read_bytes(), payload)
        self.assertEqual(clock[0], 42)
        connect.assert_called_once()

    def test_slow_transfer_resumes_partial_bytes_with_a_valid_range(self):
        clock = [0.0]
        payload = self.payload

        class SlowResponse(Response):
            def read1(self, size):
                clock[0] += 11
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
        self.assertEqual(second.request.call_args.kwargs["headers"], {"Range": f"bytes=8-{len(payload) - 1}"})

    def test_resumed_transfer_rejects_wrong_ranges_and_corrupt_bytes(self):
        payload = self.payload
        for header, body in (
            (None, payload[8:]),
            (f"bytes 0-{len(payload) - 1}/{len(payload)}", payload[8:]),
            (f"bytes 8-{len(payload) - 2}/{len(payload)}", payload[8:]),
            (f"bytes 8-{len(payload) - 1}/{len(payload) + 1}", payload[8:]),
            (f"bytes 8-{len(payload) - 1}/{len(payload)}", payload[8:-1] + bytes([payload[-1] ^ 1])),
        ):
            with self.subTest(header=header):
                clock = [0.0]

                class SlowResponse(Response):
                    def read1(self, size):
                        clock[0] += 11
                        return super().read1(min(size, 8))

                class PartialResponse(Response):
                    status = 206

                    def getheader(self, name):
                        return header

                first, second = mock.Mock(), mock.Mock()
                first.getresponse.return_value = SlowResponse(payload)
                second.getresponse.return_value = PartialResponse(body)
                with (
                    mock.patch("http.client.HTTPSConnection", side_effect=[first, second]) as connect,
                    mock.patch("artifacts.time.monotonic", side_effect=lambda: clock[0]),
                    self.assertLogs("artifacts", level="WARNING"),
                    self.assertRaises(ValueError),
                ):
                    download(self.spec, self.root / "invalid-range", {"bucket.s3.amazonaws.com"}, 60)
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
        barrier = threading.Barrier(3)

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
            self.assertCountEqual(
                requests,
                ["bytes=0-4194303", "bytes=4194304-8388607", f"bytes=8388608-{len(payload) - 1}"],
            )
            self.assertEqual({path.name for path in self.root.iterdir()}, {"parallel"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_large_download_rejects_invalid_ranges_and_missing_or_corrupt_bytes(self):
        payload = hashlib.shake_256(b"invalid-range").digest(8 * 1024 * 1024 + 9)
        self.spec["version"]["adapter"].update(
            size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()
        )
        for defect in ("ignored", "offset", "short", "oversized", "corrupt"):
            with self.subTest(defect=defect):
                connections = []

                def connect(*_args, **_kwargs):
                    connection = mock.Mock()
                    connections.append(connection)
                    bounds = []

                    def request(_method, _path, headers):
                        bounds.extend(map(int, headers["Range"].removeprefix("bytes=").split("-")))

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
                    self.assertRaises(ValueError),
                ):
                    download(self.spec, self.root / "invalid-part", {"bucket.s3.amazonaws.com"})
                self.assertEqual(len(connections), 3)
                for connection in connections:
                    connection.request.assert_called_once()
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
            mock.patch("http.client.HTTPSConnection", side_effect=[first, second]) as connect,
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
                mock.patch("http.client.HTTPSConnection", return_value=connection) as connect,
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

    def test_header_length_is_bounded_before_reading(self):
        self.write_experts(True)
        weights = self.root / "adapter_model.safetensors"
        for prefix in (b"", struct.pack("<Q", 100_000_001)):
            weights.write_bytes(prefix)
            with self.assertRaises(ValueError):
                has_fused_experts(self.root)
            with self.assertRaises(ValueError):
                validate_tensors(self.root, self.spec, {"num_hidden_layers": 2})


if __name__ == "__main__":
    unittest.main()
