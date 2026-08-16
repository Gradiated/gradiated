#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from global_tiered_kv4_reference import (
    HEAD_DIM,
    OLD_VECTOR_BYTES,
    bf16_round,
    decode_old_vector,
    e5m2_decode,
    e5m2_encode,
    encode_old_vector,
    error_metrics,
    mixed_tier_paged_attention,
    produce_cache,
)
from offline_experiment import memory_evidence
from sglang_global_tiered_kv4 import (
    OLD_CAPACITY,
    PEAK_PHYSICAL_ROWS,
    RECENT_CAPACITY,
    build_locked_c32_layout,
)


class GlobalTieredKV4Tests(unittest.TestCase):
    def test_scale_nibbles_saturation_and_unique_ordered_outliers(self):
        vector = np.linspace(-2.0, 2.0, HEAD_DIM, dtype=np.float32)
        injected = [3, 67, 130, 199, 260, 333, 401, 511]
        vector[injected] += np.asarray([9, -10, 11, -12, 13, -14, 15, -16])
        first = encode_old_vector(vector)
        second = encode_old_vector(vector)
        self.assertEqual(first.bytes.shape, (OLD_VECTOR_BYTES,))
        np.testing.assert_array_equal(first.bytes, second.bytes)
        self.assertEqual(len(set(first.outlier_channels)), 8)
        self.assertEqual(first.outlier_channels, second.outlier_channels)
        self.assertGreater(first.saturation_count, 0)
        reference = bf16_round(vector)
        base = decode_old_vector(first.bytes, corrected=False)
        corrected = decode_old_vector(first.bytes, corrected=True)
        self.assertLess(
            error_metrics(reference, corrected)["relative_l2"],
            error_metrics(reference, base)["relative_l2"],
        )

    def test_e5m2_extremes_ties_and_nonfinite_guard(self):
        values = np.asarray([0.0, -0.0, 2**-16, 57344.0, -57344.0], np.float32)
        np.testing.assert_array_equal(e5m2_decode(e5m2_encode(values)), values)
        with self.assertRaises(ValueError):
            e5m2_encode(np.asarray([np.inf], np.float32))

    def test_empty_old_and_1023_1024_1025_transition(self):
        rng = np.random.default_rng(7)
        for length, expected_old in ((1023, 0), (1024, 0), (1025, 1)):
            keys = bf16_round(
                rng.standard_normal((length, 1, HEAD_DIM), dtype=np.float32) * 0.1
            )
            values = bf16_round(
                rng.standard_normal((length, 1, HEAD_DIM), dtype=np.float32) * 0.1
            )
            cache = produce_cache(
                keys,
                values,
                owners=np.zeros(length, np.int32),
                positions=np.arange(length),
            )
            query = bf16_round(
                rng.standard_normal((1, 1, HEAD_DIM), dtype=np.float32) * 0.1
            )
            output = mixed_tier_paged_attention(
                query,
                q_request=np.asarray([0]),
                q_position=np.asarray([length - 1]),
                cache=cache,
                request_slots=[np.arange(length)],
            )
            self.assertTrue(np.isfinite(output).all())
            self.assertEqual(max(0, length - 1024), expected_old)

    def test_request_isolation_and_padded_rows(self):
        rng = np.random.default_rng(8)
        keys = bf16_round(
            rng.standard_normal((4, 1, HEAD_DIM), dtype=np.float32) * 0.1
        )
        values = bf16_round(
            rng.standard_normal((4, 1, HEAD_DIM), dtype=np.float32) * 0.1
        )
        cache = produce_cache(
            keys,
            values,
            owners=np.asarray([0, 0, 1, 1]),
            positions=np.asarray([0, 1024, 0, 1024]),
        )
        query = bf16_round(
            rng.standard_normal((2, 2, HEAD_DIM), dtype=np.float32) * 0.1
        )
        common = {
            "q_request": np.asarray([0, 1]),
            "q_position": np.asarray([1024, 1024]),
            "cache": cache,
        }
        output = mixed_tier_paged_attention(
            query,
            request_slots=[
                np.asarray([0, 1, -1]),
                np.asarray([2, 3, -1]),
            ],
            **common,
        )
        self.assertTrue(np.isfinite(output).all())
        with self.assertRaises(ValueError):
            mixed_tier_paged_attention(
                query,
                request_slots=[
                    np.asarray([2, 3, -1]),
                    np.asarray([0, 1, -1]),
                ],
                **common,
            )

    def test_locked_c32_physical_ownership_layout(self):
        layout = build_locked_c32_layout(4571)
        self.assertEqual(layout.kv_indptr.shape, (33,))
        self.assertEqual(layout.kv_indices.size, 32 * 4571)
        self.assertEqual(layout.old_physical.size, OLD_CAPACITY)
        self.assertEqual(layout.recent_physical.size, 32 * 1024)
        self.assertEqual(
            np.unique(layout.kv_indices).size,
            PEAK_PHYSICAL_ROWS,
        )
        self.assertLess(layout.recent_physical.size, RECENT_CAPACITY)
        self.assertTrue(np.all(layout.old_locations[layout.old_physical] >= 0))
        self.assertTrue(
            np.all(layout.recent_locations[layout.recent_physical] >= 0)
        )

    def test_complete_memory_bound_improves_but_does_not_fit(self):
        memory = memory_evidence()
        self.assertGreater(memory["bytes_saved_exact_before_rounding"], 1_500_000_000)
        self.assertGreater(memory["lower_deficit_reduction_fraction"], 0.39)
        self.assertFalse(memory["complete_fit"])
        self.assertGreater(memory["physical_deficit_interval_bytes"]["lower"], 0)

    def test_cuda_source_is_one_mixed_online_softmax_pass(self):
        source = (
            Path(__file__).resolve().parent / "global_tiered_kv4_cuda.cu"
        ).read_text()
        for token in (
            "constexpr int kHeadDim = 512",
            "constexpr int kGroupSize = 64",
            "constexpr int kOutliers = 8",
            "constexpr int kRecentTokens = 1024",
            "mixed_tier_paged_attention_kernel",
            "use_recent",
            "recent_locations[physical]",
            "old_locations[physical]",
            "running_max",
            "running_sum",
            "accumulator",
            "query_head / (query_heads / kv_heads)",
            "physical < 0",
        ):
            self.assertIn(token, source)
        self.assertNotIn("dequant_cache", source)


if __name__ == "__main__":
    unittest.main()
