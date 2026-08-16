import json
import tempfile
import unittest
from pathlib import Path

from phase_dispatcher import (
    AttentionPath,
    BatchShape,
    CacheBank,
    CONVERTED_LAYERS,
    ForwardMode,
    build_cost_model,
    build_result,
    dispatch_layer,
    verify_pinned_source_contract,
)


class PhaseDispatcherTest(unittest.TestCase):
    def test_pinned_source_contract(self):
        evidence = verify_pinned_source_contract()
        self.assertEqual(
            set(evidence),
            {
                "forward_batch",
                "ngram_worker",
                "ngram_info",
                "cuda_graph_runner",
                "gemma4_model",
                "swa_pool",
                "attention_backend",
            },
        )
        for item in evidence.values():
            self.assertEqual(len(item["sha256"]), 64)

    def test_target_verify_routes_only_logical_rows_to_proxy(self):
        shape = BatchShape(32, 384, 512, 12)
        plan = dispatch_layer(ForwardMode.TARGET_VERIFY, 11, shape)
        self.assertEqual(plan.primary_attention, AttentionPath.PROXY_LOCAL.value)
        self.assertEqual(plan.primary_cache_bank, CacheBank.PROXY_LOCAL.value)
        self.assertEqual(plan.shadow_kv_write_bank, CacheBank.STOCK.value)
        self.assertEqual(plan.logical_rows, 384)
        self.assertEqual(plan.padded_rows, 128)

    def test_all_other_modes_retain_stock_primary(self):
        modes = set(ForwardMode) - {ForwardMode.TARGET_VERIFY, ForwardMode.IDLE}
        for layer in CONVERTED_LAYERS:
            for mode in modes:
                tokens = 1
                shape = BatchShape(32, 32, 32, tokens)
                plan = dispatch_layer(mode, layer, shape)
                self.assertEqual(plan.primary_attention, AttentionPath.STOCK.value)
                self.assertEqual(
                    plan.shadow_kv_write_bank, CacheBank.PROXY_LOCAL.value
                )

    def test_unconverted_layer_is_always_stock(self):
        shape = BatchShape(32, 384, 384, 12)
        plan = dispatch_layer(ForwardMode.TARGET_VERIFY, 5, shape)
        self.assertEqual(plan.primary_attention, AttentionPath.STOCK.value)
        self.assertIsNone(plan.shadow_kv_write_bank)

    def test_target_shape_rejects_ambiguous_row_ownership(self):
        with self.assertRaises(ValueError):
            dispatch_layer(
                ForwardMode.TARGET_VERIFY,
                11,
                BatchShape(32, 383, 384, 12),
            )

    def test_cost_model_is_positive_but_below_campaign_gap(self):
        cost = build_cost_model()
        net_low, net_high = cost["net_savings_seconds_per_request_range"]
        self.assertGreater(net_low, 0)
        self.assertGreaterEqual(net_high, net_low)
        self.assertLess(
            max(cost["net_reduction_fraction_range"]),
            0.03,
        )
        self.assertGreater(
            min(cost["predicted_service_seconds_per_request_range"]),
            0.500119281574996,
        )

    def test_ordinary_decode_steps_charge_shadow_maintenance(self):
        zero = build_cost_model(0)
        mixed = build_cost_model(358)
        self.assertLess(
            mixed["net_savings_seconds_per_request_range"][0],
            zero["net_savings_seconds_per_request_range"][0],
        )

    def test_result_is_serializable_and_typed(self):
        result = build_result()
        self.assertEqual(result["classification"], "source_complete_candidate")
        self.assertFalse(result["scope"]["gpu_claimed"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(json.dumps(result))
            self.assertEqual(json.loads(path.read_text())["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
