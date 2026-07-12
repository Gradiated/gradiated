import unittest

import torch

from validation.qwen_int4_task_quality.quantization import (
    quantize_frozen_selective_mask,
    symmetric_group8_int4_bf16_scale_qdq,
)


class RuntimeRepresentationTests(unittest.TestCase):
    def test_codes_use_float_scale_but_dequantization_uses_bfloat16_scale(self) -> None:
        weights = torch.tensor(
            [[-1.1, -0.7, -0.2, 0.0, 0.1, 0.4, 0.8, 1.1]],
            dtype=torch.float32,
        )
        floating_scale = weights.abs().amax() / 7.0
        stored_scale = floating_scale.to(torch.bfloat16).to(torch.float32)
        expected_codes = torch.round(weights / floating_scale).clamp(-7.0, 7.0)

        restored, scales, codes = symmetric_group8_int4_bf16_scale_qdq(weights)

        self.assertTrue(torch.equal(codes, expected_codes))
        self.assertEqual(scales.item(), stored_scale.item())
        self.assertNotEqual(scales.item(), floating_scale.item())
        self.assertTrue(torch.equal(restored, expected_codes * stored_scale))

    def test_zero_group_uses_one_stored_as_bfloat16(self) -> None:
        restored, scales, codes = symmetric_group8_int4_bf16_scale_qdq(
            torch.zeros((1, 8), dtype=torch.bfloat16)
        )

        self.assertEqual(scales.item(), 1.0)
        self.assertTrue(torch.equal(codes, torch.zeros_like(codes)))
        self.assertTrue(torch.equal(restored, torch.zeros_like(restored)))

    def test_frozen_mask_modifies_only_three_named_families(self) -> None:
        model = torch.nn.ModuleDict(
            {
                "model": torch.nn.ModuleDict(
                    {
                        "layers": torch.nn.ModuleList(
                            [
                                torch.nn.ModuleDict(
                                    {
                                        "self_attn": torch.nn.ModuleDict(
                                            {
                                                "o_proj": torch.nn.Linear(
                                                    8, 8, bias=False
                                                ),
                                                "q_proj": torch.nn.Linear(
                                                    8, 8, bias=False
                                                ),
                                            }
                                        ),
                                        "mlp": torch.nn.ModuleDict(
                                            {
                                                "gate_proj": torch.nn.Linear(
                                                    8, 8, bias=False
                                                ),
                                                "up_proj": torch.nn.Linear(
                                                    8, 8, bias=False
                                                ),
                                                "down_proj": torch.nn.Linear(
                                                    8, 8, bias=False
                                                ),
                                            }
                                        ),
                                    }
                                )
                            ]
                        )
                    }
                )
            }
        )

        summary = quantize_frozen_selective_mask(
            model,
            expected_module_count=3,
            expected_parameter_count=192,
        )

        self.assertEqual(
            summary.modified_modules,
            (
                "model.layers.0.self_attn.o_proj",
                "model.layers.0.mlp.gate_proj",
                "model.layers.0.mlp.up_proj",
            ),
        )
        self.assertEqual(summary.scale_count, 24)
        self.assertEqual(summary.scale_storage, "bfloat16")
        self.assertEqual(summary.code_derivation_scale, "float32_max_abs_div_7")

    def test_frozen_mask_rejects_unexpected_model_geometry(self) -> None:
        model = torch.nn.ModuleDict({"other": torch.nn.Linear(8, 8, bias=False)})

        with self.assertRaisesRegex(ValueError, "module count"):
            quantize_frozen_selective_mask(
                model,
                expected_module_count=3,
                expected_parameter_count=192,
            )


if __name__ == "__main__":
    unittest.main()
