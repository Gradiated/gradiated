from __future__ import annotations

import unittest
from pathlib import Path

from model import component_model, expected_unique_experts, load_spec, roofline_rows


ROOT = Path(__file__).parent


class WorkloadModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_spec(ROOT / "workload.json")

    def test_layer_composition_is_complete(self) -> None:
        model = self.spec["model"]
        self.assertEqual(model["kda_layers"] + model["mla_layers"], model["total_layers"])
        self.assertEqual(model["total_layers"] - model["dense_layers"], 92)

    def test_expected_unique_experts_is_bounded(self) -> None:
        model = self.spec["model"]
        one = expected_unique_experts(model["experts"], model["selected_experts"], 1)
        sixteen = expected_unique_experts(model["experts"], model["selected_experts"], 16)
        self.assertAlmostEqual(one, model["selected_experts"])
        self.assertGreater(sixteen, one)
        self.assertLessEqual(sixteen, model["experts"])

    def test_mla_work_grows_with_context_and_kda_does_not(self) -> None:
        short = {row["name"]: row for row in component_model(self.spec, 8192, 1)}
        long = {row["name"]: row for row in component_model(self.spec, 131072, 1)}
        self.assertGreater(long["mla_context_attention"]["macs_per_token"], short["mla_context_attention"]["macs_per_token"])
        self.assertEqual(long["kda_recurrence"]["macs_per_token"], short["kda_recurrence"]["macs_per_token"])
        self.assertEqual(long["kda_recurrence"]["kda_state_bytes_per_sequence"], short["kda_recurrence"]["kda_state_bytes_per_sequence"])

    def test_batch_reduces_weight_bytes_per_token(self) -> None:
        rows, _ = roofline_rows(self.spec)
        batch_one = next(row for row in rows if row["context"] == 8192 and row["batch"] == 1 and row["scenario"] == "external_state")
        batch_sixteen = next(row for row in rows if row["context"] == 8192 and row["batch"] == 16 and row["scenario"] == "external_state")
        self.assertLess(batch_sixteen["weight_gb_per_token"], batch_one["weight_gb_per_token"])

    def test_local_state_removes_kda_from_external_traffic(self) -> None:
        rows, _ = roofline_rows(self.spec)
        external = next(row for row in rows if row["context"] == 8192 and row["batch"] == 1 and row["scenario"] == "external_state")
        local = next(row for row in rows if row["context"] == 8192 and row["batch"] == 1 and row["scenario"] == "local_kda_state")
        self.assertGreater(external["external_gb_per_token"], local["external_gb_per_token"])
        self.assertGreater(local["local_gb_per_token"], 0)


if __name__ == "__main__":
    unittest.main()
