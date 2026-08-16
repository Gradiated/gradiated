from __future__ import annotations

import unittest

from validation.ramulator_adapter.trace import (
    EXECUTABLE_PATTERN_IDS,
    PATTERN_SPECS,
    generate_trace,
    summarize_trace,
)


class TraceTests(unittest.TestCase):
    def test_generation_is_deterministic_and_pattern_specific(self) -> None:
        first = generate_trace("sequential_stream", request_count=64, seed=7)
        second = generate_trace("sequential_stream", request_count=64, seed=7)
        gathered = generate_trace("gather_score_order", request_count=64, seed=7)
        self.assertEqual(first, second)
        self.assertNotEqual(first, gathered)

    def test_all_patterns_have_identical_work_and_mix(self) -> None:
        summaries = [
            summarize_trace(generate_trace(pattern, request_count=2048, seed=20260712))
            for pattern in EXECUTABLE_PATTERN_IDS
        ]
        common = {
            (
                summary["request_count"],
                summary["read_count"],
                summary["write_count"],
                summary["request_bytes"],
                summary["total_bytes"],
            )
            for summary in summaries
        }
        self.assertEqual(common, {(2048, 2048, 0, 32, 65536)})

    def test_patterns_are_explicitly_synthetic(self) -> None:
        self.assertEqual(PATTERN_SPECS["sequential_stream"]["role"], "negative_control")
        for pattern in ("gather_score_order", "gather_address_sorted"):
            self.assertEqual(PATTERN_SPECS[pattern]["provenance"], "synthetic")
            self.assertFalse(PATTERN_SPECS[pattern]["real_glm_trace"])

    def test_score_and_address_order_share_exact_selected_set(self) -> None:
        score_order = generate_trace(
            "gather_score_order", request_count=2048, seed=20260712
        )
        address_order = generate_trace(
            "gather_address_sorted", request_count=2048, seed=20260712
        )
        score_positions = [record.token_position for record in score_order]
        address_positions = [record.token_position for record in address_order]
        self.assertEqual(set(score_positions), set(address_positions))
        self.assertNotEqual(score_positions, address_positions)
        self.assertEqual(address_positions, sorted(address_positions))
        self.assertFalse(
            PATTERN_SPECS["gather_address_sorted"][
                "physical_hbm_address_vector_lexicographic_sort"
            ]
        )

    def test_page_clustering_frontier_is_exact_where_feasible(self) -> None:
        with self.assertRaisesRegex(ValueError, "infeasible"):
            generate_trace("gather_cluster_1", request_count=2048, seed=20260712)
        for target in (2, 4, 8, 16, 32, 64):
            records = generate_trace(
                f"gather_cluster_{target}", request_count=2048, seed=20260712
            )
            summary = summarize_trace(records)
            self.assertEqual(summary["unique_token_count"], 2048)
            self.assertEqual(summary["tokens_per_selected_page_minimum"], target)
            self.assertEqual(summary["tokens_per_selected_page_maximum"], target)
            self.assertEqual(summary["selected_page_count"], 2048 // target)

    def test_bf16_record_geometry_expands_to_exact_equal_work(self) -> None:
        summaries = [
            summarize_trace(
                generate_trace(
                    pattern,
                    request_count=2048,
                    seed=20260712,
                    transactions_per_token=36,
                )
            )
            for pattern in EXECUTABLE_PATTERN_IDS
        ]
        common = {
            (
                summary["request_count"],
                summary["read_count"],
                summary["write_count"],
                summary["selected_token_count"],
                summary["transactions_per_selected_token"],
                summary["bytes_per_selected_token"],
                summary["total_bytes"],
            )
            for summary in summaries
        }
        self.assertEqual(common, {(73728, 73728, 0, 2048, 36, 1152, 2359296)})

    def test_address_vectors_match_hbm3_bounds(self) -> None:
        for pattern in EXECUTABLE_PATTERN_IDS:
            for record in generate_trace(pattern, request_count=128, seed=11):
                self.assertIn(record.operation, {"R", "W"})
                self.assertEqual(len(record.address), 7)
                channel, pseudochannel, sid, bankgroup, bank, row, column = (
                    record.address
                )
                self.assertEqual(channel, 0)
                self.assertIn(pseudochannel, range(2))
                self.assertIn(sid, range(2))
                self.assertIn(bankgroup, range(4))
                self.assertIn(bank, range(4))
                self.assertIn(row, range(8192))
                self.assertIn(column, range(256))
