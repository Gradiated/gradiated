import unittest

from validation.qwen_vllm_repeatability.results import (
    CampaignAcceptance,
    RunContext,
    normalize_vllm_result,
    run_result_from_mapping,
    summarize_campaign,
)


PROMPTS = tuple(
    {
        "request_id": f"qwen-fixed-{index}",
        "prompt_sha256": f"{index:064x}",
        "input_tokens": 128,
    }
    for index in range(8)
)


def raw_result(output_throughput: float = 32.0) -> dict:
    ttfts = [0.1 + index / 100 for index in range(8)]
    itls = [[0.02] * 31 for _ in range(8)]
    return {
        "duration": 8.0,
        "completed": 8,
        "failed": 0,
        "total_input_tokens": 1024,
        "total_output_tokens": 256,
        "request_throughput": 1.0,
        "output_throughput": output_throughput,
        "total_token_throughput": 160.0,
        "input_lens": [128] * 8,
        "output_lens": [32] * 8,
        "ttfts": ttfts,
        "itls": itls,
        "start_times": [1000.0 + index / 1000 for index in range(8)],
        "generated_texts": [f"output {index}" for index in range(8)],
        "errors": [""] * 8,
        "p95_ttft_ms": 170.0,
        "p95_tpot_ms": 20.0,
    }


class ResultTests(unittest.TestCase):
    def test_normalizes_and_preserves_every_request_measurement(self) -> None:
        context = RunContext(
            pair_id="c8-r1",
            concurrency=8,
            repeat_index=1,
            state="cold_engine",
            prompt_content_id="f" * 64,
            source_content_id="e" * 64,
            isolated=True,
        )

        result = normalize_vllm_result(raw_result(), PROMPTS, context)

        self.assertTrue(result.accepted)
        self.assertEqual(len(result.requests), 8)
        self.assertEqual(result.requests[3].request_id, "qwen-fixed-3")
        self.assertEqual(result.requests[3].output_tokens, 32)
        self.assertAlmostEqual(result.requests[3].tpot_seconds, 0.02)
        self.assertEqual(result.requests[3].generated_text, "output 3")
        self.assertAlmostEqual(result.requests[7].queue_seconds, 0.007)
        self.assertAlmostEqual(result.p95_ttft_ms, 173.15)
        self.assertEqual(run_result_from_mapping(result.to_mapping()), result)

    def test_fails_closed_on_partial_or_malformed_detailed_output(self) -> None:
        context = RunContext(
            pair_id="c8-r1",
            concurrency=8,
            repeat_index=1,
            state="cold_engine",
            prompt_content_id="f" * 64,
            source_content_id="e" * 64,
            isolated=True,
        )
        raw = raw_result()
        raw["output_lens"][4] = 31

        result = normalize_vllm_result(raw, PROMPTS, context)

        self.assertFalse(result.accepted)
        self.assertIn("request 4 output_tokens", result.rejection_reasons)

    def test_campaign_acceptance_requires_complete_isolated_low_dispersion_cells(
        self,
    ) -> None:
        runs = []
        for concurrency in (1, 2, 4, 8):
            for repeat_index in range(1, 6):
                for state in ("cold_engine", "warm_engine"):
                    context = RunContext(
                        pair_id=f"c{concurrency}-r{repeat_index}",
                        concurrency=concurrency,
                        repeat_index=repeat_index,
                        state=state,
                        prompt_content_id="f" * 64,
                        source_content_id="e" * 64,
                        isolated=True,
                    )
                    runs.append(
                        normalize_vllm_result(
                            raw_result(32.0 + repeat_index / 100), PROMPTS, context
                        )
                    )

        report = summarize_campaign(
            runs,
            expected_concurrency=(1, 2, 4, 8),
            minimum_repeats=5,
            primary_metrics=(
                "output_throughput",
                "p95_ttft_ms",
                "p95_tpot_ms",
            ),
            maximum_cv=0.1,
            maximum_relative_ci_half_width=0.15,
        )

        self.assertEqual(report.acceptance, CampaignAcceptance.PASS)
        self.assertFalse(report.claims["provider_comparison"])
        self.assertFalse(report.claims["gpu_performance"])
        self.assertFalse(report.claims["simulator_calibration"])
        self.assertFalse(report.claims["cost_per_token"])

    def test_campaign_summary_fails_closed_instead_of_crashing_on_zero_metrics(
        self,
    ) -> None:
        context = RunContext(
            pair_id="c1-r1",
            concurrency=1,
            repeat_index=1,
            state="cold_engine",
            prompt_content_id="f" * 64,
            source_content_id="e" * 64,
            isolated=False,
        )
        malformed = normalize_vllm_result({}, PROMPTS, context)

        report = summarize_campaign(
            [malformed],
            expected_concurrency=(1, 2, 4, 8),
            minimum_repeats=5,
            primary_metrics=("output_throughput",),
            maximum_cv=0.1,
            maximum_relative_ci_half_width=0.15,
        )

        self.assertEqual(report.acceptance, CampaignAcceptance.FAIL)


if __name__ == "__main__":
    unittest.main()
