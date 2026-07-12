import unittest

from validation.qwen_vllm_repeatability.schema import CampaignSpec, SpecError


def valid_mapping() -> dict:
    return {
        "schema_version": 1,
        "campaign_id": "qwen3-0.6b-vllm-cpu-repeatability-v1",
        "schedule_seed": 20260712,
        "concurrency_levels": [1, 2, 4, 8],
        "repeat_pairs": 5,
        "workload": {
            "dataset_seed": 0,
            "num_prompts": 8,
            "input_tokens": 128,
            "output_tokens": 32,
            "request_rate": "inf",
            "ignore_eos": True,
            "prompt_content_id": "a" * 64,
        },
        "engine": {
            "python": "/tmp/venv/bin/python",
            "checkout": "/tmp/vllm",
            "expected_revision": "b" * 40,
            "expected_version": "0.1.dev1",
            "expected_tracked_diff_sha256": "c" * 64,
            "expected_installed_binary_sha256": "f" * 64,
            "model_path": "/tmp/model",
            "served_model_name": "qwen3-0.6b-local",
            "model_revision": "d" * 40,
            "checkpoint_sha256": "e" * 64,
            "tokenizer_revision": "d" * 40,
            "host": "127.0.0.1",
            "port": 18731,
            "environment": {
                "VLLM_CPU_KVCACHE_SPACE": "4",
                "VLLM_CPU_OMP_THREADS_BIND": "0-9",
            },
            "server_arguments": ["--dtype", "bfloat16"],
        },
        "isolation": {
            "cooldown_seconds": 15,
            "startup_timeout_seconds": 300,
            "quiet_process_cpu_percent": 20.0,
            "minimum_available_memory_bytes": 12_000_000_000,
            "require_ac_power": True,
            "require_no_thermal_warning": True,
            "retry_wait_seconds": 15,
            "maximum_isolation_retries_per_pair": 40,
            "quiet_consecutive_samples": 3,
            "quiet_sample_interval_seconds": 5,
            "preflight_wait_timeout_seconds": 1800,
        },
        "acceptance": {
            "minimum_repeats_per_cell": 5,
            "maximum_coefficient_of_variation": 0.1,
            "maximum_relative_ci_half_width": 0.15,
            "primary_metrics": [
                "output_throughput",
                "p95_ttft_ms",
                "p95_tpot_ms",
            ],
        },
        "claim_gates": {
            "provider_comparison": False,
            "gpu_performance": False,
            "simulator_calibration": False,
            "cost_per_token": False,
        },
    }


class CampaignSpecTests(unittest.TestCase):
    def test_loads_exact_frozen_campaign_contract(self) -> None:
        spec = CampaignSpec.from_mapping(valid_mapping())

        self.assertEqual(spec.concurrency_levels, (1, 2, 4, 8))
        self.assertEqual(spec.repeat_pairs, 5)
        self.assertEqual(spec.workload.geometry, (8, 128, 32))
        self.assertEqual(spec.expected_run_count, 40)

    def test_rejects_geometry_drift(self) -> None:
        mapping = valid_mapping()
        mapping["workload"]["input_tokens"] = 127

        with self.assertRaisesRegex(SpecError, "8x128x32"):
            CampaignSpec.from_mapping(mapping)

    def test_rejects_missing_repeatability_budget(self) -> None:
        mapping = valid_mapping()
        mapping["repeat_pairs"] = 4

        with self.assertRaisesRegex(SpecError, "five"):
            CampaignSpec.from_mapping(mapping)

    def test_rejects_promoted_claim(self) -> None:
        mapping = valid_mapping()
        mapping["claim_gates"]["simulator_calibration"] = True

        with self.assertRaisesRegex(SpecError, "claim gates"):
            CampaignSpec.from_mapping(mapping)


if __name__ == "__main__":
    unittest.main()
