import math
import types
import unittest

from tkcc import costmodel, prepare, scoring, workload
from tkcc.patcher import Patcher


class PatcherTest(unittest.TestCase):
    def test_undo_restores_instance_class_and_module_attributes(self):
        class Layer:
            def forward(self):
                return "stock"

        layer = Layer()
        module = types.ModuleType("fake_kernels")
        module.kernel = lambda: "stock"
        patch = Patcher()
        patch(layer, "forward", lambda: "fast")
        patch(Layer, "extra", 3)
        patch(module, "kernel", lambda: "fast")
        self.assertEqual(layer.forward(), "fast")
        self.assertEqual(module.kernel(), "fast")
        self.assertEqual(patch.undo(), 3)
        self.assertEqual(layer.forward(), "stock")
        self.assertFalse(hasattr(Layer, "extra"))
        self.assertEqual(module.kernel(), "stock")
        self.assertNotIn("forward", layer.__dict__)

    def test_repeated_patch_of_same_attribute_unwinds_in_order(self):
        holder = types.SimpleNamespace(value=1)
        patch = Patcher()
        patch(holder, "value", 2)
        patch(holder, "value", 3)
        patch.undo()
        self.assertEqual(holder.value, 1)


class ScoringTest(unittest.TestCase):
    reference = {"tokens": [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]] * 4, "logprobs": [[-0.1] * 10] * 4}

    def test_identical_outputs_pass(self):
        result = scoring.compare_outputs(self.reference, self.reference)
        self.assertTrue(result["pass"])
        self.assertEqual(result["mean_prefix_fraction"], 1.0)

    def test_late_divergence_passes_but_early_divergence_fails(self):
        late = {"tokens": [[1, 2, 3, 4, 5, 6, 7, 8, 0, 0]] * 4, "logprobs": [[-0.1] * 10] * 4}
        self.assertTrue(scoring.compare_outputs(self.reference, late)["pass"])
        early = {"tokens": [[1, 0, 0, 0, 0, 0, 0, 0, 0, 0]] * 4, "logprobs": [[-0.1] * 10] * 4}
        self.assertFalse(scoring.compare_outputs(self.reference, early)["pass"])

    def test_logprob_drift_and_nan_fail(self):
        drift = {"tokens": self.reference["tokens"], "logprobs": [[-0.5] * 10] * 4}
        self.assertFalse(scoring.compare_outputs(self.reference, drift)["pass"])
        nan = {"tokens": self.reference["tokens"], "logprobs": [[math.nan] * 10] * 4}
        self.assertFalse(scoring.compare_outputs(self.reference, nan)["pass"])

    def test_geomean_speedup(self):
        base = {"1": {"tps_per_user": 100.0}, "8": {"tps_per_user": 50.0}}
        measured = {"1": {"tps_per_user": 200.0}, "8": {"tps_per_user": 50.0}}
        self.assertAlmostEqual(scoring.geomean_speedup(measured, base), math.sqrt(2))


class PrepareTest(unittest.TestCase):
    config = {
        "text_config": {
            "num_hidden_layers": 40,
            "compress_ratios": [0, 0] + [2] * 18 + [1] * 20 + [0, 0, 0],
            "kv_source_layer_ids": [2, 8, 14, 20],
            "index_source_layer_ids": [2, 8, 14, 20, 24, 28, 32, 36],
            "candidate_source_layer_id": 20,
            "candidate_topk_blocks": 2048,
            "engram_layer_ids": [1, 14],
            "engram_num_embeddings": [10, 20],
            "dspark_target_layer_ids": [37, 38, 39],
        }
    }

    def test_truncation_filters_cross_layer_references(self):
        text = prepare.truncate_text_config(self.config, 12)["text_config"]
        self.assertEqual(text["num_hidden_layers"], 12)
        self.assertEqual(len(text["compress_ratios"]), 15)
        self.assertEqual(text["kv_source_layer_ids"], [2, 8])
        self.assertEqual(text["index_source_layer_ids"], [2, 8])
        self.assertEqual(text["candidate_source_layer_id"], -1)
        self.assertEqual(text["engram_layer_ids"], [1])
        self.assertEqual(text["engram_num_embeddings"], [10])
        self.assertEqual(text["dspark_target_layer_ids"], [9, 10, 11])
        self.assertEqual(self.config["text_config"]["num_hidden_layers"], 40)

    def test_keep_weight(self):
        self.assertTrue(prepare.keep_weight("layers.11.attn.wq_a.weight", 12))
        self.assertFalse(prepare.keep_weight("layers.12.attn.wq_a.weight", 12))
        self.assertTrue(prepare.keep_weight("embed.weight", 12))
        self.assertTrue(prepare.keep_weight("mtp.0.layers.0.x", 12))

    def test_rejects_invalid_layer_count(self):
        with self.assertRaises(ValueError):
            prepare.truncate_text_config(self.config, 0)


