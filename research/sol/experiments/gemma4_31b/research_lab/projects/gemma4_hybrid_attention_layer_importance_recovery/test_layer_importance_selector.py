import unittest
import math
import struct

import layer_importance_selector as selector


class LayerImportanceSelectorTest(unittest.TestCase):
    def test_bf16_decode_and_rms(self) -> None:
        words = struct.pack("<4H", 0x3F80, 0x4000, 0x4040, 0x4080)
        values = selector.bf16_to_float32(words)
        self.assertEqual(values, [1.0, 2.0, 3.0, 4.0])
        self.assertAlmostEqual(selector.rms(values), math.sqrt(7.5), places=7)

    def test_selector_is_score_descending_with_layer_tie_break(self) -> None:
        scores = {5: 1.0, 11: 3.0, 17: 2.0, 23: 3.0, 29: 0.5, 35: 4.0}
        self.assertEqual(selector.rank_layers(scores, 3), [35, 11, 23])

    def test_exact_alternating_comparator_and_work_invariant(self) -> None:
        self.assertEqual(selector.ALTERNATING_RETAINED, [5, 17, 29, 41, 53])
        self.assertEqual(
            selector.converted_layers(selector.ALTERNATING_RETAINED),
            [11, 23, 35, 47, 59],
        )
        self.assertEqual(
            selector.attention_work(selector.ALTERNATING_RETAINED),
            {"total_layers": 60, "local_layers": 55, "global_layers": 5},
        )


if __name__ == "__main__":
    unittest.main()
