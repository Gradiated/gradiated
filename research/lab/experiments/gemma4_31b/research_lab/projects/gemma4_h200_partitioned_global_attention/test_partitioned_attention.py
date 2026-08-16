from __future__ import annotations

import importlib.util
import math
import pathlib
import random
import unittest


PROJECT = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "partitioned_attention", PROJECT / "partitioned_attention.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FORCED_SPEC = importlib.util.spec_from_file_location(
    "forced_residency_attention", PROJECT / "forced_residency_attention.py"
)
assert FORCED_SPEC is not None and FORCED_SPEC.loader is not None
FORCED_MODULE = importlib.util.module_from_spec(FORCED_SPEC)
FORCED_SPEC.loader.exec_module(FORCED_MODULE)


def stable_attention(
    q: list[list[float]], k: list[list[float]], v: list[list[float]]
) -> list[list[float]]:
    outputs = []
    scale = math.sqrt(len(q[0]))
    for query_index, query in enumerate(q):
        scores = [
            sum(left * right for left, right in zip(query, key)) / scale
            for key in k[: query_index + 1]
        ]
        maximum = max(scores)
        weights = [math.exp(score - maximum) for score in scores]
        denominator = sum(weights)
        outputs.append(
            [
                sum(
                    weight * value[value_index]
                    for weight, value in zip(weights, v[: query_index + 1])
                )
                / denominator
                for value_index in range(len(v[0]))
            ]
        )
    return outputs


class PartitionedAttentionTests(unittest.TestCase):
    def test_value_partition_preserves_attention(self) -> None:
        generator = random.Random(20260722)
        q = [[generator.gauss(0, 1) for _ in range(8)] for _ in range(11)]
        k = [[generator.gauss(0, 1) for _ in range(8)] for _ in range(11)]
        v = [[generator.gauss(0, 1) for _ in range(8)] for _ in range(11)]

        control = stable_attention(q, k, v)
        left = stable_attention(q, k, [row[:4] for row in v])
        right = stable_attention(q, k, [row[4:] for row in v])
        candidate = [left_row + right_row for left_row, right_row in zip(left, right)]
        for control_row, candidate_row in zip(control, candidate):
            for control_value, candidate_value in zip(control_row, candidate_row):
                self.assertAlmostEqual(control_value, candidate_value, places=12)

    def test_transform_is_hash_bound_and_exact(self) -> None:
        pinned_source = PROJECT / "inputs" / "extend_attention.v0.5.13.py"
        transformed = MODULE.transform_source(pinned_source.read_bytes()).decode()
        self.assertIn("VALUE_SPLITS = 2 if partition_global_value else 1", transformed)
        self.assertIn("cur_value_split * BLOCK_DV_SLICE", transformed)
        self.assertIn(
            "acc = tl.zeros([BLOCK_M, BLOCK_DV_SLICE], dtype=tl.float32)",
            transformed,
        )
        self.assertIn(
            "triton.cdiv(max_len_extend, BLOCK_M) * VALUE_SPLITS", transformed
        )
        self.assertEqual(transformed.count("global_head512_value_split2"), 1)

    def test_transform_rejects_unbound_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "pinned_extend_attention_source_mismatch"):
            MODULE.transform_source(b"not the pinned source")

    def test_forced_residency_transform_is_exact(self) -> None:
        pinned_source = PROJECT / "inputs" / "extend_attention.v0.5.13.py"
        transformed = FORCED_MODULE.transform_source(pinned_source.read_bytes()).decode()
        self.assertIn("kernel_maxnreg = 128 if force_global_residency else None", transformed)
        self.assertIn("maxnreg=kernel_maxnreg", transformed)
        self.assertEqual(transformed.count("global_head512_maxnreg128"), 1)


if __name__ == "__main__":
    unittest.main()
