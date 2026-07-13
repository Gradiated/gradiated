import base64
import io
import json
import sys
import tarfile
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "phase_b"))
from runpod_stock_control import (  # noqa: E402
    RunPodError,
    RunPodProvider,
    build_request,
    frozen_archive_b64,
)


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

    def test_changed_sxm_placement_binds_cuda_datacenters_and_ondemand_mode(self):
        request = build_request(
            {
                "provider_request": {
                    "name": "phase-b-stock-a100-sxm-secure-test",
                    "gpu_type_id": "NVIDIA A100-SXM4-80GB",
                    "cloud_class": "SECURE",
                    "allowed_cuda_versions": ["13.0"],
                    "data_center_ids": ["US-KS-2"],
                    "data_center_priority": "availability",
                    "interruptible": False,
                    "support_public_ip": True,
                },
                "timeouts": {"remote_command_seconds": 5100},
            },
            "c" * 64,
            1783952000,
        )
        self.assertEqual(request["gpuTypeIds"], ["NVIDIA A100-SXM4-80GB"])
        self.assertEqual(request["cloudType"], "SECURE")
        self.assertEqual(request["allowedCudaVersions"], ["13.0"])
        self.assertEqual(request["dataCenterIds"], ["US-KS-2"])
        self.assertEqual(request["dataCenterPriority"], "availability")
        self.assertIs(request["interruptible"], False)
        self.assertIs(request["supportPublicIp"], True)

    def test_provider_http_error_event_is_allowlisted_and_credential_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            event_log = Path(directory) / "provider-events.jsonl"
            provider = RunPodProvider(
                event_log=event_log,
                deadline_epoch=1783952000,
                startup_timeout_seconds=900,
            )
            error = urllib.error.HTTPError(
                "https://rest.runpod.io/v1/pods",
                500,
                "server error",
                {"content-type": "application/json", "x-request-id": "req-test"},
                io.BytesIO(
                    b'{"error":"create pod: no capacity","status":500,'
                    b'"token":"must-not-be-retained"}'
                ),
            )
            with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(
                RunPodError
            ):
                provider._api("/pods", "POST", {"name": "test"})
            event = json.loads(event_log.read_text())
            self.assertEqual(event["event"], "provider_http_error")
            self.assertEqual(event["http_status"], 500)
            self.assertEqual(event["safe_response_body"], {
                "error": "create pod: no capacity",
                "status": 500,
            })
            self.assertNotIn("must-not-be-retained", event_log.read_text())


if __name__ == "__main__":
    unittest.main()
