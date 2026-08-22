import datetime
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest


TOOL = pathlib.Path(__file__).parents[1] / "tools" / "repair-handshake"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        check=False,
        capture_output=True,
        text=True,
    )


class RepairHandshakeTests(unittest.TestCase):
    def test_repair_ids_isolate_repeated_episodes_under_one_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            deadline = (
                datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5)
            ).isoformat()

            for repair_id in ("docker-permission", "sm90a-header"):
                marked = run(
                    "ready",
                    "--root",
                    str(root),
                    "--repair-id",
                    repair_id,
                    "--deadline",
                    deadline,
                    "--failure-kind",
                    "integration",
                    "--diagnostic",
                    f"diagnostics/{repair_id}.json",
                    "--retry-scope",
                    "failed operation only",
                )
                self.assertEqual(marked.returncode, 0, marked.stderr)
                requested = run(
                    "request",
                    "--root",
                    str(root),
                    "--repair-id",
                    repair_id,
                    "--patch-artifact",
                    f"patches/{repair_id}.diff",
                )
                self.assertEqual(requested.returncode, 0, requested.stderr)

            first_root = root / ".repair-handshakes" / "docker-permission"
            second_root = root / ".repair-handshakes" / "sm90a-header"
            self.assertTrue((first_root / "REPAIR_REQUEST.json").exists())
            self.assertTrue((second_root / "REPAIR_REQUEST.json").exists())
            self.assertNotEqual(
                (first_root / "REPAIR_READY.json").read_text(),
                (second_root / "REPAIR_READY.json").read_text(),
            )
            status = run(
                "status",
                "--root",
                str(root),
                "--repair-id",
                "sm90a-header",
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["state"], "requested")

    def test_repair_id_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rejected = run(
                "status",
                "--root",
                temporary,
                "--repair-id",
                "../escape",
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("repair id must be", rejected.stderr)

    def test_ready_request_and_status_are_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            deadline = (
                datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5)
            ).isoformat()
            marked = run(
                "ready",
                "--root",
                str(root),
                "--deadline",
                deadline,
                "--failure-kind",
                "integration",
                "--diagnostic",
                "diagnostics/failure.json",
                "--retry-scope",
                "candidate endpoint only",
            )
            self.assertEqual(marked.returncode, 0, marked.stderr)
            ready = json.loads((root / "REPAIR_READY.json").read_text())
            expected_hash = hashlib.sha256(
                (json.dumps(ready, indent=2, sort_keys=True) + "\n").encode()
            ).hexdigest()
            self.assertEqual(json.loads(marked.stdout)["ready_sha256"], expected_hash)

            waiting = run("status", "--root", str(root))
            self.assertEqual(waiting.returncode, 3)
            self.assertEqual(json.loads(waiting.stdout)["state"], "waiting")

            requested = run(
                "request",
                "--root",
                str(root),
                "--patch-artifact",
                "patches/fix.diff",
            )
            self.assertEqual(requested.returncode, 0, requested.stderr)
            request = json.loads((root / "REPAIR_REQUEST.json").read_text())
            self.assertEqual(request["ready_sha256"], expected_hash)
            self.assertEqual(request["retry_scope"], "candidate endpoint only")
            self.assertEqual(request["patch_artifact"], "patches/fix.diff")
            self.assertEqual(request["packet_path"], request["patch_artifact"])

            status = run("status", "--root", str(root))
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["state"], "requested")

    def test_request_after_deadline_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            deadline = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)
            value = {
                "schema_version": 1,
                "state": "repair_ready",
                "created_at_utc": deadline.isoformat(),
                "absolute_repair_deadline_utc": deadline.isoformat(),
                "repair_deadline_epoch": deadline.timestamp(),
                "failure_kind": "integration",
                "diagnostic": "failure.json",
                "retry_scope": "candidate only",
            }
            (root / "REPAIR_READY.json").write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n"
            )
            requested = run("request", "--root", str(root))
            self.assertEqual(requested.returncode, 2)
            self.assertIn("repair_deadline_passed", requested.stderr)
            self.assertFalse((root / "REPAIR_REQUEST.json").exists())

    def test_ready_is_idempotent_but_cannot_change_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            deadline = (
                datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5)
            ).isoformat()
            common = (
                "ready",
                "--root",
                str(root),
                "--deadline",
                deadline,
                "--failure-kind",
                "consumer",
                "--diagnostic",
                "failure.json",
                "--retry-scope",
            )
            first = run(*common, "consumer only")
            second = run(*common, "consumer only")
            changed = run(*common, "whole experiment")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertTrue(json.loads(second.stdout)["idempotent"])
            self.assertEqual(changed.returncode, 2)
            self.assertIn("different_repair_ready_already_exists", changed.stderr)

    def test_request_cannot_broaden_ready_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            deadline = (
                datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5)
            ).isoformat()
            marked = run(
                "ready",
                "--root",
                str(root),
                "--deadline",
                deadline,
                "--failure-kind",
                "consumer",
                "--diagnostic",
                "failure.json",
                "--retry-scope",
                "consumer:resume",
            )
            self.assertEqual(marked.returncode, 0, marked.stderr)

            broadened = run(
                "request",
                "--root",
                str(root),
                "--patch-artifact",
                "patches/fix.json",
                "--retry-scope",
                "source_stage",
            )
            self.assertEqual(broadened.returncode, 2)
            self.assertIn("repair_request_scope_mismatch", broadened.stderr)
            self.assertFalse((root / "REPAIR_REQUEST.json").exists())

            exact = run(
                "request",
                "--root",
                str(root),
                "--patch-artifact",
                "patches/fix.json",
                "--retry-scope",
                "consumer:resume",
            )
            self.assertEqual(exact.returncode, 0, exact.stderr)
            request = json.loads((root / "REPAIR_REQUEST.json").read_text())
            self.assertEqual(request["retry_scope"], "consumer:resume")

    def test_wait_keeps_owner_blocked_until_hash_bound_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            deadline = (
                datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=5)
            ).isoformat()
            marked = run(
                "ready",
                "--root",
                str(root),
                "--deadline",
                deadline,
                "--failure-kind",
                "consumer",
                "--diagnostic",
                "failure.json",
                "--retry-scope",
                "consumer only",
            )
            self.assertEqual(marked.returncode, 0, marked.stderr)

            waiter = subprocess.Popen(
                [
                    sys.executable,
                    str(TOOL),
                    "wait",
                    "--root",
                    str(root),
                    "--deadline",
                    deadline,
                    "--poll-seconds",
                    "0.01",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.05)
            self.assertIsNone(waiter.poll())

            requested = run(
                "request",
                "--root",
                str(root),
                "--patch-artifact",
                "patches/fix.diff",
            )
            self.assertEqual(requested.returncode, 0, requested.stderr)
            stdout, stderr = waiter.communicate(timeout=2)
            self.assertEqual(waiter.returncode, 0, stderr)
            self.assertEqual(json.loads(stdout)["state"], "requested")

    def test_wait_rejects_deadline_that_differs_from_ready_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            deadline = (
                datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5)
            )
            marked = run(
                "ready",
                "--root",
                str(root),
                "--deadline",
                deadline.isoformat(),
                "--failure-kind",
                "consumer",
                "--diagnostic",
                "failure.json",
                "--retry-scope",
                "consumer only",
            )
            self.assertEqual(marked.returncode, 0, marked.stderr)

            waited = run(
                "wait",
                "--root",
                str(root),
                "--deadline",
                (deadline + datetime.timedelta(seconds=1)).isoformat(),
            )

            self.assertEqual(waited.returncode, 2)
            self.assertIn("repair_wait_deadline_mismatch", waited.stderr)

    def test_wait_exits_at_absolute_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            deadline = (
                datetime.datetime.now(datetime.UTC)
                + datetime.timedelta(milliseconds=50)
            ).isoformat()
            marked = run(
                "ready",
                "--root",
                str(root),
                "--deadline",
                deadline,
                "--failure-kind",
                "consumer",
                "--diagnostic",
                "failure.json",
                "--retry-scope",
                "consumer only",
            )
            self.assertEqual(marked.returncode, 0, marked.stderr)
            waited = run(
                "wait",
                "--root",
                str(root),
                "--poll-seconds",
                "0.01",
            )
            self.assertEqual(waited.returncode, 3, waited.stderr)
            self.assertEqual(json.loads(waited.stdout)["state"], "expired")

    def test_hold_publishes_ready_and_blocks_until_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            deadline = (
                datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=5)
            ).isoformat()
            holder = subprocess.Popen(
                [
                    sys.executable,
                    str(TOOL),
                    "hold",
                    "--root",
                    str(root),
                    "--deadline",
                    deadline,
                    "--failure-kind",
                    "integration",
                    "--diagnostic",
                    "diagnostics/missing-command.json",
                    "--retry-scope",
                    "checkpoint stage only",
                    "--poll-seconds",
                    "0.01",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            ready = root / "REPAIR_READY.json"
            for _ in range(100):
                if ready.exists():
                    break
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            self.assertIsNone(holder.poll())

            requested = run(
                "request",
                "--root",
                str(root),
                "--patch-artifact",
                "patches/checkpoint-stage.diff",
            )
            self.assertEqual(requested.returncode, 0, requested.stderr)
            stdout, stderr = holder.communicate(timeout=2)
            self.assertEqual(holder.returncode, 0, stderr)
            result = json.loads(stdout)
            self.assertEqual(result["state"], "requested")
            self.assertEqual(
                result["request"]["retry_scope"], "checkpoint stage only"
            )


if __name__ == "__main__":
    unittest.main()
