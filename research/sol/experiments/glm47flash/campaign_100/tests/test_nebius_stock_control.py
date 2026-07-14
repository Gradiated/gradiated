import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from stock_control import (  # noqa: E402
    ABSOLUTE_TIMEOUT_SECONDS,
    IMAGE,
    MAX_COMPUTE_COST_USD,
    MODEL_REVISION,
    build_container_command,
    build_host_bootstrap,
    build_model_transfer_command,
    fixed_sequence_pass,
    mtp_performance_gate,
    paired_non_regression_gate,
    validate_local_contracts,
    verify_internal_manifest,
)
from placement_control import build_create_command  # noqa: E402


class NebiusStockControlTests(unittest.TestCase):
    def test_create_command_supports_changed_l40s_preemptible_lineage(self):
        command = build_create_command(
            name="awq-v1",
            disk_name="awq-v1-boot",
            cloud_init="#cloud-config\n",
            disk_gib=100,
            platform="gpu-l40s-a",
            preset="1gpu-16vcpu-64gb",
            preemptible=True,
        )
        joined = " ".join(command)
        self.assertIn("--resources-platform gpu-l40s-a", joined)
        self.assertIn("--resources-preset 1gpu-16vcpu-64gb", joined)
        self.assertIn("--preemptible-on-preemption stop", joined)
        self.assertNotIn("preemptible-priority", joined)

    def test_diagnostic_admission_requires_artifact_and_fixed_sequence(self):
        arm = {"artifact_ok": True, "allocation_result": {"sequence_pass": True, "quality_pass": False}}
        self.assertTrue(fixed_sequence_pass(arm))
        arm["artifact_ok"] = False
        self.assertFalse(fixed_sequence_pass(arm))

    def test_paired_non_regression_is_separate_from_absolute_quality(self):
        result = {
            "overall_regression": 0.0,
            "category_regressions": {"coding": 0.0, "teacher_forced_loss": 0.0},
            "point_screen_pass": False,
        }
        gate = paired_non_regression_gate(result)
        self.assertTrue(gate["pass"])
        self.assertFalse(gate["absolute_point_screen_pass"])
        result["category_regressions"]["coding"] = -0.06
        self.assertTrue(paired_non_regression_gate(result)["pass"])
        result["category_regressions"]["coding"] = 0.06
        self.assertFalse(paired_non_regression_gate(result)["pass"])

    def test_mtp_performance_gate_requires_five_percent_and_both_slos(self):
        def result(rate, slo=True):
            return {"profiles": [{
                "profile_id": "fixed_8k_1k_c8",
                "output_tokens_per_second_conservative": rate,
                "frozen_slo_pass": slo,
            }]}

        self.assertTrue(mtp_performance_gate(result(100), result(105))["pass"])
        self.assertFalse(mtp_performance_gate(result(100), result(104.9))["pass"])
        self.assertFalse(mtp_performance_gate(result(100), result(110, False))["pass"])

    def test_image_and_budget_are_pinned_under_authorized_cap(self):
        self.assertEqual(
            IMAGE,
            "lmsysorg/sglang:v0.5.15-cu130@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af",
        )
        self.assertEqual(MODEL_REVISION, "33faccf4c2ba82142214d0d4e16232a4e9ccfe10")
        self.assertEqual(ABSOLUTE_TIMEOUT_SECONDS, 5400)
        self.assertAlmostEqual(MAX_COMPUTE_COST_USD, 5.775)
        self.assertLess(MAX_COMPUTE_COST_USD, 25)

    def test_bootstrap_configures_docker_gpu_runtime_and_records_versions(self):
        script = build_host_bootstrap()
        self.assertIn("docker.io", script)
        self.assertIn("nvidia-container-toolkit", script)
        self.assertIn("nvidia-ctk runtime configure", script)
        self.assertIn("dpkg-query", script)
        self.assertIn("docker pull", script)
        self.assertIn(IMAGE, script)
        self.assertNotIn("PRIVATE KEY", script)

    def test_container_command_mounts_frozen_inputs_and_disables_http_wait(self):
        command = build_container_command("a" * 64, 1783990000)
        joined = " ".join(command)
        self.assertIn("--gpus", command)
        self.assertIn("/workspace:/workspace", joined)
        self.assertIn("/input:ro", joined)
        self.assertIn("SERVE_ARTIFACT=0", joined)
        self.assertIn("WORKLOAD_ARCHIVE_PATH=/input/frozen-workloads.tar.gz", joined)
        self.assertIn("QUALITY_ARCHIVE_PATH=/input/frozen-quality.tar.gz", joined)
        self.assertIn("ARTIFACT_BUILDER_PATH=/input/artifact_builder.py", joined)
        self.assertIn(f"MODEL_REVISION={MODEL_REVISION}", joined)
        self.assertIn("MODEL_MANIFEST_PATH=/workspace/model-bf16/model-files.sha256", joined)
        self.assertIn(IMAGE, command)
        self.assertNotIn("RUNPOD_API_KEY", joined)

    def test_model_transfer_changes_workspace_ownership_before_extract(self):
        command = build_model_transfer_command()
        self.assertIn("sudo install -d -o glmrunner -g glmrunner", command)
        self.assertIn("tar -C /workspace/model-bf16 -xf -", command)

    def test_internal_manifest_verifier_accepts_exact_hashes_and_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "campaign-100-phase-b"
            root.mkdir()
            (root / "evidence.txt").write_text("measured\n")
            import hashlib
            digest = hashlib.sha256((root / "evidence.txt").read_bytes()).hexdigest()
            (root / "manifest.json").write_text(json.dumps([
                {"path": "evidence.txt", "bytes": 9, "sha256": digest}
            ]))
            archive = Path(directory) / "artifact.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                bundle.add(root, arcname=root.name)
            self.assertEqual(verify_internal_manifest(archive), 1)
            (root / "evidence.txt").write_text("tampered\n")
            with tarfile.open(archive, "w:gz") as bundle:
                bundle.add(root, arcname=root.name)
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_internal_manifest(archive)

    def test_local_contracts_are_validated_before_provider_access(self):
        identities = validate_local_contracts()
        self.assertEqual(
            identities["workload_sha256"],
            "f47c7af5e53483524010d06a93313b29f1a10c08f7df4bf18638349b4767193a",
        )
        self.assertEqual(
            identities["quality_sha256"],
            "152548d51fba8e8ff5e8f1e665c5af166fb6d97cdf3010723042112855964668",
        )


if __name__ == "__main__":
    unittest.main()
