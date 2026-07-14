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


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


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

    def test_graphql_h100_request_maps_exact_official_input_without_credentials(self):
        request = build_request(
            {
                "provider_request": {
                    "api_surface": "graphql_podFindAndDeployOnDemand",
                    "name": "phase-b-stock-h100-ap-in-test",
                    "gpu_type_id": "NVIDIA H100 80GB HBM3",
                    "cloud_class": "SECURE",
                    "allowed_cuda_versions": ["13.0"],
                    "data_center_ids": ["AP-IN-1"],
                    "interruptible": False,
                    "support_public_ip": True,
                    "container_disk_gb": 40,
                    "volume_gb": 100,
                    "public_artifact_port": 8000,
                },
                "timeouts": {"remote_command_seconds": 5100},
            },
            "d" * 64,
            1783952000,
        )

        self.assertEqual(request["api_surface"], "graphql_podFindAndDeployOnDemand")
        self.assertIn("podFindAndDeployOnDemand", request["query"])
        graphql_input = request["variables"]["input"]
        self.assertEqual(graphql_input["cloudType"], "SECURE")
        self.assertEqual(graphql_input["gpuTypeId"], "NVIDIA H100 80GB HBM3")
        self.assertEqual(graphql_input["dataCenterId"], "AP-IN-1")
        self.assertEqual(graphql_input["allowedCudaVersions"], ["13.0"])
        self.assertEqual(graphql_input["containerDiskInGb"], 40)
        self.assertEqual(graphql_input["volumeInGb"], 100)
        self.assertEqual(graphql_input["ports"], "8000/tcp")
        self.assertTrue(graphql_input["dockerArgs"].startswith("/bin/bash -lc "))
        self.assertIn("/tmp/campaign-100-phase-b.sh", graphql_input["dockerArgs"])
        env = {row["key"]: row["value"] for row in graphql_input["env"]}
        self.assertEqual(env["EXPERIMENT_SPEC_SHA256"], "d" * 64)
        self.assertNotIn("RUNPOD_API_KEY", env)
        self.assertNotIn("RUNPOD_API_KEY", json.dumps(request))

    def test_graphql_request_rejects_multiple_datacenters(self):
        with self.assertRaisesRegex(RunPodError, "exactly one data center"):
            build_request(
                {
                    "provider_request": {
                        "api_surface": "graphql_podFindAndDeployOnDemand",
                        "name": "invalid",
                        "gpu_type_id": "NVIDIA H100 80GB HBM3",
                        "cloud_class": "SECURE",
                        "data_center_ids": ["AP-IN-1", "US-KS-2"],
                        "interruptible": False,
                    },
                    "timeouts": {"remote_command_seconds": 5100},
                },
                "e" * 64,
                1783952000,
            )

    def test_graphql_errors_fail_closed_without_credential_or_error_body_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            event_log = Path(directory) / "provider-events.jsonl"
            provider = RunPodProvider(
                event_log=event_log,
                deadline_epoch=1783952000,
                startup_timeout_seconds=900,
            )
            secret = "credential-must-not-leak"
            response = FakeResponse(json.dumps({
                "errors": [{"message": f"provider reflected {secret}"}],
                "data": {"podFindAndDeployOnDemand": None},
            }).encode())
            request = {
                "api_surface": "graphql_podFindAndDeployOnDemand",
                "query": "mutation($input: PodFindAndDeployOnDemandInput){podFindAndDeployOnDemand(input:$input){id}}",
                "variables": {"input": {"name": "test"}},
            }
            with patch.dict("os.environ", {"RUNPOD_API_KEY": secret}), patch(
                "urllib.request.urlopen", return_value=response
            ) as urlopen, self.assertRaisesRegex(RunPodError, "GraphQL create returned errors"):
                provider.create(request)
            sent_request = urlopen.call_args.args[0]
            self.assertEqual(sent_request.full_url, "https://api.runpod.io/graphql")
            self.assertEqual(sent_request.get_header("User-agent"), "glm47flash-campaign-100/1.0")
            self.assertNotIn(secret, sent_request.data.decode())
            self.assertNotIn(secret, event_log.read_text())

    def test_graphql_no_pod_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RunPodProvider(
                event_log=Path(directory) / "provider-events.jsonl",
                deadline_epoch=1783952000,
                startup_timeout_seconds=900,
            )
            response = FakeResponse(json.dumps({
                "data": {"podFindAndDeployOnDemand": {"costPerHr": 2.99}}
            }).encode())
            request = {
                "api_surface": "graphql_podFindAndDeployOnDemand",
                "query": "mutation($input: PodFindAndDeployOnDemandInput){podFindAndDeployOnDemand(input:$input){id costPerHr}}",
                "variables": {"input": {"name": "test"}},
            }
            with patch.dict("os.environ", {"RUNPOD_API_KEY": "safe-test-key"}), patch(
                "urllib.request.urlopen", return_value=response
            ), self.assertRaisesRegex(RunPodError, "omitted pod id"):
                provider.create(request)

    def test_graphql_response_maps_into_existing_orchestrator_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RunPodProvider(
                event_log=Path(directory) / "provider-events.jsonl",
                deadline_epoch=1783952000,
                startup_timeout_seconds=900,
            )
            response = FakeResponse(json.dumps({
                "data": {"podFindAndDeployOnDemand": {
                    "id": "pod-graphql-1",
                    "costPerHr": 2.99,
                    "createdAt": "2026-07-13T15:00:00Z",
                    "desiredStatus": "RUNNING",
                    "machineId": "machine-1",
                    "imageName": "image",
                }}
            }).encode())
            request = {
                "api_surface": "graphql_podFindAndDeployOnDemand",
                "query": "mutation($input: PodFindAndDeployOnDemandInput){podFindAndDeployOnDemand(input:$input){id costPerHr createdAt desiredStatus machineId imageName}}",
                "variables": {"input": {"name": "test"}},
            }
            with patch.dict("os.environ", {"RUNPOD_API_KEY": "safe-test-key"}), patch(
                "urllib.request.urlopen", return_value=response
            ):
                row = provider.create(request)
            self.assertEqual(row["id"], "pod-graphql-1")
            self.assertEqual(row["costPerHr"], 2.99)
            self.assertEqual(row["desiredStatus"], "RUNNING")
            self.assertEqual(provider.last_pod_id, "pod-graphql-1")
            self.assertEqual(provider.hourly_rate, 2.99)

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
