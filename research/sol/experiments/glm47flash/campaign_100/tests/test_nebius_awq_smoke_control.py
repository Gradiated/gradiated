import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from awq_smoke_control import (  # noqa: E402
    ABSOLUTE_TIMEOUT_SECONDS,
    DISK_HOURLY_RATE_USD,
    HOURLY_RATE_USD,
    IMAGE,
    MODEL_REVISION,
    MODEL_SHARD_COUNT,
    MODEL_WEIGHT_BYTES,
    build_container_command,
    build_model_transfer_command,
    validate_local_model,
)


class NebiusAwqSmokeControlTests(unittest.TestCase):
    def test_remote_smoke_extends_scheduler_watchdog_beyond_cold_jit(self):
        script = (ROOT / "nebius" / "remote_awq_smoke.sh").read_text()
        self.assertIn("--watchdog-timeout 1800", script)

    def test_contract_is_bounded_and_pinned(self):
        self.assertEqual(MODEL_REVISION, "ab31d120fbe79988fe2a0259993cf3c222aa8881")
        self.assertEqual(MODEL_SHARD_COUNT, 4)
        self.assertEqual(MODEL_WEIGHT_BYTES, 20_170_199_928)
        self.assertEqual(ABSOLUTE_TIMEOUT_SECONDS, 4500)
        self.assertEqual(HOURLY_RATE_USD, 0.8484)
        self.assertEqual(DISK_HOURLY_RATE_USD, 0.0097222)
        self.assertIn("@sha256:", IMAGE)
        self.assertLess((HOURLY_RATE_USD + DISK_HOURLY_RATE_USD) * ABSOLUTE_TIMEOUT_SECONDS / 3600, 1.1)

    def test_container_uses_local_model_and_patch_without_hub_download(self):
        command = build_container_command("a" * 64, 1783990000)
        joined = " ".join(command)
        self.assertIn("/workspace/model-awq", joined)
        self.assertIn("/input/remote_awq_smoke.sh", joined)
        self.assertIn("/input/patch_sglang_awq_loader.py", joined)
        self.assertIn("MODEL_MANIFEST_PATH=/workspace/model-awq/model-files.sha256", joined)
        self.assertNotIn("RUNPOD_API_KEY", joined)
        self.assertNotIn("HF_TOKEN", joined)

    def test_transfer_changes_workspace_ownership(self):
        command = build_model_transfer_command()
        self.assertIn("sudo install -d -o glmrunner -g glmrunner", command)
        self.assertIn("tar -C /workspace/model-awq -xf -", command)

    def test_local_model_validator_rejects_wrong_revision_before_provider_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model-files.sha256").write_text("")
            (root / "model-files-manifest.json").write_text(json.dumps({
                "revision": "wrong",
                "shard_count": 4,
                "weight_bytes": MODEL_WEIGHT_BYTES,
                "files": [],
            }))
            with self.assertRaisesRegex(RuntimeError, "revision"):
                validate_local_model(root)


if __name__ == "__main__":
    unittest.main()
