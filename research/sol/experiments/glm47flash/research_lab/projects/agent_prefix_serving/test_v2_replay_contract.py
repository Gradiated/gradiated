import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from v2_replay_contract import build_v2_plan, request_payload, validate_v2_plan


class V2ReplayContractTest(unittest.TestCase):
    def test_materializes_eight_isolated_three_turn_sessions_and_transports_salts(self):
        plan = build_v2_plan()
        validated = validate_v2_plan(plan)

        self.assertEqual(validated["profile_id"], "agent_prefix_c8")
        self.assertEqual(len(validated["requests"]), 24)
        salts = [row["cache_salt"] for row in validated["requests"]]
        self.assertEqual(len(set(salts)), 8)
        self.assertTrue(all(len(salt) == 64 for salt in salts))
        self.assertEqual([salts.count(salt) for salt in sorted(set(salts))], [3] * 8)
        payload = request_payload(validated["requests"][0])
        self.assertEqual(payload["model"], "glm-4.7-flash-awq")
        self.assertEqual(payload["cache_salt"], validated["requests"][0]["cache_salt"])
        self.assertEqual(payload["stream_options"], {"include_usage": True, "continuous_usage_stats": True})


if __name__ == "__main__":
    unittest.main()
