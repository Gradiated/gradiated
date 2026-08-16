import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nebius"))

from selective_w4_scope import (  # noqa: E402
    apply_scope_to_config,
    expected_weight_count,
    selected_weight,
    validate_scope_config,
)


def candidate_weights() -> list[str]:
    return ["lm_head.weight"] + [
        f"model.layers.{layer}.mlp.shared_experts.{projection}.weight"
        for layer in range(1, 47)
        for projection in ("gate_proj", "up_proj", "down_proj")
    ]


def source_config() -> dict:
    return {
        "quantization_config": {
            "config_groups": {
                "group_0": {
                    "format": "pack-quantized",
                    "targets": ["Linear"],
                    "weights": {
                        "num_bits": 4,
                        "type": "int",
                        "symmetric": True,
                        "strategy": "group",
                        "group_size": 32,
                    },
                }
            },
            "ignore": [
                "unrelated.layer",
                *[name.removesuffix(".weight") for name in candidate_weights()],
            ],
        }
    }


class SelectiveW4ScopeTests(unittest.TestCase):
    def test_each_scope_has_exact_dispatch_and_ignore_semantics(self):
        candidates = candidate_weights()
        original = source_config()
        for scope, expected in (
            ("combined", 139),
            ("head_only", 1),
            ("shared_only", 138),
        ):
            with self.subTest(scope=scope):
                scoped = apply_scope_to_config(original, candidates, scope)
                validate_scope_config(scoped, candidates, scope)
                self.assertEqual(
                    expected,
                    sum(selected_weight(name, scope) for name in candidates),
                )
                self.assertEqual(expected, expected_weight_count(scope))
                groups = scoped["quantization_config"]["config_groups"]
                ignored = set(scoped["quantization_config"]["ignore"])
                self.assertEqual(
                    scope in {"combined", "head_only"},
                    "parallel_lm_head_w4" in groups,
                )
                self.assertEqual(scope == "shared_only", "lm_head" in ignored)
        self.assertEqual(source_config(), original)

    def test_partial_candidate_universe_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "candidate closure mismatch"):
            apply_scope_to_config(source_config(), candidate_weights()[:-1], "combined")

    def test_shared_only_validation_rejects_stale_head_dispatch(self):
        candidates = candidate_weights()
        scoped = apply_scope_to_config(source_config(), candidates, "shared_only")
        scoped["quantization_config"]["config_groups"]["parallel_lm_head_w4"] = {
            "targets": ["ParallelLMHead"]
        }
        with self.assertRaisesRegex(ValueError, "ParallelLMHead dispatch mismatch"):
            validate_scope_config(scoped, candidates, "shared_only")


if __name__ == "__main__":
    unittest.main()
