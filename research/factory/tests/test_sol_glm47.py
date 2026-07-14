from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from grad_research.sol_glm47 import bootstrap_glm47


class SolGlm47BootstrapTests(unittest.TestCase):
    def test_bootstrap_follows_final_dense_residual_and_is_idempotent(self):
        workspace = Path(__file__).resolve().parents[3]
        campaign = workspace / "research/sol/experiments/glm47flash/campaign_100"
        with tempfile.TemporaryDirectory() as directory:
            first = bootstrap_glm47(directory, campaign)
            first_event_count = first["state"]["event_count"]
            second = bootstrap_glm47(directory, campaign)
            state = second["state"]
            selected = state["portfolios"]["1"]["selected_ids"]

            self.assertEqual(first_event_count, state["event_count"])
            self.assertEqual("glm47-l40s-vllm-awq-split4-v28", state["baseline"]["id"])
            self.assertIn("Dense GEMM/GEMV", state["residual_bottleneck"])
            self.assertIn("Calibrate", state["next_action"])
            self.assertTrue(state["portfolios"]["1"]["coverage"]["ready"])
            self.assertIn("glm47-dense-resource-signature", selected)
            self.assertIn("glm47-host-scheduler-critical-path", selected)
            self.assertIn("glm47-layer-selective-representation", selected)
            self.assertIn("glm47-quality-and-observer-skeptic", selected)
            self.assertFalse(any("split8" in identifier or "kv-splits" in identifier for identifier in selected))
            self.assertEqual("STOP_NUM_KV_SPLITS_8", state["legacy"]["lineage_decision"])
            context = Path(second["context_path"]).read_text()
            self.assertIn("dense", context.lower())
            self.assertIn("adversarial", context.lower())


if __name__ == "__main__":
    unittest.main()
