import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "nebius" / "vllm_batched_runner.py"
spec = importlib.util.spec_from_file_location("vllm_batched_runner", SOURCE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class VllmBatchedRunnerTests(unittest.TestCase):
    def test_percentile_is_nearest_rank(self):
        self.assertEqual(module.percentile([1, 2, 3, 4], 0.5), 2)
        self.assertEqual(module.percentile([1, 2, 3, 4], 0.95), 4)

    def test_fenced_json_is_accepted_for_semantic_smoke_only(self):
        self.assertEqual(module.parse_json_content('```json\n{"alpha":17,"beta":"smoke"}\n```'), module.EXPECTED_JSON)

    def test_metric_totals_accept_vllm_prefix_and_labels(self):
        text = 'vllm:request_queue_time_seconds_sum{model_name="x"} 1.5\nvllm:request_queue_time_seconds_count{model_name="x"} 3\n'
        result = module.metric_totals(text)
        self.assertEqual(result["request_queue_time_seconds_sum"], 1.5)
        self.assertEqual(result["request_queue_time_seconds_count"], 3)

    def test_economic_thresholds_are_frozen(self):
        self.assertAlmostEqual(module.L40S_HOURLY_USD, 0.8581222)
        self.assertAlmostEqual(module.BF16_C8_TOK_S, 305.0449)

    def test_quality_scorer_interface_and_source_match_frozen_contract(self):
        source = SOURCE.read_text()
        self.assertNotIn('"--suite"', source)
        self.assertIn('"runtime_teacher_forced_input_token_logprobs"', source)

    def test_vllm_completion_prompt_logprobs_are_read_from_choice(self):
        response = {
            "choices": [{
                "prompt_token_ids": [10, 11, 12],
                "prompt_logprobs": [None, {"11": {"logprob": -1.25}}, {"12": {"logprob": -2.5}}],
            }]
        }
        result = module.extract_teacher_forced_logprobs(response, minimum_scored_tokens=2)
        self.assertEqual(result, [{"logprob": -1.25, "token_id": 11}, {"logprob": -2.5, "token_id": 12}])

    def test_quality_failure_does_not_suppress_fixed_performance(self):
        source = SOURCE.read_text()
        self.assertIn('"quality_error"', source)
        self.assertIn("performance_batch(args.output, args.tokenizer, parse_concurrencies(args.concurrencies))", source)

    def test_prefix_cache_counters_are_part_of_slo_evidence(self):
        text = "vllm:prefix_cache_queries_total 0\nvllm:prefix_cache_hits_total 0\n"
        totals = module.metric_totals(text)
        self.assertEqual(totals["prefix_cache_queries_total"], 0)
        self.assertEqual(totals["prefix_cache_hits_total"], 0)

    def test_frontier_concurrency_contract_accepts_any_positive_increasing_frontier(self):
        self.assertEqual(module.parse_concurrencies("1,8,16"), (1, 8, 16))
        self.assertEqual(module.parse_concurrencies("16,24,32"), (16, 24, 32))
        self.assertNotIn('next(profile for profile in profiles if profile["concurrency"] == 8)', SOURCE.read_text())
        with self.assertRaises(module.BatchError):
            module.parse_concurrencies("16,8")
        with self.assertRaises(module.BatchError):
            module.parse_concurrencies("1,8,8")
        with self.assertRaises(module.BatchError):
            module.parse_concurrencies("0,8")

    def test_scheduling_knee_preserves_duplicate_c32_anchors_with_unique_artifact_ids(self):
        values = module.parse_concurrencies("32,24,28,30,32")
        self.assertEqual(values, (32, 24, 28, 30, 32))
        self.assertEqual(module.arm_identities(values), ("c32_pre", "c24", "c28", "c30", "c32_post"))
        self.assertEqual(len(set(module.arm_identities(values))), 5)

    def test_scheduling_knee_uses_two_complete_waves_per_ordered_arm(self):
        for concurrency in (32, 24, 28, 30, 32):
            self.assertEqual(module.requests_for_concurrency(concurrency), concurrency * 2)

    def test_higher_frontier_profiles_use_two_full_batches(self):
        self.assertEqual(module.requests_for_concurrency(1), 4)
        self.assertEqual(module.requests_for_concurrency(8), 16)
        self.assertEqual(module.requests_for_concurrency(16), 32)

    def test_stream_token_ids_are_retained_as_an_order_free_histogram(self):
        histogram = {}
        self.assertEqual(module.accumulate_output_token_histogram(histogram, [5, 2, 5]), 3)
        self.assertEqual(histogram, {2: 1, 5: 2})
        with self.assertRaises(module.BatchError):
            module.accumulate_output_token_histogram(histogram, [5, "invalid"])
        source = SOURCE.read_text()
        self.assertIn('"output_token_histogram"', source)
        self.assertIn('"output_token_ids_complete"', source)


if __name__ == "__main__":
    unittest.main()
