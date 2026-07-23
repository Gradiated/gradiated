#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import json
import pathlib
import tempfile
import unittest


PROJECT = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "operation_overlap_harness", PROJECT / "operation_overlap_harness.py"
)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class OfflineHarnessTest(unittest.TestCase):
    def test_distribution_and_decision_metric(self) -> None:
        result = HARNESS.distribution([3.0, 1.0, 2.0, 2.0, 7.0])
        self.assertEqual(result["median_ms"], 2.0)
        self.assertEqual(result["p90_ms"], 7.0)
        attention = 4.0
        linear = 6.0
        concurrent = 7.0
        efficiency = (attention + linear - concurrent) / min(
            attention, linear
        )
        self.assertEqual(efficiency, 0.75)

    def test_bound_input_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            input_path = root / "input.json"
            input_path.write_text('{"pass":true}\n')
            binding = {
                "pass": True,
                "attention": {"query_rows": 2048},
                "fp8_linear": {"shape_mkn": [2048, 5376, 43008]},
                "inputs": {
                    "root": str(root),
                    "paths": {"fp8_map": input_path.name},
                    "sha256": {
                        "fp8_map": hashlib.sha256(
                            input_path.read_bytes()
                        ).hexdigest()
                    },
                },
            }
            binding_path = root / "binding.json"
            binding_path.write_text(json.dumps(binding))
            HARNESS.validate_binding(binding_path)
            input_path.write_bytes(input_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                RuntimeError, "bound_input_identity_mismatch"
            ):
                HARNESS.validate_binding(binding_path)


if __name__ == "__main__":
    unittest.main()
