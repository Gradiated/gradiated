import importlib.util
import math
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "rolling_screen", PROJECT_DIR / "run_rolling_batching_screen.py"
)
assert SPEC is not None and SPEC.loader is not None
SCREEN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SCREEN
SPEC.loader.exec_module(SCREEN)


class RollingBatchingScreenTest(unittest.TestCase):
    def test_cache_mix_is_exact_per_period(self) -> None:
        cached = [
            SCREEN.cached_tokens_for_request(index)
            for index in range(SCREEN.CACHE_MIX_PERIOD)
        ]
        self.assertEqual(cached.count(535), 822)
        self.assertEqual(cached.count(536), 178)
        self.assertEqual(sum(cached), 535_178)

    def test_attention_geometry_matches_parent_whole_prompt(self) -> None:
        request = SCREEN.Request(0, 0.0, 535, 3679)
        sliding, global_pairs, kv_bytes = SCREEN.prefill_attention_geometry(
            request, 3679
        )
        self.assertEqual(sliding, 3_647_980)
        self.assertEqual(global_pairs, 8_737_625)
        self.assertEqual(
            kv_bytes,
            60 * SCREEN.PROMPT_TOKENS * SCREEN.KV_BYTES_PER_TOKEN_LAYER,
        )

    def test_small_finite_stream_preserves_every_stage(self) -> None:
        count = 100
        result = SCREEN.simulate(SCREEN.make_requests(count, 0.5))
        accounting = result["accounting"]
        expected_prefill = sum(
            request.fresh_prompt_tokens
            for request in SCREEN.make_requests(count, 0)
        )
        self.assertTrue(result["all_requests_completed"])
        self.assertEqual(int(accounting["prefill_tokens"]), expected_prefill)
        self.assertEqual(
            int(accounting["decode_rows"] + accounting["prefill_head_rows"]),
            count * SCREEN.OUTPUT_TOKENS,
        )
        self.assertEqual(
            int(accounting["target_cycles"]), count * SCREEN.TARGET_CYCLES
        )
        self.assertEqual(result["starved_requests"], 0)

    def test_costs_are_finite_and_nonnegative(self) -> None:
        result = SCREEN.simulate(SCREEN.make_requests(20, 0.25))
        self.assertTrue(math.isfinite(result["final_completion_seconds"]))
        self.assertGreater(result["final_completion_seconds"], 0)
        self.assertTrue(
            all(value >= 0 for value in result["accounting"].values())
        )


if __name__ == "__main__":
    unittest.main()
