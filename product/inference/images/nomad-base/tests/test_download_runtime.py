import importlib.util
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

source = Path(__file__).parents[1] / "download-runtime.py"
if not source.exists():
    source = Path("/opt/gradiated/bin/download-runtime")
spec = importlib.util.spec_from_loader(
    "download_runtime", SourceFileLoader("download_runtime", str(source))
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.archive = Path(self.directory.name) / "runtime.tar.gz"
        self.payload = bytes(range(256)) + b"x"
        self.calls = []
        self.lock = threading.Lock()
        self.environment = patch.dict(
            os.environ,
            {
                "AWS_ACCESS_KEY_ID": "synthetic-key",
                "AWS_SECRET_ACCESS_KEY": "synthetic-secret",
                "AWS_SESSION_TOKEN": "synthetic-session",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def fake_curl(self, args, *, input, stdout, timeout, check=False):
        self.assertNotIn("synthetic-secret", " ".join(args))
        self.assertIn(b'user = "synthetic-key:synthetic-secret"', input)
        self.assertIn(b"x-amz-security-token: synthetic-session", input)
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 1200)
        if "--head" in args:
            return subprocess.CompletedProcess(args, 0, str(len(self.payload)).encode())
        start, end = map(int, args[args.index("--range") + 1].split("-"))
        self.assertEqual(int(args[args.index("--max-filesize") + 1]), end - start + 1)
        with self.lock:
            self.calls.append((start, end))
        stdout.write(self.payload[start : end + 1])
        return subprocess.CompletedProcess(args, 0)

    def run_download(self, curl=None):
        with patch.object(module.subprocess, "run", side_effect=curl or self.fake_curl):
            module.download("https://test.invalid/archive", self.archive)

    def test_all_eight_ranges_write_one_complete_archive(self):
        self.run_download()
        self.assertEqual(self.archive.read_bytes(), self.payload)
        self.assertEqual(
            sorted(self.calls), [(i, min(i + 32, 256)) for i in range(0, 257, 33)]
        )
        self.assertEqual(list(self.archive.parent.iterdir()), [self.archive])

    def test_size_probe_retries_transient_failures_before_starting_ranges(self):
        codes = iter((7, 28, 56, 18, 0))
        probes = []

        def curl(args, **kwargs):
            if "--head" in args:
                code = next(codes)
                probes.append(code)
                if code:
                    self.assertFalse(self.archive.exists())
                    return subprocess.CompletedProcess(args, code, b"")
            return self.fake_curl(args, **kwargs)

        with patch.object(module.time, "sleep"):
            self.run_download(curl)
        self.assertEqual(probes, [7, 28, 56, 18, 0])
        self.assertEqual(self.archive.read_bytes(), self.payload)

    def test_size_probe_denial_is_not_retried(self):
        with (
            patch.object(
                module.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 22, b""),
            ) as curl,
            self.assertRaisesRegex(RuntimeError, "bundle size"),
        ):
            module.download("https://test.invalid/archive", self.archive)
        self.assertEqual(curl.call_count, 1)
        self.assertFalse(self.archive.exists())

    def test_size_probe_retries_share_the_original_deadline(self):
        now = [0]

        def curl(args, **kwargs):
            now[0] += 400
            return subprocess.CompletedProcess(args, 28, b"")

        with (
            patch.object(module.time, "monotonic", side_effect=lambda: now[0]),
            patch.object(module.time, "sleep"),
            self.assertRaisesRegex(TimeoutError, "deadline"),
        ):
            self.run_download(curl)
        self.assertFalse(self.archive.exists())

    def test_timeout_resumes_each_range_from_written_prefix(self):
        barrier = threading.Barrier(8, timeout=5)
        starts = set(range(0, 257, 33))

        def curl(args, **kwargs):
            if "--head" in args:
                return self.fake_curl(args, **kwargs)
            start, end = map(int, args[args.index("--range") + 1].split("-"))
            del end
            if start in starts:
                barrier.wait()
                kwargs["stdout"].write(self.payload[start : start + 2])
                return subprocess.CompletedProcess(args, 28)
            return self.fake_curl(args, **kwargs)

        self.run_download(curl)
        self.assertEqual(self.archive.read_bytes(), self.payload)
        self.assertEqual(
            sorted(start for start, _ in self.calls), [i + 2 for i in starts]
        )

    def test_range_connection_failure_retries_without_advancing_the_offset(self):
        attempted = set()

        def curl(args, **kwargs):
            if "--head" in args:
                return self.fake_curl(args, **kwargs)
            value = args[args.index("--range") + 1]
            if value not in attempted:
                attempted.add(value)
                return subprocess.CompletedProcess(args, 7)
            return self.fake_curl(args, **kwargs)

        self.run_download(curl)
        self.assertEqual(len(attempted), 8)
        self.assertEqual(self.archive.read_bytes(), self.payload)

    def test_child_process_advances_the_shared_file_position(self):
        def curl(args, **kwargs):
            if "--head" in args:
                return self.fake_curl(args, **kwargs)
            start, end = map(int, args[args.index("--range") + 1].split("-"))
            # Bypass the patched run function to exercise the inherited file descriptor.
            child = subprocess.Popen(
                [
                    "python3",
                    "-c",
                    "import os,sys; os.write(1, bytes.fromhex(sys.argv[1]))",
                    self.payload[start : end + 1].hex(),
                ],
                stdout=kwargs["stdout"],
            )
            return subprocess.CompletedProcess(args, child.wait(timeout=5))

        self.run_download(curl)
        self.assertEqual(self.archive.read_bytes(), self.payload)

    def test_real_http_disconnect_resumes_into_the_shared_archive(self):
        payload = self.payload
        requests = []
        dropped = set()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_HEAD(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()

            def do_GET(self):
                start, end = map(
                    int, self.headers["Range"].removeprefix("bytes=").split("-")
                )
                requests.append((start, end))
                self.send_response(206)
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
                self.end_headers()
                if end not in dropped:
                    dropped.add(end)
                    self.wfile.write(payload[start : start + 2])
                    self.close_connection = True
                else:
                    self.wfile.write(payload[start : end + 1])

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            module.download(
                f"http://127.0.0.1:{server.server_port}/archive", self.archive
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(self.archive.read_bytes(), payload)
        self.assertEqual(len(requests), 16)
        self.assertEqual(
            sorted(start for start, _ in requests),
            sorted([i + j for i in range(0, 257, 33) for j in (0, 2)]),
        )

    def test_access_denied_is_not_retried(self):
        def curl(args, **kwargs):
            if "--head" in args:
                return self.fake_curl(args, **kwargs)
            with self.lock:
                self.calls.append(args)
            return subprocess.CompletedProcess(args, 22)

        with self.assertRaisesRegex(RuntimeError, "curl 22"):
            self.run_download(curl)
        self.assertLessEqual(len(self.calls), 8)

    def test_premature_success_is_rejected(self):
        def curl(args, **kwargs):
            if "--head" in args:
                return self.fake_curl(args, **kwargs)
            return subprocess.CompletedProcess(args, 0)

        with self.assertRaisesRegex(RuntimeError, "truncated"):
            self.run_download(curl)

    def test_response_larger_than_requested_range_is_rejected(self):
        def curl(args, **kwargs):
            if "--head" in args:
                return self.fake_curl(args, **kwargs)
            kwargs["stdout"].write(b"x" * 1000)
            return subprocess.CompletedProcess(args, 0)

        with self.assertRaisesRegex(RuntimeError, "transfer failed"):
            self.run_download(curl)

    def test_invalid_size_does_not_create_an_archive(self):
        for body in (b"", b"0", b"-1", b"invalid"):
            with (
                self.subTest(body=body),
                patch.object(
                    module.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0, body),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "bundle size"):
                    module.download("https://test.invalid/archive", self.archive)
                self.assertFalse(self.archive.exists())

    def test_deadline_bounds_every_retry(self):
        now = [0]

        def curl(args, **kwargs):
            if "--head" in args:
                return self.fake_curl(args, **kwargs)
            with self.lock:
                now[0] += 400
            return subprocess.CompletedProcess(args, 28)

        with (
            patch.object(module.time, "monotonic", side_effect=lambda: now[0]),
            self.assertRaisesRegex(TimeoutError, "deadline"),
        ):
            self.run_download(curl)


if __name__ == "__main__":
    unittest.main()
