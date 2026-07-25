from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from grad_research.science_tools.common import (
    ScienceToolError,
    artifact_identity,
    read_jsonl,
    run_command,
    write_json_atomic,
    write_jsonl_atomic,
)


class ScienceToolCommonTest(unittest.TestCase):
    def test_atomic_json_and_jsonl_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = write_json_atomic(root / "nested" / "value.json", {"b": 2, "a": 1})
            rows = write_jsonl_atomic(root / "rows.jsonl", [{"n": 1}, {"n": 2}])

            self.assertEqual(json.loads(document.read_text()), {"a": 1, "b": 2})
            self.assertEqual(read_jsonl(rows), [{"n": 1}, {"n": 2}])
            identity = artifact_identity(rows)
            self.assertEqual(identity["size_bytes"], rows.stat().st_size)
            self.assertEqual(len(identity["sha256"]), 64)

    def test_read_jsonl_rejects_non_object_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            path.write_text("[1, 2, 3]\n")
            with self.assertRaisesRegex(ScienceToolError, "must contain a JSON object"):
                read_jsonl(path)

    def test_run_command_retains_logs_and_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_command(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('out'); print('err', file=sys.stderr)",
                ],
                output_dir=directory,
                name="fixture",
            )

            self.assertEqual(result["returncode"], 0)
            self.assertEqual(Path(result["stdout"]["path"]).read_text(), "out\n")
            self.assertEqual(Path(result["stderr"]["path"]).read_text(), "err\n")

    def test_run_command_returns_typed_timeout_and_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_command(
                [
                    sys.executable,
                    "-c",
                    "import time; print('started', flush=True); time.sleep(30)",
                    "--api-key",
                    "do-not-record",
                    "https://user:password@example.com/path?signed=secret",
                ],
                output_dir=directory,
                name="timeout",
                timeout_seconds=0.05,
            )

            self.assertTrue(result["timed_out"])
            self.assertNotEqual(result["returncode"], 0)
            self.assertIn("started", Path(result["stdout"]["path"]).read_text())
            encoded = json.dumps(result)
            self.assertNotIn("do-not-record", encoded)
            self.assertNotIn("signed=secret", encoded)

    def test_run_command_redacts_sensitive_header_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_command(
                [
                    sys.executable,
                    "-c",
                    "pass",
                    "-H",
                    "Authorization: Bearer sk-do-not-record",
                ],
                output_dir=directory,
                name="header",
            )

            encoded = json.dumps(result)
            self.assertNotIn("sk-do-not-record", encoded)
            self.assertIn("<redacted-header>", encoded)

    def test_run_command_redacts_joined_headers_and_user_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_command(
                [
                    sys.executable,
                    "-c",
                    "pass",
                    "-HAuthorization: Bearer sk-joined-secret",
                    "--header=Cookie: session=cookie-secret",
                    "--user",
                    "researcher:user-secret",
                    "--proxy-user=proxy:proxy-secret",
                    "-uinline:inline-secret",
                    "-Uproxy-inline:proxy-inline-secret",
                    "--oauth2-bearer=oauth-secret",
                ],
                output_dir=directory,
                name="joined-credentials",
            )

            encoded = json.dumps(result)
            for secret in (
                "sk-joined-secret",
                "cookie-secret",
                "user-secret",
                "proxy-secret",
                "inline-secret",
                "proxy-inline-secret",
                "oauth-secret",
            ):
                self.assertNotIn(secret, encoded)
            self.assertIn("<redacted-header>", encoded)
            self.assertIn("<redacted>", encoded)


if __name__ == "__main__":
    unittest.main()
