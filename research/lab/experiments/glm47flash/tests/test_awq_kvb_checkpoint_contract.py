import json
import unittest
from pathlib import Path

from patch_sglang_awq_loader import WEIGHT_LOADER_NEW


FIXTURE = Path(__file__).parent / "fixtures" / "layer1_kvb_metadata.json"


class KvbCheckpointContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())

    def test_exact_checkpoint_geometry_matches_int4_groupwise_inverse(self):
        weight_shape = self.fixture["weight_shape"]["values"]
        packed_shape = self.fixture["weight_packed"]["shape"]
        scale_shape = self.fixture["weight_scale"]["shape"]
        quantization = self.fixture["quantization"]

        pack_factor = 32 // quantization["num_bits"]

        self.assertEqual(packed_shape[0], weight_shape[0])
        self.assertEqual(packed_shape[1] * pack_factor, weight_shape[1])
        self.assertEqual(scale_shape[0], weight_shape[0])
        self.assertEqual(
            scale_shape[1] * quantization["group_size"], weight_shape[1]
        )
        self.assertTrue(quantization["symmetric"])
        self.assertIsNone(quantization["actorder"])

    def test_patch_uses_the_canonical_pre_marlin_checkpoint_inverse(self):
        compressed_branch = WEIGHT_LOADER_NEW.split(
            'elif hasattr(self_attn.kv_b_proj, "weight_packed"):', 1
        )[1].split("            else:", 1)[0]

        self.assertIn("unpack_from_int32", compressed_branch)
        self.assertIn("scheme.quant_type.size_bits", compressed_branch)
        self.assertIn("scale=kv_b_proj.weight_scale", compressed_branch)
        self.assertIn("zero_point=None", compressed_branch)
        self.assertIn("g_idx=None", compressed_branch)
        self.assertIn("scheme.quant_type.size_bits != 4", compressed_branch)
        self.assertIn("not scheme.symmetric or scheme.has_g_idx", compressed_branch)
        self.assertNotIn(".T", compressed_branch)


if __name__ == "__main__":
    unittest.main()
