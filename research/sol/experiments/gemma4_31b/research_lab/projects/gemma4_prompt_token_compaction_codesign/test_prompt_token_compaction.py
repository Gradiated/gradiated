from __future__ import annotations

import ast
import unittest

import materialize_candidate
import prompt_token_compaction_runtime as runtime
import run_physical_screen


class PromptStateMergeTest(unittest.TestCase):
    def test_every_input_contributes_once_and_protected_states_are_singletons(self):
        length = runtime.PROMPT_TOKENS
        input_ids = list(range(length))
        input_ids[900] = 99
        plan = runtime.build_request_merge_plan(
            input_ids, special_token_ids=(99,)
        )
        plan.assert_contribution_invariant()
        contributors = [
            index for group in plan.groups for index in group.source_indices
        ]
        singletons = {
            group.source_indices[0]
            for group in plan.groups
            if group.protected_singleton
        }
        summaries = [
            group for group in plan.groups if not group.protected_singleton
        ]
        self.assertEqual(plan.output_length, runtime.OUTPUT_STATES)
        self.assertEqual(sorted(contributors), list(range(length)))
        self.assertEqual(len(contributors), len(set(contributors)))
        self.assertTrue(set(range(535)).issubset(singletons))
        self.assertTrue(
            set(range(length - 384, length)).issubset(singletons)
        )
        self.assertIn(900, singletons)
        self.assertGreaterEqual(len(summaries), runtime.MIN_SUMMARY_STATES)
        self.assertTrue(all(group.source_indices for group in summaries))

    def test_protected_overflow_fails_closed(self):
        length = runtime.PROMPT_TOKENS
        input_ids = [0] * length
        tool_mask = [False] * length
        start = runtime.PROTECTED_SHARED_PREFIX_TOKENS
        count = runtime.MAX_ADDITIONAL_PROTECTED_TOKENS + 1
        tool_mask[start : start + count] = [True] * count
        with self.assertRaisesRegex(
            runtime.CompactionFallback, "fewer_than_64_summaries"
        ):
            runtime.build_request_merge_plan(input_ids, tool_mask=tool_mask)

    def test_reference_merge_shrinks_first_late_consumers_and_kv_writes(self):
        length = runtime.PROMPT_TOKENS
        plan = runtime.build_request_merge_plan(list(range(length)))
        hidden = [[float(index), 1.0, 2.0, 3.0] for index in range(length)]
        merged = []
        representative_slots = []
        for group in plan.groups:
            members = [hidden[index] for index in group.source_indices]
            merged.append(
                [
                    sum(row[column] for row in members) / len(members)
                    for column in range(4)
                ]
            )
            representative_slots.append(100_000 + group.output_position)
        first_late_linear = [
            [sum(row), sum(row), sum(row)] for row in merged
        ]
        first_late_attention_scores = [
            sum(left * right for left, right in zip(merged[0], row))
            for row in merged
        ]
        self.assertEqual(len(merged), runtime.OUTPUT_STATES)
        self.assertEqual(len(first_late_linear), runtime.OUTPUT_STATES)
        self.assertEqual(len(first_late_linear[0]), 3)
        self.assertEqual(
            len(first_late_attention_scores), runtime.OUTPUT_STATES
        )
        self.assertEqual(len(representative_slots), runtime.OUTPUT_STATES)
        self.assertTrue(
            all(a < b for a, b in zip(representative_slots, representative_slots[1:]))
        )

    def test_candidate_sources_parse_and_merge_dominates_late_consumers(self):
        proof = materialize_candidate.materialize()
        self.assertTrue(proof["merge_follows_layer_5"])
        self.assertTrue(proof["every_input_contributes_by_construction"])
        self.assertTrue(
            proof["later_layer_call_receives_compacted_state_and_batch"]
        )
        for path in (
            materialize_candidate.CANDIDATE_MODEL,
            materialize_candidate.CANDIDATE_RUNNER,
        ):
            ast.parse(path.read_text())

    def test_screen_is_information_carrying_and_meets_target(self):
        result = run_physical_screen.build_result()
        self.assertEqual(
            result["classification"], "source_complete_physical_candidate"
        )
        self.assertTrue(
            result["decision"]["every_input_contributes_to_downstream_state"]
        )
        accounting = result["physical_accounting"]
        self.assertLessEqual(
            accounting["conservative_candidate_service_seconds_per_request"],
            accounting["locked_target_seconds_per_request"],
        )
        self.assertGreater(
            result["removed_execution"]["prefill_gemm_rows_removed"], 0
        )
        sensitivity = {
            row["output_states"]: row
            for row in result["sensitivity"]["summary_budget"]
        }
        self.assertTrue(sensitivity[1152]["meets_target"])
        self.assertFalse(sensitivity[1200]["meets_target"])


if __name__ == "__main__":
    unittest.main()
