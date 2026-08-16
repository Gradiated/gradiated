import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from v2_cache_smoke_runner import evaluate_repetitions, usage_cached_tokens


class V2CacheSmokeRunnerTest(unittest.TestCase):
    def test_extracts_cached_tokens_and_accepts_identical_repeated_digests(self):
        usage = {"prompt_tokens": 183, "prompt_tokens_details": {"cached_tokens": 176}}
        repetitions = [
            [{"request_id": "a", "status": "success", "stream_sha256": "one", "cache_salt": "a" * 64, "usage": usage}],
            [{"request_id": "a", "status": "success", "stream_sha256": "one", "cache_salt": "a" * 64, "usage": usage}],
        ]

        result = evaluate_repetitions(repetitions)

        self.assertEqual(usage_cached_tokens(usage), 176)
        self.assertTrue(result["semantic_repeat_pass"])

    def test_rejects_missing_cached_tokens_and_digest_divergence(self):
        repetitions = [
            [{"request_id": "a", "status": "success", "stream_sha256": "one", "cache_salt": "a" * 64, "usage": {"prompt_tokens": 183}}],
            [{"request_id": "a", "status": "success", "stream_sha256": "two", "cache_salt": "a" * 64, "usage": {"prompt_tokens": 183}}],
        ]

        result = evaluate_repetitions(repetitions)

        self.assertFalse(result["semantic_repeat_pass"])
        self.assertIn("prompt_tokens_details.cached_tokens", result["failures"])


if __name__ == "__main__":
    unittest.main()
