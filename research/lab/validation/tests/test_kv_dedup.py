import unittest

import torch

from validation.qwen_kv_dedup_quality.transform import (
    apply_kv_head_deduplication,
    minimum_weight_distance_pairing,
)


class FakeAttention(torch.nn.Module):
    def __init__(self, k_rows: list[float], v_rows: list[float]) -> None:
        super().__init__()
        self.k_proj = torch.nn.Linear(1, len(k_rows), bias=False)
        self.v_proj = torch.nn.Linear(1, len(v_rows), bias=False)
        with torch.no_grad():
            self.k_proj.weight.copy_(torch.tensor(k_rows).reshape(-1, 1))
            self.v_proj.weight.copy_(torch.tensor(v_rows).reshape(-1, 1))


class FakeLayer(torch.nn.Module):
    def __init__(self, k_rows: list[float], v_rows: list[float]) -> None:
        super().__init__()
        self.self_attn = FakeAttention(k_rows, v_rows)


class FakeBackbone(torch.nn.Module):
    def __init__(self, layers: list[FakeLayer] | None = None) -> None:
        super().__init__()
        self.layers = torch.nn.ModuleList(layers or [self.default_layer()])

    @staticmethod
    def default_layer() -> FakeLayer:
        return FakeLayer([0.0, 10.0, 1.0, 11.0], [0.0, 20.0, 2.0, 22.0])


class FakeModel(torch.nn.Module):
    def __init__(self, layers: list[FakeLayer] | None = None) -> None:
        super().__init__()
        self.model = FakeBackbone(layers)
        self.config = type(
            "FakeConfig",
            (),
            {
                "num_hidden_layers": len(self.model.layers),
                "num_key_value_heads": 4,
                "head_dim": 1,
            },
        )()


class KvHeadDeduplicationTests(unittest.TestCase):
    def test_finds_minimum_joint_kv_weight_distance_pairing(self) -> None:
        k_weight = torch.tensor([[0.0], [10.0], [1.0], [11.0]])
        v_weight = torch.tensor([[0.0], [20.0], [2.0], [22.0]])

        pairing, distance = minimum_weight_distance_pairing(
            k_weight,
            v_weight,
            num_heads=4,
            head_dim=1,
        )

        self.assertEqual(pairing, ((0, 2), (1, 3)))
        self.assertEqual(distance, 10.0)

    def test_pairing_is_lexicographic_when_distances_tie(self) -> None:
        weights = torch.zeros((4, 1))

        pairing, distance = minimum_weight_distance_pairing(
            weights,
            weights,
            num_heads=4,
            head_dim=1,
        )

        self.assertEqual(pairing, ((0, 1), (2, 3)))
        self.assertEqual(distance, 0.0)

    def test_applies_pair_means_and_reports_exact_cache_reduction(self) -> None:
        model = FakeModel()

        summary = apply_kv_head_deduplication(
            model,
            baseline_checkpoint_bits_per_parameter=16,
        )

        attention = model.model.layers[0].self_attn
        self.assertTrue(
            torch.equal(attention.k_proj.weight[0], attention.k_proj.weight[2])
        )
        self.assertTrue(
            torch.equal(attention.k_proj.weight[1], attention.k_proj.weight[3])
        )
        self.assertTrue(
            torch.equal(attention.v_proj.weight[0], attention.v_proj.weight[2])
        )
        self.assertTrue(
            torch.equal(attention.v_proj.weight[1], attention.v_proj.weight[3])
        )
        self.assertEqual(summary.layer_pairings, (((0, 2), (1, 3)),))
        self.assertEqual(summary.original_kv_heads, 4)
        self.assertEqual(summary.unique_kv_heads, 2)
        self.assertEqual(summary.baseline_kv_cache_bytes_per_token, 16)
        self.assertEqual(summary.deduplicated_kv_cache_bytes_per_token, 8)
        self.assertEqual(summary.kv_cache_reduction_percent, 50.0)
        self.assertFalse(summary.runtime_kv_cache_deduplicated)
        self.assertTrue(summary.requires_custom_attention_alias_kernel)

    def test_transforms_only_lowest_relative_distance_layer_when_limited(self) -> None:
        low_distance = FakeLayer(
            [100.0, 200.0, 101.0, 201.0], [100.0, 200.0, 101.0, 201.0]
        )
        high_distance = FakeLayer([0.0, 10.0, 4.0, 14.0], [0.0, 10.0, 4.0, 14.0])
        model = FakeModel([high_distance, low_distance])
        unchanged = high_distance.self_attn.k_proj.weight.clone()

        summary = apply_kv_head_deduplication(
            model,
            baseline_checkpoint_bits_per_parameter=16,
            maximum_transformed_layers=1,
            maximum_pairs_per_transformed_layer=1,
        )

        self.assertEqual(summary.transformed_layer_indices, (1,))
        self.assertTrue(torch.equal(high_distance.self_attn.k_proj.weight, unchanged))
        self.assertEqual(summary.transformed_module_count, 2)
        self.assertEqual(summary.unique_kv_heads, 3)
        self.assertEqual(len(summary.layer_pairings[0]), 1)
        self.assertEqual(summary.kv_cache_reduction_percent, 12.5)

    def test_rejects_odd_kv_head_count(self) -> None:
        weights = torch.zeros((3, 1))

        with self.assertRaisesRegex(ValueError, "even"):
            minimum_weight_distance_pairing(
                weights,
                weights,
                num_heads=3,
                head_dim=1,
            )


if __name__ == "__main__":
    unittest.main()
