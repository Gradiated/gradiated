import base64
import io
import json
import sys
import tarfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "phase_b"))
from runpod_stock_control import build_request, frozen_archive_b64  # noqa: E402


class RunPodStockControlTests(unittest.TestCase):
    def test_frozen_archives_contain_exact_manifest_members(self):
        for directory in (ROOT / "workloads", ROOT / "quality"):
            manifest = json.loads((directory / "FROZEN_MANIFEST.json").read_text())
            expected = {"FROZEN_MANIFEST.json", *manifest["files"]}
            payload = base64.b64decode(frozen_archive_b64(directory))
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
                self.assertEqual(set(archive.getnames()), expected)

    def test_request_is_changed_a100_stock_placement_without_credentials(self):
        request = build_request(
            {
                "provider_request": {
                    "name": "phase-b-stock-a100-test",
                    "gpu_type_id": "NVIDIA A100 80GB PCIe",
                    "cloud_class": "COMMUNITY",
                },
                "timeouts": {"remote_command_seconds": 5100},
            },
            "a" * 64,
            1783952000,
        )
        self.assertEqual(request["gpuTypeIds"], ["NVIDIA A100 80GB PCIe"])
        self.assertEqual(request["cloudType"], "COMMUNITY")
        self.assertEqual(request["gpuCount"], 1)
        self.assertIn("v0.5.15-cu130@sha256:", request["imageName"])
        self.assertEqual(request["env"]["EXPERIMENT_SPEC_SHA256"], "a" * 64)
        self.assertNotIn("RUNPOD_API_KEY", json.dumps(request))
        self.assertNotIn("--speculative", base64.b64decode(request["env"]["SCRIPT_B64"]).decode())
        self.assertIn("--disable-radix-cache", base64.b64decode(request["env"]["SCRIPT_B64"]).decode())

    def test_secure_retry_changes_cloud_class_without_changing_gpu(self):
        request = build_request(
            {
                "provider_request": {
                    "name": "phase-b-stock-a100-secure-test",
                    "gpu_type_id": "NVIDIA A100 80GB PCIe",
                    "cloud_class": "SECURE",
                },
                "timeouts": {"remote_command_seconds": 5100},
            },
            "b" * 64,
            1783952000,
        )
        self.assertEqual(request["gpuTypeIds"], ["NVIDIA A100 80GB PCIe"])
        self.assertEqual(request["cloudType"], "SECURE")


if __name__ == "__main__":
    unittest.main()
