import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("parallel_draft_frontier.py")
SPEC = importlib.util.spec_from_file_location("parallel_draft_frontier", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ParallelDraftFrontierTest(unittest.TestCase):
    def test_runtime_first_difference_is_request_keyed(self):
        left = [
            {"index": 0, "request_sha256": "a", "token_ids": [1, 2]},
            {"index": 1, "request_sha256": "b", "token_ids": [3, 4]},
        ]
        right = [
            {"index": 9, "request_sha256": "b", "token_ids": [3, 5]},
            {"index": 8, "request_sha256": "a", "token_ids": [1, 2]},
        ]
        self.assertEqual(
            MODULE.first_token_difference(left, right),
            {
                "request_index": 1,
                "request_sha256": "b",
                "output_index": 1,
                "left_token": 4,
                "right_token": 5,
                "left_prefix": [3, 4],
                "right_prefix": [3, 5],
            },
        )

    def test_future_map_preserves_real_state_ownership(self):
        first = {
            "request_id": "a",
            "bonus_token": 11,
            "sequence_length_after": 101,
            "kv_locations": [1001],
        }
        second = {
            "request_id": "b",
            "bonus_token": 22,
            "sequence_length_after": 202,
            "kv_locations": [2002],
        }
        result = MODULE.relay_reproducer(first, second)
        self.assertTrue(result["aa_identity_control"]["arms_equal"])
        self.assertFalse(
            result["reorder_discriminator"]["direct_carry_pass"]
        )
        self.assertTrue(result["reorder_discriminator"]["future_map_pass"])


if __name__ == "__main__":
    unittest.main()
