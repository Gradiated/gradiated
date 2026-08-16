from __future__ import annotations

import unittest

from causal_parallel_offset_head import (
    HeadConfig,
    acceptance_curve,
    parameter_count,
    prefix_lengths,
    service_bytes,
    service_flops,
)


class OffsetHeadTest(unittest.TestCase):
    def test_geometry_accounting(self) -> None:
        config = HeadConfig()
        self.assertEqual(parameter_count(config), 6301440)
        self.assertEqual(
            service_bytes(config, 32)["tied_weight_bf16_compulsory"],
            2818572288,
        )
        self.assertEqual(
            service_bytes(config, 32)["full_logits_fp32_materialization"],
            536870912,
        )
        self.assertGreater(
            service_flops(config, 32)["tied_projection"],
            1000 * service_flops(config, 32)["tap_projection"],
        )

    def test_prefix_metrics_stop_at_first_mismatch(self) -> None:
        prediction = [[1, 2, 9, 4], [1, 2, 3, 4]]
        target = [[1, 2, 3, 4], [1, 8, 3, 4]]
        self.assertEqual(prefix_lengths(prediction, target), [2, 1])
        curve = acceptance_curve(prediction, target, depths=(4,))
        self.assertEqual(curve[4]["mean_accepted_draft_tokens"], 1.5)
        self.assertEqual(curve[4]["mean_accepted_target_tokens"], 2.5)
        self.assertEqual(curve[4]["full_prefix_fraction"], 0.0)

    def test_invalid_tap_configuration_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            HeadConfig(tap_layers=(54, 45, 60)).validate()


if __name__ == "__main__":
    unittest.main()
