import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from vllm_recover_existing import resolve_control_summary, reuse_staged_runtime  # noqa: E402


class RecoverExistingTests(unittest.TestCase):
    def test_recovery_accepts_the_pinned_runtime_fp8_token(self):
        source = (ROOT / "nebius" / "vllm_recover_existing.py").read_text()
        self.assertIn('choices=("auto", "fp8_e4m3")', source)
        self.assertNotIn("fp8_e4m3fn", source)
        self.assertIn("execution_outcome(", source)
        self.assertIn("args.keep_instance_after_result and background_pass", source)

    def test_runtime_can_be_reused_while_a_changed_checkpoint_is_restaged(self):
        runtime_only = Namespace(
            reuse_staged_runtime=True,
            reuse_staged_runtime_and_checkpoint=False,
        )
        runtime_and_checkpoint = Namespace(
            reuse_staged_runtime=False,
            reuse_staged_runtime_and_checkpoint=True,
        )
        neither = Namespace(
            reuse_staged_runtime=False,
            reuse_staged_runtime_and_checkpoint=False,
        )

        self.assertTrue(reuse_staged_runtime(runtime_only))
        self.assertTrue(reuse_staged_runtime(runtime_and_checkpoint))
        self.assertFalse(reuse_staged_runtime(neither))

    def write_summary(self, directory: Path, **overrides):
        summary = {
            "retained_for_next_experiment": True,
            "instance_id": "computeinstance-retained",
            "final_instance_count": 1,
            "final_disk_count": 1,
        }
        summary.update(overrides)
        path = directory / "control-summary.json"
        path.write_text(__import__("json").dumps(summary))
        return path

    def test_control_summary_resolves_exact_retained_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_summary(Path(temp))
            instances = [{"metadata": {"id": "computeinstance-retained", "name": "glm-test"}}]
            disks = [{"metadata": {"id": "disk-retained", "name": "glm-test-boot"}}]
            with patch("vllm_recover_existing.list_items", side_effect=[instances, disks]):
                self.assertEqual(resolve_control_summary(path, "glm-test"), "computeinstance-retained")

    def test_control_summary_rejects_not_retained_or_missing_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with self.assertRaisesRegex(RuntimeError, "does not retain"):
                resolve_control_summary(self.write_summary(directory, retained_for_next_experiment=False), "glm-test")
            with self.assertRaisesRegex(RuntimeError, "lacks"):
                resolve_control_summary(self.write_summary(directory, instance_id=""), "glm-test")

    def test_control_summary_rejects_ambiguous_or_drifted_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_summary(Path(temp))
            instances = [
                {"metadata": {"id": "computeinstance-retained", "name": "glm-test"}},
                {"metadata": {"id": "computeinstance-other", "name": "other"}},
            ]
            with patch("vllm_recover_existing.list_items", return_value=instances):
                with self.assertRaisesRegex(RuntimeError, "inventory drifted"):
                    resolve_control_summary(path, "glm-test")

    def test_control_summary_rejects_malformed_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.json"
            path.write_text("{")
            with self.assertRaisesRegex(RuntimeError, "unreadable"):
                resolve_control_summary(path, "glm-test")


if __name__ == "__main__":
    unittest.main()
