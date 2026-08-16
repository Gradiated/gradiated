from __future__ import annotations

import ast
import unittest

import conditional_depth_policy as policy
import materialize_candidate
import run_dynamic_depth_screen


class Mode:
    def __init__(self, name: str):
        self.name = name


class Batch:
    def __init__(self, mode: str, route_id: str = policy.PHYSICAL_PROXY_ROUTE):
        self.forward_mode = Mode(mode)
        self.conditional_depth_route_id = route_id


class ConditionalDepthTest(unittest.TestCase):
    def test_exact_phase_schedules_and_kv_ownership(self):
        prefill = policy.active_layer_indices(Batch("EXTEND"))
        verification = policy.active_layer_indices(Batch("TARGET_VERIFY"))
        self.assertEqual(len(prefill), 30)
        self.assertEqual(len(verification), 20)
        self.assertTrue(verification.issubset(prefill))
        self.assertEqual(
            run_dynamic_depth_screen.contiguous_groups(prefill),
            [[0, 10], [25, 35], [50, 60]],
        )
        self.assertEqual(
            run_dynamic_depth_screen.contiguous_groups(verification),
            [[0, 10], [50, 60]],
        )

    def test_route_homogeneity_fails_closed(self):
        batch = Batch("EXTEND")
        batch.conditional_depth_route_ids = [
            policy.PHYSICAL_PROXY_ROUTE,
            policy.FULL_DEPTH_ROUTE,
        ]
        with self.assertRaisesRegex(ValueError, "route-homogeneous"):
            policy.active_layer_indices(batch)

    def test_full_depth_fallback_executes_all_layers(self):
        for mode in ("EXTEND", "TARGET_VERIFY", "DECODE"):
            self.assertEqual(
                policy.active_layer_indices(
                    Batch(mode, route_id=policy.FULL_DEPTH_ROUTE)
                ),
                frozenset(range(60)),
            )

    def test_executable_policy_removes_exact_layer_calls(self):
        for mode, expected in (("EXTEND", 30), ("TARGET_VERIFY", 20)):
            calls = []
            active = policy.active_layer_indices(Batch(mode))
            for layer_index in range(60):
                if layer_index not in active:
                    continue
                calls.append(layer_index)
            self.assertEqual(calls, sorted(active))
            self.assertEqual(len(calls), expected)

    def test_candidate_materializes_and_skip_dominates_layer_call(self):
        proof = materialize_candidate.materialize()
        self.assertTrue(proof["skip_dominates_layer_load_and_call"])
        candidate = materialize_candidate.CANDIDATE.read_text()
        ast.parse(candidate)
        skip = candidate.index("if layer_idx not in active_layer_indices:")
        load = candidate.index("layer = self.layers[layer_idx]", skip)
        call = candidate.index("layer_outputs = layer(", load)
        self.assertLess(skip, load)
        self.assertLess(load, call)

    def test_screen_is_source_complete_and_below_target(self):
        result = run_dynamic_depth_screen.build_result()
        self.assertEqual(
            result["classification"], "source_complete_physical_candidate"
        )
        self.assertLessEqual(
            result["physical_accounting"][
                "conservative_candidate_service_seconds_per_request"
            ],
            result["physical_accounting"]["locked_target_seconds_per_request"],
        )
        self.assertGreater(
            result["physical_accounting"]["non_skippable_residual_seconds_per_request"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
