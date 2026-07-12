import unittest
from types import SimpleNamespace

import torch

from validation.qwen_kv_recovery.transform import (
    LowRankAdapterLinear,
    apply_recovery_structure,
    assert_exact_kv_sharing,
)


class ToyAttention(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.k_proj = torch.nn.Linear(4, 8, bias=False)
        self.v_proj = torch.nn.Linear(4, 8, bias=False)
        self.q_proj = torch.nn.Linear(4, 8, bias=False)
        self.o_proj = torch.nn.Linear(8, 4, bias=False)


class ToyLayer(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.self_attn = ToyAttention()


class ToyModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.model = SimpleNamespace(
            layers=torch.nn.ModuleList([ToyLayer(), ToyLayer()])
        )
        self.layers = self.model.layers
        self.config = SimpleNamespace(
            num_hidden_layers=2,
            num_key_value_heads=4,
            head_dim=2,
        )


class RecoveryTransformTests(unittest.TestCase):
    def test_keeps_all_pairs_exact_and_only_adapters_trainable(self) -> None:
        torch.manual_seed(4)
        model = ToyModel()

        summary = apply_recovery_structure(
            model,
            original_kv_heads=4,
            unique_kv_heads=2,
            adapter_rank=2,
            adapter_alpha=2.0,
        )

        self.assertEqual(summary.layer_count, 2)
        self.assertEqual(summary.trainable_parameter_count, 96)
        self.assertEqual(summary.deduplicated_projection_parameter_count, 64)
        self.assertTrue(summary.adapter_b_zero_at_initialization)
        self.assertTrue(assert_exact_kv_sharing(model, summary.layer_pairings))
        self.assertIsInstance(model.layers[0].self_attn.q_proj, LowRankAdapterLinear)
        self.assertIsInstance(model.layers[0].self_attn.o_proj, LowRankAdapterLinear)
        trainable = {
            name for name, value in model.named_parameters() if value.requires_grad
        }
        self.assertEqual(
            trainable,
            {
                "layers.0.self_attn.q_proj.adapter_a",
                "layers.0.self_attn.q_proj.adapter_b",
                "layers.0.self_attn.o_proj.adapter_a",
                "layers.0.self_attn.o_proj.adapter_b",
                "layers.1.self_attn.q_proj.adapter_a",
                "layers.1.self_attn.q_proj.adapter_b",
                "layers.1.self_attn.o_proj.adapter_a",
                "layers.1.self_attn.o_proj.adapter_b",
            },
        )

    def test_zero_initialized_adapter_preserves_structural_model_output(self) -> None:
        linear = torch.nn.Linear(4, 3, bias=False)
        wrapper = LowRankAdapterLinear(linear, rank=2, alpha=2.0)
        inputs = torch.randn(2, 4)

        self.assertTrue(torch.equal(wrapper(inputs), linear(inputs)))

    def test_adapter_update_does_not_break_kv_pair_equality(self) -> None:
        torch.manual_seed(5)
        model = ToyModel()
        summary = apply_recovery_structure(
            model,
            original_kv_heads=4,
            unique_kv_heads=2,
            adapter_rank=2,
            adapter_alpha=2.0,
        )
        optimizer = torch.optim.AdamW(
            (value for value in model.parameters() if value.requires_grad),
            lr=0.01,
        )
        output = model.layers[0].self_attn.q_proj(torch.randn(3, 4)).sum()
        output.backward()
        optimizer.step()

        self.assertTrue(assert_exact_kv_sharing(model, summary.layer_pairings))


if __name__ == "__main__":
    unittest.main()
