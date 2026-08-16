from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

import numpy as np

import accuracy_redesign_analysis as analysis


ROOT = Path(__file__).resolve().parent
CANDIDATE = ROOT / "packed_m384_attention_fp32_partitioned.py"
RUNNER = ROOT / "accuracy_redesign_component_runner.py"
REPORT = ROOT / "artifacts/accuracy-redesign/OFFLINE_ACCURACY_ANALYSIS.json"


class AccuracyRedesignTest(unittest.TestCase):
    def test_fp8_quantizer_known_lattice(self) -> None:
        values = np.array(
            [0.0, 2.0**-9, 2.0**-8, 1.0, 1.0625, 448.0, 500.0],
            dtype=np.float32,
        )
        expected = np.array(
            [0.0, 2.0**-9, 2.0**-8, 1.0, 1.0, 448.0, 448.0],
            dtype=np.float32,
        )
        np.testing.assert_array_equal(analysis.e4m3fn(values), expected)

    def test_bf16_rounding_is_idempotent(self) -> None:
        values = np.linspace(-3.0, 3.0, 1001, dtype=np.float32)
        rounded = analysis.bf16(values)
        np.testing.assert_array_equal(analysis.bf16(rounded), rounded)

    def test_candidate_is_materially_new_fp32_partition(self) -> None:
        source = CANDIDATE.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertNotIn("packed_m384_attention_v2", source)
        self.assertIn("VALUE_BLOCK = 32", source)
        self.assertIn("dtype=torch.float32", source)
        self.assertIn("_partition_value_fp32_kernel", source)
        self.assertIn("_merge_value_fp32_kernel", source)
        self.assertNotIn("probability.to(values.dtype)", source)

    def test_runner_is_lifecycle_pure_and_new_candidate_only(self) -> None:
        tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        self.assertFalse(
            imported
            & {
                "subprocess",
                "paramiko",
                "grad_research.gpu_pool",
                "nebius",
            }
        )
        source = RUNNER.read_text(encoding="utf-8")
        self.assertNotIn("packed_m384_attention_v2", source)
        self.assertIn("token-margin-oracle", source)
        self.assertIn("high_precision_reference", source)
        self.assertIn("compiler_resources", source)

    def test_offline_report_falsifies_global_physical_gate(self) -> None:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        cases = {
            case["name"]: case for case in report["physical"]["cases"]
        }
        self.assertTrue(report["numerical_gate"]["sampled_proxy_pass"])
        self.assertTrue(
            cases["local"]["physically_credible_from_nonoverlapping_bound"]
        )
        self.assertFalse(
            cases["global"]["physically_credible_from_nonoverlapping_bound"]
        )
        self.assertGreater(
            cases["global"]["lower_bound_over_admitted_loss"], 10.0
        )


if __name__ == "__main__":
    unittest.main()
