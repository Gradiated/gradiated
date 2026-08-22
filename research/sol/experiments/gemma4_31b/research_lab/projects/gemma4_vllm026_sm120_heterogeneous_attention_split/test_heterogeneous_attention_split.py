from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from heterogeneous_attention_split import DISPATCH, evaluate


PROJECT = Path(__file__).resolve().parent
WORKSPACE = PROJECT.parents[6]
VLLM = WORKSPACE / ".agents/runtime/vllm-v0.26.0"
CONFIG = (
    PROJECT.parent
    / "gemma4_rtxpro6000_fp8_endpoint/inputs/model_inputs/config.json"
)


class HeterogeneousAttentionSplitTest(unittest.TestCase):
    def test_exact_config_returns_dispatch(self) -> None:
        result = evaluate(VLLM, CONFIG)
        self.assertEqual(result["classification"], "exact_layer_aware_dispatch")
        self.assertEqual(result["attention_config"], DISPATCH)
        self.assertEqual(
            result["consumer_binding"]["full_attention"]["k_v_layout"], "[T,4,512]"
        )

    def test_kv_sharing_mutation_returns_typed_none(self) -> None:
        config = json.loads(CONFIG.read_text())
        config["text_config"]["num_kv_shared_layers"] = 1
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(config))
            result = evaluate(VLLM, path)
        self.assertEqual(result["classification"], "typed_none")
        self.assertTrue(
            any("num_kv_shared_layers" in failure for failure in result["failures"])
        )

    def test_softcap_mutation_returns_typed_none(self) -> None:
        config = copy.deepcopy(json.loads(CONFIG.read_text()))
        config["text_config"]["attn_logit_softcapping"] = 30.0
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps(config))
            result = evaluate(VLLM, path)
        self.assertEqual(result["classification"], "typed_none")
        self.assertTrue(
            any("attn_logit_softcapping" in failure for failure in result["failures"])
        )


if __name__ == "__main__":
    unittest.main()
