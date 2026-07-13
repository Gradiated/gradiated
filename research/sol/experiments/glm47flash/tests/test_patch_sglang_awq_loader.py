import unittest

from patch_sglang_awq_loader import (
    DEEPSEEK_NEW_PACKED,
    DEEPSEEK_OLD_PACKED,
    GLM_NEW_MAPPING,
    GLM_OLD_MAPPING,
    GLM_OLD_QUANT_INIT,
    NEW,
    OLD,
    patch_deepseek_source,
    patch_glm_source,
    patch_source,
)


class PatchSourceTests(unittest.TestCase):
    def test_replaces_only_pinned_fusion_block(self):
        source = "before\n" + OLD + "after\n"

        patched = patch_source(source)

        self.assertEqual(patched, "before\n" + NEW + "after\n")

    def test_refuses_unknown_source(self):
        with self.assertRaisesRegex(ValueError, "found 0"):
            patch_source("different runtime")

    def test_refuses_ambiguous_source(self):
        with self.assertRaisesRegex(ValueError, "found 2"):
            patch_source(OLD + OLD)

    def test_glm_patch_registers_fused_mapping_and_shape_fix(self):
        source = GLM_OLD_MAPPING + "\n" + GLM_OLD_QUANT_INIT + "\n" + OLD

        patched = patch_glm_source(source)

        self.assertIn(GLM_NEW_MAPPING, patched)
        self.assertIn(NEW, patched)
        self.assertNotIn(GLM_OLD_MAPPING, patched)

    def test_deepseek_patch_recognizes_weight_packed(self):
        patched = patch_deepseek_source(DEEPSEEK_OLD_PACKED)

        self.assertEqual(patched, DEEPSEEK_NEW_PACKED)
