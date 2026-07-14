import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from mla_microbench_control import (  # noqa: E402
    ABSOLUTE_TIMEOUT_SECONDS,
    DISK_GIB,
    DISK_HOURLY_RATE_USD,
    HOURLY_RATE_USD,
    IMAGE,
    PLATFORM,
    PRESET,
    build_container_command,
    build_host_bootstrap,
)
from vllm_mla_microbench import (  # noqa: E402
    E2E_SHARE_STATUS,
    SOURCE_SHA256,
    UNSCOPED_MIXED_TRACE_KERNEL_DURATION_SHARE,
    Candidate,
    exact_shapes,
    generate_candidates,
    prospective_e2e_gain,
    select_promotable_candidate,
)


class NebiusMlaMicrobenchTests(unittest.TestCase):
    def test_exact_shapes_bind_runtime_and_model_geometry(self):
        shapes = exact_shapes()
        self.assertEqual({shape.batch_size for shape in shapes}, {1, 8})
        self.assertEqual(
            {shape.context_tokens for shape in shapes},
            {8193, 8449, 8705, 8961, 9215},
        )
        for shape in shapes:
            self.assertEqual(shape.query_heads, 20)
            self.assertEqual(shape.kv_heads, 1)
            self.assertEqual(shape.kv_lora_rank, 512)
            self.assertEqual(shape.qk_rope_head_dim, 64)
            self.assertEqual(shape.query_width, 576)
            self.assertEqual(shape.value_width, 512)
            self.assertEqual(shape.model_value_head_dim, 256)
            self.assertEqual(shape.page_size, 16)
            self.assertEqual(shape.stock_kv_splits, 4)

    def test_candidate_grid_is_bounded_and_contains_stock(self):
        candidates = generate_candidates()
        self.assertEqual(len(candidates), len(set(candidates)))
        self.assertIn(Candidate(16, 32, 4, 2, 4), candidates)
        self.assertLessEqual(len(candidates), 80)
        self.assertTrue(all(value.block_h in {8, 16, 32} for value in candidates))
        self.assertTrue(all(value.block_n in {16, 32, 64} for value in candidates))
        self.assertTrue(all(value.num_warps in {2, 4, 8} for value in candidates))
        self.assertTrue(all(value.num_stages in {1, 2, 3} for value in candidates))
        self.assertTrue(all(value.num_kv_splits in {1, 2, 4, 8, 16} for value in candidates))
        self.assertFalse(any(value.block_n == 64 and value.num_stages == 2 for value in candidates))

    def test_source_and_unscoped_trace_diagnostic_are_pinned(self):
        self.assertEqual(SOURCE_SHA256, "cf4debbbbdf2245355177dd7be91c4ac75730a9207a10cd7dab6306a5c3bdec4")
        self.assertAlmostEqual(UNSCOPED_MIXED_TRACE_KERNEL_DURATION_SHARE, 0.3738261181394841)
        self.assertEqual(E2E_SHARE_STATUS, "unavailable_until_phase_aware_c8_trace_or_empirical_ab")

    def test_promotion_requires_scope_matched_e2e_share_and_both_gates(self):
        self.assertIsNone(prospective_e2e_gain(0.10))
        self.assertAlmostEqual(prospective_e2e_gain(0.20, 0.30), 0.06)
        rows = [
            {
                "candidate": Candidate(8, 32, 4, 2, 4).as_dict(),
                "correctness_pass": True,
                "hardware_legal": True,
                "component_time_reduction": 0.12,
            },
            {
                "candidate": Candidate(8, 64, 4, 1, 4).as_dict(),
                "correctness_pass": True,
                "hardware_legal": True,
                "component_time_reduction": 0.15,
            },
        ]
        self.assertIsNone(select_promotable_candidate(rows))
        selected = select_promotable_candidate(rows, measured_e2e_share=0.40)
        self.assertEqual(selected["candidate"]["block_n"], 64)
        self.assertGreaterEqual(selected["prospective_e2e_gain"], 0.05)

    def test_incorrect_or_illegal_candidates_cannot_promote(self):
        rows = [
            {
                "candidate": Candidate(8, 64, 4, 1, 4).as_dict(),
                "correctness_pass": False,
                "hardware_legal": True,
                "component_time_reduction": 0.50,
            },
            {
                "candidate": Candidate(4, 64, 8, 2, 4).as_dict(),
                "correctness_pass": True,
                "hardware_legal": False,
                "component_time_reduction": 0.50,
            },
        ]
        self.assertIsNone(select_promotable_candidate(rows))

    def test_control_uses_cheapest_same_gpu_geometry_and_bounded_cost(self):
        self.assertEqual(PLATFORM, "gpu-l40s-a")
        self.assertEqual(PRESET, "1gpu-8vcpu-32gb")
        self.assertEqual(DISK_GIB, 100)
        self.assertAlmostEqual(HOURLY_RATE_USD, 0.7492)
        self.assertAlmostEqual(DISK_HOURLY_RATE_USD, 0.0097222)
        self.assertEqual(ABSOLUTE_TIMEOUT_SECONDS, 2700)
        self.assertLess((HOURLY_RATE_USD + DISK_HOURLY_RATE_USD) * ABSOLUTE_TIMEOUT_SECONDS / 3600, 0.60)

    def test_bootstrap_and_container_pin_exact_runtime_without_weights(self):
        bootstrap = build_host_bootstrap()
        self.assertIn(IMAGE, bootstrap)
        self.assertIn("rm -f /etc/ld.so.conf.d/00-cuda-compat.conf", bootstrap)
        self.assertIn("torch.cuda.get_device_name", bootstrap)
        command = " ".join(build_container_command("a" * 64, 1783990000))
        self.assertIn(IMAGE, command)
        self.assertIn("/input/vllm_mla_microbench.py", command)
        self.assertIn("EXPERIMENT_SPEC_SHA256=" + "a" * 64, command)
        self.assertNotIn("model-awq", command)

    def test_remote_harness_captures_telemetry_and_content_addressed_artifact(self):
        source = (ROOT / "nebius" / "remote_mla_microbench.sh").read_text()
        self.assertIn("nvidia-smi --query-gpu=", source)
        self.assertIn("manifest.json", source)
        self.assertIn("sha256sum", source)
        self.assertIn("vllm_mla_microbench.py", source)
        self.assertIn("benchmark_sha256", source)

    def test_reference_masks_padding_on_nonmultiple_final_pages(self):
        source = (ROOT / "nebius" / "vllm_mla_microbench.py").read_text()
        self.assertIn("< sequence_lengths[:, None]", source)
        self.assertIn('masked_fill(~valid_tokens[:, None, :], float("-inf"))', source)

    def test_infrastructure_failure_opens_bounded_repair_window(self):
        source = (ROOT / "nebius" / "mla_microbench_control.py").read_text()
        self.assertIn("time.time() + 600", source)
        self.assertIn("repair-decision.json", source)
        self.assertIn("hold_for_repair_decision(output_dir, events, deadline)", source)


if __name__ == "__main__":
    unittest.main()
