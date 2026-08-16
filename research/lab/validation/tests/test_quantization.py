import unittest

import torch

from validation.qwen_int4_quality.quantization import (
    quantize_linear_weights,
    symmetric_int4_qdq,
)


class SymmetricInt4QdqTests(unittest.TestCase):
    def test_per_channel_uses_independent_output_channel_scales(self) -> None:
        weights = torch.tensor(
            [
                [-1.0, -0.5, 0.0, 0.5, 1.0],
                [-14.0, -7.0, 0.0, 7.0, 14.0],
                [0.0, 0.0, 0.0, 0.0, 0.0],
            ]
        )

        quantized, scales = symmetric_int4_qdq(weights, granularity="per_channel")

        self.assertEqual(scales.shape, (3, 1))
        self.assertAlmostEqual(scales[0, 0].item(), 1.0 / 7.0)
        self.assertAlmostEqual(scales[1, 0].item(), 2.0)
        self.assertEqual(scales[2, 0].item(), 1.0)
        self.assertTrue(torch.equal(quantized[2], torch.zeros(5)))
        self.assertLessEqual(quantized[0].abs().max().item(), 1.0)
        self.assertEqual(quantized[1, -1].item(), 14.0)

    def test_groupwise_uses_independent_scales_and_handles_tail_group(self) -> None:
        weights = torch.tensor([[1.0, 0.5, 14.0, 7.0, 0.25]])

        quantized, scales = symmetric_int4_qdq(
            weights,
            granularity="groupwise",
            group_size=2,
        )

        self.assertEqual(scales.shape, (1, 3, 1))
        self.assertAlmostEqual(scales[0, 0, 0].item(), 1.0 / 7.0)
        self.assertAlmostEqual(scales[0, 1, 0].item(), 2.0)
        self.assertAlmostEqual(scales[0, 2, 0].item(), 0.25 / 7.0)
        self.assertAlmostEqual(quantized[0, 4].item(), 0.25)

    def test_quantized_codes_stay_in_symmetric_signed_int4_range(self) -> None:
        weights = torch.tensor([[100.0, -100.0, 70.0, -70.0]])

        quantized, scales = symmetric_int4_qdq(
            weights,
            granularity="groupwise",
            group_size=4,
        )
        codes = torch.round(weights / scales[0, 0, 0])

        self.assertGreaterEqual(codes.min().item(), -7.0)
        self.assertLessEqual(codes.max().item(), 7.0)
        self.assertTrue(torch.isfinite(quantized).all())

    def test_rejects_invalid_group_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "group_size"):
            symmetric_int4_qdq(
                torch.ones((2, 2)),
                granularity="groupwise",
                group_size=0,
            )

    def test_rejects_non_matrix_weights(self) -> None:
        with self.assertRaisesRegex(ValueError, "two-dimensional"):
            symmetric_int4_qdq(torch.ones(4), granularity="per_channel")

    def test_model_quantization_reports_modified_and_excluded_layers(self) -> None:
        model = torch.nn.ModuleDict(
            {
                "body": torch.nn.Linear(4, 3, bias=False),
                "lm_head": torch.nn.Linear(3, 2, bias=False),
            }
        )

        summary = quantize_linear_weights(
            model,
            granularity="groupwise",
            group_size=2,
            excluded_patterns=("lm_head",),
            baseline_checkpoint_bits_per_parameter=16,
        )

        self.assertEqual(summary.module_count, 1)
        self.assertEqual(summary.parameter_count, 12)
        self.assertEqual(summary.scale_count, 6)
        self.assertEqual(summary.modified_modules, ("body",))
        self.assertEqual(summary.estimated_packed_weight_bytes, 6)
        self.assertEqual(summary.storage_estimate.unique_parameter_count, 18)
        self.assertEqual(summary.storage_estimate.baseline_checkpoint_weight_bytes, 36)
        self.assertEqual(
            summary.storage_estimate.retained_full_precision_parameter_count,
            6,
        )
        self.assertEqual(summary.storage_estimate.estimated_packed_code_bytes, 6)
        self.assertEqual(summary.storage_estimate.estimated_scale_bytes, 12)
        self.assertEqual(
            summary.storage_estimate.estimated_retained_full_precision_bytes,
            12,
        )
        self.assertEqual(summary.storage_estimate.estimated_deployed_weight_bytes, 30)
        self.assertAlmostEqual(
            summary.storage_estimate.estimated_whole_model_bits_per_parameter,
            40.0 / 3.0,
        )
        self.assertAlmostEqual(
            summary.storage_estimate.estimated_weight_storage_reduction_percent,
            100.0 / 6.0,
        )
        self.assertEqual(
            summary.to_dict()["storage_estimate"]["kind"],
            "estimated_packed_mixed_precision_weights",
        )
        self.assertFalse(summary.runtime_storage_compressed)

    def test_storage_accounting_counts_tied_embeddings_once(self) -> None:
        class TiedModel(torch.nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.embed = torch.nn.Embedding(5, 4)
                self.body = torch.nn.Linear(4, 3, bias=False)
                self.norm = torch.nn.LayerNorm(3)
                self.lm_head = torch.nn.Linear(4, 5, bias=False)
                self.lm_head.weight = self.embed.weight

        summary = quantize_linear_weights(
            TiedModel(),
            granularity="groupwise",
            group_size=2,
            excluded_patterns=("lm_head",),
            baseline_checkpoint_bits_per_parameter=16,
        )

        storage = summary.storage_estimate
        self.assertEqual(storage.unique_parameter_count, 38)
        self.assertEqual(storage.quantized_parameter_count, 12)
        self.assertEqual(storage.retained_full_precision_parameter_count, 26)
        self.assertEqual(storage.baseline_checkpoint_weight_bytes, 76)
        self.assertEqual(storage.estimated_packed_code_bytes, 6)
        self.assertEqual(storage.estimated_scale_bytes, 12)
        self.assertEqual(storage.estimated_retained_full_precision_bytes, 52)
        self.assertEqual(storage.estimated_deployed_weight_bytes, 70)
        self.assertAlmostEqual(
            storage.estimated_whole_model_bits_per_parameter, 560.0 / 38.0
        )
        self.assertAlmostEqual(
            storage.estimated_weight_storage_reduction_percent,
            100.0 * 6.0 / 76.0,
        )

    def test_packed_code_bytes_round_each_weight_tensor_independently(self) -> None:
        model = torch.nn.ModuleDict(
            {
                "first": torch.nn.Linear(3, 1, bias=False),
                "second": torch.nn.Linear(3, 1, bias=False),
            }
        )

        summary = quantize_linear_weights(
            model,
            granularity="groupwise",
            group_size=3,
            baseline_checkpoint_bits_per_parameter=16,
        )

        self.assertEqual(summary.parameter_count, 6)
        self.assertEqual(summary.estimated_packed_weight_bytes, 4)
        self.assertEqual(summary.storage_estimate.estimated_packed_code_bytes, 4)


if __name__ == "__main__":
    unittest.main()
