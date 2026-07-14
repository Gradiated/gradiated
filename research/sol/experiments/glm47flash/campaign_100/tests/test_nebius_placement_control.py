import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from placement_control import (  # noqa: E402
    HOURLY_RATE_USD,
    build_create_command,
    conservative_cost_usd,
    extract_instance_id,
    extract_public_ipv4,
    validate_gpu_csv,
)


class NebiusPlacementControlTests(unittest.TestCase):
    def test_create_command_is_exact_regular_h100_geometry(self):
        command = build_create_command(
            name="glm-nebius-h100-smoke-test",
            disk_name="glm-nebius-h100-smoke-test-boot",
            cloud_init="#cloud-config\nusers: []\n",
        )
        joined = " ".join(command)
        self.assertIn("gpu-h100-sxm", command)
        self.assertIn("1gpu-16vcpu-200gb", command)
        self.assertIn("ubuntu24.04-cuda13.0", command)
        self.assertIn("network_ssd", command)
        self.assertIn("default-subnet", joined)
        self.assertIn("vpcsubnet-", joined)
        self.assertNotIn("private.pem", joined)
        self.assertNotIn("secret", joined.lower())

    def test_create_command_accepts_larger_inference_disk(self):
        command = build_create_command(
            name="glm-nebius-stock-test",
            disk_name="glm-nebius-stock-test-boot",
            cloud_init="#cloud-config\nusers: []\n",
            disk_gib=250,
        )
        index = command.index("--boot-disk-managed-disk-size-gibibytes")
        self.assertEqual(command[index + 1], "250")

    def test_instance_id_is_found_in_resource_or_operation_shape(self):
        for payload in (
            {"metadata": {"id": "computeinstance-e00abc"}},
            {"resource_id": "computeinstance-e00def"},
            {"result": {"metadata": {"id": "computeinstance-e00ghi"}}},
        ):
            with self.subTest(payload=payload):
                self.assertTrue(extract_instance_id(payload).startswith("computeinstance-"))

    def test_public_ipv4_is_found_without_accepting_private_address(self):
        payload = {
            "status": {
                "network_interfaces": [{
                    "ip_address": {"address": "10.0.0.4"},
                    "public_ip_address": {"address": "8.8.8.8/32"},
                }]
            }
        }
        self.assertEqual(extract_public_ipv4(payload), "8.8.8.8")

    def test_gpu_gate_accepts_one_80gb_h100_without_mig(self):
        row = "NVIDIA H100 80GB HBM3, 81559, Disabled, 550.90.07, 1, 12, 65.0"
        parsed = validate_gpu_csv(row)
        self.assertEqual(parsed["gpu_count"], 1)
        self.assertGreaterEqual(parsed["memory_mib"], 80000)

    def test_gpu_gate_rejects_wrong_gpu_or_mig(self):
        with self.assertRaisesRegex(ValueError, "H100"):
            validate_gpu_csv("NVIDIA A100-SXM4-80GB, 81920, Disabled, 550.1, 0, 0, 50")
        with self.assertRaisesRegex(ValueError, "MIG"):
            validate_gpu_csv("NVIDIA H100 80GB HBM3, 81559, Enabled, 550.1, 0, 0, 50")

    def test_cost_is_conservative_and_capped_geometry_is_below_budget(self):
        self.assertEqual(HOURLY_RATE_USD, 2.95)
        self.assertAlmostEqual(conservative_cost_usd(900), 0.7375)
        self.assertLess(conservative_cost_usd(900), 0.80)

    def test_source_contains_no_credential_values(self):
        source = (ROOT / "nebius" / "placement_control.py").read_text()
        self.assertNotIn("BEGIN PRIVATE KEY", source)
        self.assertNotIn("RUNPOD_API_KEY", source)
        json.dumps(source)


if __name__ == "__main__":
    unittest.main()
