import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
import subprocess
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from session_staging import (  # noqa: E402
    CheckpointFile,
    RemoteCheckpointState,
    build_remote_state_command,
    checkpoint_files,
    initialize_remote_staging,
    plan_transfer,
    query_remote_state,
    transfer_checkpoint,
    transfer_timeout_seconds,
    validate_local_files_cached,
)


class NebiusSessionStagingTests(unittest.TestCase):
    def make_checkpoint(self, root: Path) -> None:
        (root / "config.json").write_text("{}\n")
        (root / "model-00001.safetensors").write_bytes(b"a" * 10)
        digest = hashlib.sha256(b"a" * 10).hexdigest()
        (root / "model-files.sha256").write_text(f"{digest}  model-00001.safetensors\n")
        (root / "model-files-manifest.json").write_text(json.dumps({"files": []}) + "\n")

    def test_timeout_scales_with_checkpoint_size(self):
        awq = transfer_timeout_seconds(20_170_199_928)
        bf16 = transfer_timeout_seconds(62_444_175_504)
        self.assertEqual(awq, 1189)
        self.assertEqual(bf16, 3303)
        self.assertGreater(bf16, awq)

    def test_checkpoint_inventory_includes_runtime_metadata_and_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkpoint(root)
            rows = checkpoint_files(root)
        self.assertEqual(
            {row.path for row in rows},
            {"config.json", "model-00001.safetensors", "model-files.sha256", "model-files-manifest.json"},
        )

    def test_local_validation_hashes_once_then_uses_content_bound_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b"checkpoint"
            path = root / "model"
            path.write_bytes(payload)
            (root / "model-files.sha256").write_text(
                f"{hashlib.sha256(payload).hexdigest()}  model\n"
            )
            rows = [{"path": "model", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}]
            self.assertFalse(validate_local_files_cached(root, rows))
            self.assertTrue(validate_local_files_cached(root, rows))
            self.assertNotIn(".campaign-local-integrity-v1.json", {row.path for row in checkpoint_files(root)})
            path.write_bytes(b"checkpoinu")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                validate_local_files_cached(root, rows)

    def test_checksum_manifest_stages_required_local_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkpoint(root)
            marker = root / ".campaign-local-integrity-v1.json"
            marker.write_text("{}\n")
            digest = hashlib.sha256(marker.read_bytes()).hexdigest()
            with (root / "model-files.sha256").open("a") as handle:
                handle.write(f"{digest}  {marker.name}\n")

            rows = checkpoint_files(root)
            self.assertIn(marker.name, {row.path for row in rows})

    def test_plan_reuses_complete_files_and_replaces_only_truncated_files(self):
        files = (CheckpointFile("a", 10), CheckpointFile("b", 20), CheckpointFile("c", 30))
        remote = RemoteCheckpointState({"a": 10, "b": 19}, False)
        plan = plan_transfer(files, remote)
        self.assertEqual([row.path for row in plan.files], ["b", "c"])
        self.assertEqual(plan.reusable_bytes, 10)
        self.assertEqual(plan.transfer_bytes, 50)

    def test_matching_marker_and_sizes_is_zero_byte_cache_hit(self):
        files = (CheckpointFile("a", 10), CheckpointFile("b", 20))
        plan = plan_transfer(files, RemoteCheckpointState({"a": 10, "b": 20}, True))
        self.assertEqual(plan.files, ())
        self.assertEqual(plan.transfer_bytes, 0)
        self.assertTrue(plan.marker_manifest_match)

    def test_remote_query_is_grouped_into_one_content_bound_command(self):
        command = build_remote_state_command(
            "/workspace/model-awq",
            (CheckpointFile("model", 10),),
            "a" * 64,
        )
        self.assertEqual(command[:2], ["python3", "-c"])
        self.assertIn("marker_manifest_match", command[2])
        self.assertIn("staging_manifest_match", command[2])
        self.assertEqual(command[3], "/workspace/model-awq")
        self.assertEqual(command[5], "a" * 64)

    def test_remote_query_command_reports_sizes_and_marker_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "model").write_bytes(b"1234")
            manifest_sha = "a" * 64
            (root / ".campaign-integrity-v1").write_text(f"manifest_sha256={manifest_sha}\n")
            command = build_remote_state_command(
                str(root),
                (CheckpointFile("model", 4), CheckpointFile("missing", 2)),
                manifest_sha,
            )
            result = subprocess.run(command, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["sizes"], {"model": 4})
        self.assertTrue(payload["marker_manifest_match"])
        self.assertFalse(payload["staging_manifest_match"])

    def test_remote_workspace_parent_is_owned_before_state_query(self):
        response = CompletedProcess(
            [],
            0,
            json.dumps(
                {
                    "sizes": {},
                    "marker_manifest_match": False,
                    "staging_manifest_match": False,
                }
            ),
            "",
        )
        with patch("session_staging.run_ssh", side_effect=[CompletedProcess([], 0, "", ""), response]) as run:
            query_remote_state(
                "192.0.2.1",
                Path("/tmp/key"),
                "/home/glmrunner/gemma/model",
                (CheckpointFile("model", 4),),
                "a" * 64,
            )

        self.assertIn(
            "/home/glmrunner/gemma /home/glmrunner/gemma/model",
            run.call_args_list[0].args[2],
        )

    def test_remote_staging_initialization_owns_workspace_parent(self):
        with patch(
            "session_staging.run_ssh",
            return_value=CompletedProcess([], 0, "", ""),
        ) as run:
            initialize_remote_staging(
                "192.0.2.1",
                Path("/tmp/key"),
                "/workspace/model",
                "a" * 64,
            )

        self.assertIn(
            "install -d -o glmrunner -g glmrunner /workspace",
            run.call_args.args[2],
        )

    def test_transfer_retries_only_missing_files_and_keeps_completed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkpoint(root)
            rows = checkpoint_files(root)
            states = iter(
                [
                    RemoteCheckpointState({}, False, True),
                    RemoteCheckpointState({rows[0].path: rows[0].bytes}, False, True),
                    RemoteCheckpointState({row.path: row.bytes for row in rows}, False, True),
                ]
            )
            commands = []

            def state_query(*_args):
                return next(states)

            def command_runner(command, **_kwargs):
                commands.append(command)
                return CompletedProcess(command, 1 if len(commands) == 1 else 0, "", "interrupted")

            result = transfer_checkpoint(
                "192.0.2.1",
                Path("/tmp/key"),
                root,
                "/workspace/model",
                timeout_seconds=60,
                state_query=state_query,
                command_runner=command_runner,
            )
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(commands), 2)
        first_sources = set(commands[0][commands[0].index("/tmp/key") + 7 : -1])
        second_sources = set(commands[1][commands[1].index("/tmp/key") + 7 : -1])
        self.assertGreater(len(first_sources), len(second_sources))

    def test_different_checkpoint_contract_resets_same_sized_remote_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkpoint(root)
            rows = checkpoint_files(root)
            states = iter(
                [
                    RemoteCheckpointState({row.path: row.bytes for row in rows}, False, False),
                    RemoteCheckpointState({row.path: row.bytes for row in rows}, False, True),
                ]
            )
            initialized = []
            commands = []

            def state_query(*_args):
                return next(states)

            def initializer(*_args):
                initialized.append(True)
                return RemoteCheckpointState({}, False, True)

            def command_runner(command, **_kwargs):
                commands.append(command)
                return CompletedProcess(command, 0, "", "")

            result = transfer_checkpoint(
                "192.0.2.1",
                Path("/tmp/key"),
                root,
                "/workspace/model",
                state_query=state_query,
                staging_initializer=initializer,
                command_runner=command_runner,
            )
        self.assertEqual(initialized, [True])
        self.assertEqual(result.reusable_bytes, 0)
        self.assertEqual(result.files_scheduled, len(rows))
        self.assertEqual(len(commands), 1)

    def test_warm_hit_uses_one_state_query_and_no_scp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_checkpoint(root)
            rows = checkpoint_files(root)
            calls = []

            def state_query(*_args):
                calls.append("state")
                return RemoteCheckpointState({row.path: row.bytes for row in rows}, True)

            result = transfer_checkpoint(
                "192.0.2.1",
                Path("/tmp/key"),
                root,
                "/workspace/model",
                state_query=state_query,
                command_runner=lambda *_args, **_kwargs: self.fail("warm hit must not transfer"),
            )
        self.assertEqual(calls, ["state"])
        self.assertEqual(result.attempts, 0)
        self.assertEqual(result.scheduled_bytes, 0)


if __name__ == "__main__":
    unittest.main()
