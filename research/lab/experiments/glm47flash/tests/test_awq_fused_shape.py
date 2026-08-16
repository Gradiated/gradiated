import json
import unittest
from pathlib import Path

from awq_fused_metadata import (
    dequantize_symmetric_int4_groupwise,
    fuse_projection_tensor,
    fused_projection_is_packed,
    should_ignore_fused_projection,
)
from patch_sglang_awq_loader import patch_deepseek_weight_loader_source


FIXTURE = Path(__file__).parent / "fixtures" / "layer1_qkv_a_metadata.json"


class FusedProjectionTensorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())

    def test_old_concatenation_reproduces_loader_mismatch(self):
        q_shape = self.fixture["q_a_proj.weight_shape"]["values"]
        kv_shape = self.fixture["kv_a_proj_with_mqa.weight_shape"]["values"]
        target_shape = self.fixture["fused_target.weight_shape"]

        old_fused = q_shape + kv_shape

        self.assertEqual(len(target_shape), 2)
        self.assertEqual(len(old_fused), 4)

    def test_weight_shape_fuses_output_features_only(self):
        q_shape = self.fixture["q_a_proj.weight_shape"]["values"]
        kv_shape = self.fixture["kv_a_proj_with_mqa.weight_shape"]["values"]

        fused = fuse_projection_tensor(
            "model.layers.1.self_attn.q_a_proj.weight_shape",
            q_shape,
            kv_shape,
        )

        self.assertEqual(fused, self.fixture["fused_target.weight_shape"])

    def test_non_metadata_tensors_still_concatenate_axis_zero(self):
        q_rows = [[1, 2], [3, 4]]
        kv_rows = [[5, 6]]

        fused = fuse_projection_tensor(
            "model.layers.1.self_attn.q_a_proj.weight_packed",
            q_rows,
            kv_rows,
        )

        self.assertEqual(fused, [[1, 2], [3, 4], [5, 6]])

    def test_weight_shape_rejects_different_input_features(self):
        with self.assertRaisesRegex(ValueError, "input features"):
            fuse_projection_tensor("x.weight_shape", [768, 2048], [576, 1024])

    def test_weight_shape_rejects_non_descriptor(self):
        with self.assertRaisesRegex(ValueError, "two-element"):
            fuse_projection_tensor("x.weight_shape", [768], [576, 2048])

    def test_layer_zero_fused_projection_inherits_source_exclusion(self):
        ignore = [
            "model.layers.0.self_attn.q_a_proj",
            "model.layers.0.self_attn.kv_a_proj_with_mqa",
        ]
        mapping = {
            "fused_qkv_a_proj_with_mqa": [
                "q_a_proj",
                "kv_a_proj_with_mqa",
            ]
        }

        self.assertTrue(
            should_ignore_fused_projection(
                "model.layers.0.self_attn.fused_qkv_a_proj_with_mqa",
                ignore,
                mapping,
            )
        )
        self.assertFalse(
            should_ignore_fused_projection(
                "model.layers.1.self_attn.fused_qkv_a_proj_with_mqa",
                ignore,
                mapping,
            )
        )

    def test_compressed_tensors_weight_packed_is_detected(self):
        self.assertTrue(fused_projection_is_packed(True, "compressed-tensors"))
        self.assertTrue(fused_projection_is_packed(False, "awq_marlin"))
        self.assertFalse(fused_projection_is_packed(False, "compressed-tensors"))

    def test_signed_int4_groupwise_dequantization_fixture(self):
        # Two output rows, eight input columns, group size four. Values are the
        # signed int4 values after compressed-tensors' uint4b8 offset decoding.
        quantized = [[-8, -2, 0, 7, 1, 2, 3, 4], [4, 3, 2, 1, -1, -2, -3, -4]]
        scales = [[0.5, 2.0], [0.25, 1.5]]
        self.assertEqual(
            dequantize_symmetric_int4_groupwise(quantized, scales, 4),
            [[-4.0, -1.0, 0.0, 3.5, 2.0, 4.0, 6.0, 8.0],
             [1.0, 0.75, 0.5, 0.25, -1.5, -3.0, -4.5, -6.0]],
        )

    def test_weight_loader_patch_adds_only_compressed_kv_b_branch(self):
        old = '''            if hasattr(self_attn.kv_b_proj, "qweight"):\n                # awq compatible, dequantize the weight if supported\n                awq_dequantize_f = awq_dequantize_func()\n                if awq_dequantize_f is not None:\n                    w = awq_dequantize_f(\n                        self_attn.kv_b_proj.qweight,\n                        self_attn.kv_b_proj.scales,\n                        self_attn.kv_b_proj.qzeros,\n                    ).T\n                else:\n                    raise ValueError(\n                        "AWQ dequantize function is not supported for the current device"\n                    )\n            else:\n                w = self_attn.kv_b_proj.weight\n'''
        patched = patch_deepseek_weight_loader_source(old)
        self.assertIn('hasattr(self_attn.kv_b_proj, "weight_packed")', patched)
        self.assertIn("unpack_from_int32", patched)
        self.assertIn("scheme.quant_type.size_bits != 4", patched)
        self.assertIn("w = dequantize(", patched)
        self.assertEqual(patched.count("elif"), 1)


if __name__ == "__main__":
    unittest.main()
