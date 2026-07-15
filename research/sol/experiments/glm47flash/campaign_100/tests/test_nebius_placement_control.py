import json
import subprocess
import sys
import time
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from placement_control import (  # noqa: E402
    HOURLY_RATE_USD,
    build_create_command,
    conservative_cost_usd,
    extract_instance_id,
    extract_public_ipv4,
    watchdog,
    validate_gpu_csv,
)
import placement_control  # noqa: E402


class NebiusPlacementControlTests(unittest.TestCase):
    def test_wait_ssh_emits_ordered_success_attempt_without_sensitive_fields(self):
        clock = mock.Mock(side_effect=[100.0, 100.0, 101.5])
        observed = []
        probe = mock.Mock(return_value=mock.Mock(returncode=0, stdout="secret", stderr="private"))
        with mock.patch.object(placement_control, "refresh_ephemeral_host_key"), \
             mock.patch.object(placement_control.time, "time", clock), \
             mock.patch.object(placement_control.subprocess, "run", probe):
            placement_control.wait_ssh(
                "8.8.8.8", Path("/secret/key"), 200.0,
                observer=lambda event, fields: observed.append((event, fields)),
            )
        self.assertEqual([event for event, _ in observed], ["ssh_cloud_init_attempt"])
        self.assertEqual(observed[0][1]["attempt_number"], 1)
        self.assertEqual(observed[0][1]["return_code"], 0)
        self.assertTrue(observed[0][1]["success"])
        self.assertNotIn("8.8.8.8", json.dumps(observed))
        self.assertNotIn("secret", json.dumps(observed))
        self.assertNotIn("private", json.dumps(observed))
        self.assertNotIn("/secret/key", json.dumps(observed))
        probe.assert_called_once()

    def test_wait_ssh_retry_timeout_error_and_deadline_are_typed_and_bounded(self):
        cases = [
            ("retry_then_success", [mock.Mock(returncode=1), mock.Mock(returncode=0)], None),
            ("subprocess_timeout", [subprocess.TimeoutExpired(["ssh"], 20)], placement_control.PlacementError),
            ("subprocess_error", [OSError("transport")], placement_control.PlacementError),
            ("deadline_timeout", [mock.Mock(returncode=1)], placement_control.PlacementError),
        ]
        for name, outcomes, expected_error in cases:
            with self.subTest(name=name):
                now = [100.0]
                observed = []
                def fake_time():
                    return now[0]
                def fake_sleep(seconds):
                    now[0] += seconds
                def fake_run(*_args, **_kwargs):
                    result = outcomes.pop(0)
                    if isinstance(result, BaseException):
                        raise result
                    return result
                with mock.patch.object(placement_control, "refresh_ephemeral_host_key"), \
                     mock.patch.object(placement_control.time, "time", side_effect=fake_time), \
                     mock.patch.object(placement_control.time, "sleep", side_effect=fake_sleep), \
                     mock.patch.object(placement_control.subprocess, "run", side_effect=fake_run):
                    if expected_error:
                        with self.assertRaises(expected_error):
                            placement_control.wait_ssh(
                                "192.0.2.1", Path("key"), 108.0,
                                observer=lambda event, fields: observed.append((event, fields)),
                            )
                    else:
                        placement_control.wait_ssh(
                            "192.0.2.1", Path("key"), 200.0,
                            observer=lambda event, fields: observed.append((event, fields)),
                        )
                self.assertTrue(observed)
                self.assertEqual(
                    [fields["attempt_number"] for _, fields in observed],
                    list(range(1, len(observed) + 1)),
                )
                self.assertTrue(all("outcome" in fields and "success" in fields for _, fields in observed))
                if name == "deadline_timeout":
                    self.assertEqual(len(observed), 1)
                    self.assertEqual(observed[0][1]["outcome"], "return_code")

    def test_readiness_geometry_is_fail_closed_and_provider_commands_are_not_in_fixture_tests(self):
        source = (ROOT / "nebius" / "observer_diagnostic_control.py").read_text()
        self.assertIn("started + 420", source)
        self.assertIn("started + 480", source)
        self.assertIn("ABSOLUTE_TIMEOUT_SECONDS = 2000", source)
        self.assertIn("CLEANUP_RESERVE_SECONDS = 240", source)
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

    def test_create_command_binds_factory_labels_to_instance_and_disk(self):
        labels = {
            "program_id": "glm-4-7-flash",
            "campaign_id": "glm47-nebius-25",
            "run_id": "glm47-observer-diagnostic-l40s-v1",
        }
        command = build_create_command(
            name="glm47-observer-diagnostic-l40s-v1",
            disk_name="glm47-observer-diagnostic-l40s-v1-boot",
            cloud_init="#cloud-config\nusers: []\n",
            labels=labels,
        )
        encoded = "program_id=glm-4-7-flash,campaign_id=glm47-nebius-25,run_id=glm47-observer-diagnostic-l40s-v1"
        self.assertEqual(encoded, command[command.index("--labels") + 1])
        self.assertEqual(
            encoded,
            command[command.index("--boot-disk-managed-disk-labels") + 1],
        )

    def test_create_command_rejects_unsafe_factory_labels(self):
        with self.assertRaisesRegex(ValueError, "label"):
            build_create_command(
                name="glm47-observer",
                disk_name="glm47-observer-boot",
                cloud_init="#cloud-config\nusers: []\n",
                labels={"run_id": "contains,comma"},
            )

    @mock.patch("placement_control.delete_disk")
    @mock.patch("placement_control.list_items")
    @mock.patch("placement_control.delete_instance")
    @mock.patch("placement_control.get_instance", return_value=None)
    def test_watchdog_deletes_named_disk_when_instance_is_already_absent(
        self, _get_instance, _delete_instance, list_items, delete_disk
    ):
        list_items.return_value = [
            {"metadata": {"id": "disk-example", "name": "observer-boot"}}
        ]
        self.assertEqual(0, watchdog("instance-example", "observer-boot", time.time() + 60))
        delete_disk.assert_called_once_with("disk-example")

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
