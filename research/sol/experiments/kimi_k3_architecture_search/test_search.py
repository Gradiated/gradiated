from __future__ import annotations

import json
import unittest
from pathlib import Path

from run_search import (
    build_work,
    cache_capacity_bytes,
    evaluate,
    max_capex_for_hourly_cost,
    mode_stages,
    ownership_hourly_cost,
    parameter_ledger,
)


ROOT = Path(__file__).parent


class ArchitectureSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = json.loads((ROOT / "spec.json").read_text())

    def test_model_geometry_reconciles_with_release(self) -> None:
        result = evaluate(self.spec)
        self.assertLess(result["parameter_reconciliation"]["relative_error"], 0.02)
        self.assertLess(result["parameter_reconciliation"]["routed_relative_error"], 0.005)

    def test_all_core_dimensions_are_128_aligned(self) -> None:
        model = self.spec["model"]
        for key in ("hidden", "latent_moe_hidden", "expert_intermediate", "q_lora_rank"):
            self.assertEqual(model[key] % 128, 0, key)
        self.assertEqual(model["attention_heads"] * model["kda_head_dim"] % 128, 0)

    def test_batch_reuse_reduces_weight_bytes_per_token(self) -> None:
        machine = self.spec["machines"][0]
        model = self.spec["model"]
        one = build_work(model, 1, 8192, machine).weight_bytes
        many = build_work(model, 128, 8192, machine).weight_bytes / 128
        self.assertLess(many, one / 5)

    def test_unique_experts_is_monotonic_and_bounded(self) -> None:
        machine = self.spec["machines"][0]
        model = self.spec["model"]
        values = [build_work(model, batch, 8192, machine).expected_unique_experts_per_layer for batch in (1, 32, 128, 512)]
        self.assertEqual(values, sorted(values))
        self.assertAlmostEqual(values[0], model["experts_per_token"], places=8)
        self.assertLessEqual(values[-1], model["experts"])

    def test_long_context_capacity_rejects_oversubscription(self) -> None:
        result = evaluate(self.spec)
        control_512 = next(row for row in result["rows"] if row["machine"] == "nvidia_dgx_b300_tp8" and row["concurrency"] == 512)
        self.assertFalse(control_512["feasible_capacity"])

    def test_calibration_reproduces_public_control(self) -> None:
        result = evaluate(self.spec)
        scale = result["calibration"]["latency_scales"]["nvidia_dgx_b300_tp8"]
        self.assertGreater(scale, 0)
        self.assertTrue(0.1 < scale < 10.0)

    def test_pipeline_modes_have_expected_stage_count(self) -> None:
        self.assertEqual(mode_stages("tensor_expert_parallel"), 1)
        self.assertEqual(mode_stages("tp2_pp4"), 4)
        self.assertEqual(mode_stages("pipeline8"), 8)

    def test_cache_grows_with_context(self) -> None:
        model = self.spec["model"]
        self.assertGreater(cache_capacity_bytes(model, 82308), cache_capacity_bytes(model, 8192))

    def test_parameter_ledger_names_are_unique(self) -> None:
        names = [row["name"] for row in parameter_ledger(self.spec["model"])]
        self.assertEqual(len(names), len(set(names)))

    def test_released_header_inventory_matches_bound_checkpoint(self) -> None:
        inventory = json.loads((ROOT / "evidence" / "tensor_inventory.json").read_text())
        self.assertEqual(inventory["revision"], self.spec["model"]["revision"])
        self.assertEqual(inventory["checkpoint_bytes"], self.spec["model"]["checkpoint_bytes"])
        self.assertEqual(inventory["shard_count"], 96)
        self.assertEqual(inventory["file_size_mismatches"], [])
        self.assertEqual(inventory["categories"]["routed_experts"]["storage_bytes"], 1_446_456_066_048)

    def test_economy_point_is_selected_under_stated_cost_scenario(self) -> None:
        result = evaluate(self.spec)
        selected = result["selected_design_to_cost_point"]
        self.assertEqual(selected["machine"], "streamtile_e12_economy")
        self.assertTrue(selected["speed_floor_pass"])
        control = next(
            row
            for row in result["rows"]
            if row["machine"] == "nvidia_dgx_b300_tp8" and row["concurrency"] == 128
        )
        self.assertLess(
            selected["target_owned_dollars_per_million_output_tokens"],
            control["b300_secure_cloud_dollars_per_million_output_tokens"],
        )

    def test_cost_increases_with_capex_and_break_even_inverts(self) -> None:
        machine = next(m for m in self.spec["machines"] if m["id"] == "streamtile_e12_economy")
        economics = self.spec["economics"]
        low = ownership_hourly_cost(machine, economics, 200_000)
        high = ownership_hourly_cost(machine, economics, 300_000)
        self.assertIsNotNone(low)
        self.assertIsNotNone(high)
        self.assertLess(low, high)
        reconstructed = max_capex_for_hourly_cost(machine, economics, high)
        self.assertAlmostEqual(reconstructed, 300_000, places=6)

    def test_tile_sram_matches_module_budget(self) -> None:
        for machine in self.spec["machines"]:
            if machine.get("bsp_group_tiles") is None:
                continue
            tile_total_mb = machine["tiles_per_chip"] * machine["sram_kb_per_tile"] / 1024.0
            self.assertAlmostEqual(tile_total_mb, machine["sram_mb_per_chip"])


if __name__ == "__main__":
    unittest.main()
