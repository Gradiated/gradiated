import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from paid_smoke_preregistration import build_preregistration, validate_preregistration


class PaidSmokePreregistrationTest(unittest.TestCase):
    def test_binds_immutable_packet_runner_and_respects_all_in_cap(self):
        value = build_preregistration()

        validate_preregistration(value)

        self.assertLessEqual(value["budget"]["all_in_cap_usd"], 1.50)
        self.assertEqual(value["phases"]["total_allocation_seconds"], 2700)
        self.assertEqual(value["phases"]["rows"][2]["name"], "verified_awq_checkpoint_transfer")
        self.assertEqual(value["controller_lifecycle"]["provider_create_gate"], "durable_factory_controller_live_and_watchdog_armed")


if __name__ == "__main__":
    unittest.main()
