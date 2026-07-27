#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from offline_experiment import memory_evidence
from local_kv4_outlier_reference import (
    HEAD_DIM,
    VECTOR_BYTES,
    bf16_round,
    decode_vector,
    dense_attention_oracle,
    e5m2_decode,
    e5m2_encode,
    encode_vector,
    error_metrics,
    pack_cache,
    paged_attention,
)


class LocalKV4OutlierTests(unittest.TestCase):
    def test_e5m2_finite_extremes_and_ties(self):
        values = np.asarray([0.0, -0.0, 2**-16, 57344.0, -57344.0], np.float32)
        decoded = e5m2_decode(e5m2_encode(values))
        np.testing.assert_array_equal(decoded, values)
        with self.assertRaises(ValueError):
            e5m2_encode(np.asarray([np.inf], np.float32))

    def test_layout_determinism_and_residual_improves(self):
        vector = np.linspace(-3.0, 3.0, HEAD_DIM, dtype=np.float32)
        vector[[4, 9, 71, 200]] += np.asarray([8.0, -7.0, 6.0, -9.0])
        first = encode_vector(vector)
        second = encode_vector(vector)
        self.assertEqual(first.bytes.shape, (VECTOR_BYTES,))
        np.testing.assert_array_equal(first.bytes, second.bytes)
        base = decode_vector(first.bytes, corrected=False)
        corrected = decode_vector(first.bytes, corrected=True)
        reference = bf16_round(vector)
        self.assertLess(
            error_metrics(reference, corrected)["relative_l2"],
            error_metrics(reference, base)["relative_l2"],
        )

    def test_zero_and_low_channel_tie_break(self):
        zero = encode_vector(np.zeros(HEAD_DIM, np.float32))
        self.assertEqual(zero.outlier_channels, (0, 1, 2, 3))
        np.testing.assert_array_equal(decode_vector(zero.bytes), np.zeros(HEAD_DIM))

    def test_negative_slot_noop_gqa_masks_and_request_isolation(self):
        rng = np.random.default_rng(4)
        k = bf16_round(rng.standard_normal((5, 2, HEAD_DIM), dtype=np.float32))
        v = bf16_round(rng.standard_normal((5, 2, HEAD_DIM), dtype=np.float32))
        locations = np.asarray([0, 1, 2, 3, -1])
        cache_k, k_stats = pack_cache(k, locations, capacity=4)
        cache_v, v_stats = pack_cache(v, locations, capacity=4)
        self.assertEqual(k_stats["negative_slot_noops"], 1)
        self.assertEqual(v_stats["negative_slot_noops"], 1)
        q = bf16_round(rng.standard_normal((2, 4, HEAD_DIM), dtype=np.float32))
        common = {
            "q_request": np.asarray([0, 1]),
            "q_position": np.asarray([64, 1024]),
            "request_slots": [
                np.asarray([0, 1, -1]),
                np.asarray([2, 3, -1]),
            ],
            "key_positions": [
                np.asarray([63, 64, 64]),
                np.asarray([0, 1024, 1024]),
            ],
            "window": 1024,
        }
        oracle = dense_attention_oracle(
            q, dense_k=k[:4], dense_v=v[:4], **common
        )
        candidate = paged_attention(
            q,
            cache_k=cache_k,
            cache_v=cache_v,
            corrected=True,
            **common,
        )
        self.assertLess(error_metrics(oracle, candidate)["relative_l2"], 0.2)
        swapped = dict(common)
        swapped["request_slots"] = [
            np.asarray([2, 3, -1]),
            np.asarray([0, 1, -1]),
        ]
        crossed = paged_attention(
            q,
            cache_k=cache_k,
            cache_v=cache_v,
            corrected=True,
            **swapped,
        )
        self.assertGreater(float(np.max(np.abs(candidate - crossed))), 0.0)

    def test_complete_memory_interval_rejects_unchanged_launch(self):
        memory = memory_evidence()
        self.assertFalse(memory["fit"])
        self.assertGreater(
            memory["complete_required_interval_bytes"]["lower"],
            memory["physical_bytes"],
        )
        self.assertGreater(memory["static_allocator_deficit_interval_bytes"]["lower"], 0)

    def test_cuda_source_fuses_decode_and_preserves_fixed_contract(self):
        source = (
            Path(__file__).resolve().parent / "local_kv4_outlier_cuda.cu"
        ).read_text()
        for token in (
            "constexpr int kHeadDim = 256",
            "constexpr int kGroupSize = 64",
            "constexpr int kOutliers = 4",
            "constexpr int kVectorBytes = 144",
            "running_max",
            "running_sum",
            "accumulator",
            "query_head / group",
            "slot < 0",
            "visible_kv_stop",
        ):
            self.assertIn(token, source)
        self.assertNotIn("dequant_cache", source)


if __name__ == "__main__":
    unittest.main()