class WorkloadTest(unittest.TestCase):
    def test_prompts_have_exact_length_and_are_deterministic(self):
        corpus = workload.Corpus(("alpha beta gamma " * 50, "delta epsilon " * 80))
        encode = lambda text: [len(word) for word in text.split()]
        first = workload.build_prompt_token_ids(corpus, encode, 3, 300, seed=7)
        second = workload.build_prompt_token_ids(corpus, encode, 3, 300, seed=7)
        self.assertEqual(first, second)
        self.assertTrue(all(len(p) == 300 for p in first))

    def test_random_tokens_avoid_reserved_ids(self):
        prompts = workload.random_token_ids(2, 500, 10, seed=1, reserved=[0, 1])
        self.assertTrue(all(t >= 2 for p in prompts for t in p))


class CostModelTest(unittest.TestCase):
    model = costmodel.ModelSpec()
    chip = costmodel.B300_SPEC

    def test_zipf_routing_sums_to_topk(self):
        for skew in (0.0, 0.5, 1.2):
            pi = costmodel.zipf_routing(384, 6, skew)
            self.assertAlmostEqual(sum(pi), 6, places=3)
            self.assertTrue(all(0 <= p <= 1 for p in pi))

    def test_expected_max_of_identical_point_masses(self):
        self.assertAlmostEqual(costmodel.expected_max([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]]), 2.0)

    def test_ep_imbalance_exceeds_tp_share_at_batch_one(self):
        pi = costmodel.zipf_routing(384, 6, 0.0)
        max_unique, _ = costmodel.expert_load(pi, 1, 4, 6)
        self.assertGreater(max_unique, 6 / 4)
        self.assertLess(max_unique, 6)

    def test_skew_increases_ep_imbalance(self):
        flat, _ = costmodel.expert_load(costmodel.zipf_routing(384, 6, 0.0), 32, 4, 6)
        skewed, _ = costmodel.expert_load(costmodel.zipf_routing(384, 6, 1.0), 32, 4, 6)
        self.assertGreater(skewed / costmodel.unique_experts(costmodel.zipf_routing(384, 6, 1.0), 32) * 4,
                           flat / costmodel.unique_experts(costmodel.zipf_routing(384, 6, 0.0), 32) * 4)

    def test_single_chip_is_inadmissible_and_tp4_wins_batch_one(self):
        schemes = costmodel.enumerate_schemes(self.model, self.chip, 4)
        self.assertTrue(all(s.chips >= 2 for s in schemes))
        ranked = costmodel.rank_schemes(self.model, self.chip, 1, 32768, 4)
        self.assertEqual((ranked[0].scheme.chips, ranked[0].scheme.attn_tp, ranked[0].scheme.moe), (4, 4, "tp"))

    def test_more_tokens_take_longer(self):
        scheme = costmodel.Scheme(4, 4, "tp")
        small = costmodel.decode_step(self.model, self.chip, scheme, 1, 32768)
        large = costmodel.decode_step(self.model, self.chip, scheme, 32, 32768)
        self.assertGreater(large.step_s, small.step_s)
        self.assertGreater(large.aggregate_tps, small.aggregate_tps)


if __name__ == "__main__":
    unittest.main()


class RelativeGateTest(unittest.TestCase):
    def test_gate_is_relative_to_stock_self_agreement(self):
        ref = {"tokens": [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]] * 4, "logprobs": [[-0.1] * 10] * 4}
        noisy = {"tokens": [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]] * 2 + [[1, 2, 0, 0, 0, 0, 0, 0, 0, 0]] * 2,
                 "logprobs": [[-0.12] * 10] * 4}
        self.assertFalse(scoring.compare_outputs(ref, noisy)["pass"])
        stock = {"prefix_match_rate": 0.6, "mean_prefix_fraction": 0.5, "mean_abs_logprob_delta": 0.03}
        self.assertTrue(scoring.compare_outputs(ref, noisy, stock)["pass"])
        garbage = {"tokens": [[0] * 10] * 4, "logprobs": [[-3.0] * 10] * 4}
        self.assertFalse(scoring.compare_outputs(ref, garbage, stock)["pass"])
