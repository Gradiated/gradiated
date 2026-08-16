import sys
import json
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from cache_on_smoke_packet import evaluate_smoke, metric_totals


class CacheOnSmokePacketTest(unittest.TestCase):
    def test_accepts_nonzero_cache_counters_and_per_request_cached_tokens(self):
        fixtures = PROJECT / "fixtures"
        before = (fixtures / "cache-on-metrics-before.prom").read_text()
        after = (fixtures / "cache-on-metrics-after.prom").read_text()
        outcomes = [json.loads(row) for row in (fixtures / "cache-on-outcomes.jsonl").read_text().splitlines()]

        result = evaluate_smoke(metric_totals(before), metric_totals(after), outcomes)

        self.assertTrue(result["pass"])
        self.assertEqual(result["cached_prompt_tokens"], 176)

    def test_rejects_missing_per_request_cache_details(self):
        before = "vllm:prefix_cache_queries_total 0\nvllm:prefix_cache_hits_total 0\n"
        after = "vllm:prefix_cache_queries_total 1\nvllm:prefix_cache_hits_total 1\n"
        outcomes = [{"request_id": "s0t0", "status": "success", "cache_salt": "a" * 64, "usage": {"prompt_tokens": 183}}]

        result = evaluate_smoke(metric_totals(before), metric_totals(after), outcomes)

        self.assertFalse(result["pass"])
        self.assertIn("prompt_tokens_details.cached_tokens", result["failures"])


if __name__ == "__main__":
    unittest.main()
