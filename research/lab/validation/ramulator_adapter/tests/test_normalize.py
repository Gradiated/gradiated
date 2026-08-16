from __future__ import annotations

import copy
import unittest

from validation.ramulator_adapter.normalize import (
    build_report,
    content_identity,
    normalize_stats,
    validate_report,
)


RAW_STATS = {
    "memory_system": {
        "total_num_read_requests": 12,
        "total_num_write_requests": 4,
        "controller": {
            "cycles": 200,
            "avg_read_latency": 24.5,
            "read_latency": 294,
            "num_read_reqs": 12,
            "num_write_reqs": 4,
            "num_read_reqs_served": 12,
            "num_write_reqs_served": 4,
            "row_hits": 10,
            "row_misses": 2,
            "row_conflicts": 4,
        },
    },
    "driver": {
        "accepted_request_count": 16,
        "completed_request_count": 16,
        "tick_count": 200,
        "callback_latency_sum": 294,
    },
}


class NormalizeTests(unittest.TestCase):
    def test_normalizes_only_native_stats(self) -> None:
        normalized = normalize_stats(RAW_STATS)
        self.assertEqual(normalized["controller_cycles"], 200)
        self.assertEqual(normalized["average_read_latency_cycles"], 24.5)
        self.assertEqual(normalized["row_hit_fraction"], 0.625)
        self.assertEqual(normalized["accepted_request_count"], 16)
        self.assertEqual(normalized["served_request_count"], 16)

    def test_report_validates_conservation_replay_and_claims(self) -> None:
        summary = {
            "request_count": 16,
            "read_count": 12,
            "write_count": 4,
            "request_bytes": 32,
            "total_bytes": 512,
        }
        report = build_report(
            source_identity={
                "repository": "https://github.com/CMU-SAFARI/ramulator2.git"
            },
            build={"status": "succeeded"},
            cases=[
                {
                    "pattern_id": "sequential_stream",
                    "trace_summary": summary,
                    "runs": [normalize_stats(RAW_STATS), normalize_stats(RAW_STATS)],
                }
            ],
        )
        self.assertEqual(validate_report(report), [])
        self.assertEqual(report["content_identity_sha256"], content_identity(report))
        self.assertTrue(report["cases"][0]["request_conservation_passed"])
        self.assertTrue(report["cases"][0]["deterministic_replay_passed"])
        self.assertTrue(report["cases"][0]["native_drain_accounting_passed"])

    def test_validation_rejects_conservation_failure(self) -> None:
        bad = copy.deepcopy(RAW_STATS)
        bad["memory_system"]["controller"]["num_read_reqs"] = 11
        summary = {
            "request_count": 16,
            "read_count": 12,
            "write_count": 4,
            "request_bytes": 32,
            "total_bytes": 512,
        }
        report = build_report(
            source_identity={},
            build={"status": "succeeded"},
            cases=[
                {
                    "pattern_id": "sequential_stream",
                    "trace_summary": summary,
                    "runs": [normalize_stats(bad), normalize_stats(bad)],
                }
            ],
        )
        self.assertIn("request conservation failed", " ".join(validate_report(report)))

    def test_validation_rejects_accepted_but_undrained_requests(self) -> None:
        partial = copy.deepcopy(RAW_STATS)
        partial["memory_system"]["controller"]["num_read_reqs_served"] = 11
        summary = {
            "request_count": 16,
            "read_count": 12,
            "write_count": 4,
            "request_bytes": 32,
            "total_bytes": 512,
        }
        report = build_report(
            source_identity={},
            build={"status": "succeeded"},
            cases=[
                {
                    "pattern_id": "sequential_stream",
                    "trace_summary": summary,
                    "runs": [normalize_stats(partial), normalize_stats(partial)],
                }
            ],
        )
        case = report["cases"][0]
        self.assertTrue(case["request_acceptance_conservation_passed"])
        self.assertFalse(case["all_requests_served"])
        self.assertFalse(case["request_conservation_passed"])
        self.assertIn("request conservation failed", " ".join(validate_report(report)))

    def test_validation_rejects_callback_latency_accounting_drift(self) -> None:
        drifted = copy.deepcopy(RAW_STATS)
        drifted["driver"]["callback_latency_sum"] += 1
        summary = {
            "request_count": 16,
            "read_count": 12,
            "write_count": 4,
            "request_bytes": 32,
            "total_bytes": 512,
        }
        report = build_report(
            source_identity={},
            build={"status": "succeeded"},
            cases=[
                {
                    "pattern_id": "sequential_stream",
                    "trace_summary": summary,
                    "runs": [normalize_stats(drifted), normalize_stats(drifted)],
                }
            ],
        )
        self.assertFalse(report["cases"][0]["native_drain_accounting_passed"])
        self.assertIn("drain accounting failed", " ".join(validate_report(report)))

    def test_validation_rejects_replay_drift(self) -> None:
        replay = normalize_stats(RAW_STATS)
        replay["controller_cycles"] += 1
        summary = {
            "request_count": 16,
            "read_count": 12,
            "write_count": 4,
            "request_bytes": 32,
            "total_bytes": 512,
        }
        report = build_report(
            source_identity={},
            build={"status": "succeeded"},
            cases=[
                {
                    "pattern_id": "sequential_stream",
                    "trace_summary": summary,
                    "runs": [normalize_stats(RAW_STATS), replay],
                }
            ],
        )
        self.assertIn("deterministic replay failed", " ".join(validate_report(report)))

    def test_validation_rejects_promoted_claim(self) -> None:
        report = build_report(source_identity={}, build={"status": "blocked"}, cases=[])
        report["claims"]["glm_performance"] = True
        self.assertIn("claim must remain false", " ".join(validate_report(report)))

    def test_work_equality_is_scoped_per_geometry(self) -> None:
        base = {
            "request_count": 16,
            "read_count": 12,
            "write_count": 4,
            "request_bytes": 32,
            "total_bytes": 512,
        }
        expanded = {
            "request_count": 32,
            "read_count": 24,
            "write_count": 8,
            "request_bytes": 32,
            "total_bytes": 1024,
        }
        doubled_stats = copy.deepcopy(RAW_STATS)
        memory = doubled_stats["memory_system"]
        controller = memory["controller"]
        memory["total_num_read_requests"] = 24
        memory["total_num_write_requests"] = 8
        controller["num_read_reqs"] = 24
        controller["num_write_reqs"] = 8
        controller["num_read_reqs_served"] = 24
        controller["num_write_reqs_served"] = 8
        report = build_report(
            source_identity={},
            build={"status": "succeeded"},
            cases=[
                {
                    "geometry_id": "line",
                    "pattern_id": "sequential_stream",
                    "trace_summary": base,
                    "runs": [normalize_stats(RAW_STATS), normalize_stats(RAW_STATS)],
                },
                {
                    "geometry_id": "record",
                    "pattern_id": "sequential_stream",
                    "trace_summary": expanded,
                    "runs": [
                        normalize_stats(doubled_stats),
                        normalize_stats(doubled_stats),
                    ],
                },
            ],
        )
        self.assertNotIn("case work is not identical", validate_report(report))

    def test_declared_geometry_and_pattern_set_are_fail_closed(self) -> None:
        geometry = {
            "transactions_per_selected_token": 1,
            "bytes_per_selected_token": 32,
            "scope": "test",
        }
        summary = {
            "request_count": 16,
            "read_count": 12,
            "write_count": 4,
            "request_bytes": 32,
            "total_bytes": 512,
            "selected_token_count": 16,
            "unique_token_count": 16,
            "transactions_per_selected_token": 1,
            "bytes_per_selected_token": 32,
        }
        report = build_report(
            source_identity={},
            build={"status": "succeeded"},
            metadata={
                "workload": {
                    "geometries": {"line": geometry},
                    "executable_pattern_ids": [
                        "sequential_stream",
                        "gather_score_order",
                    ],
                    "selected_token_count": 16,
                    "request_bytes": 32,
                }
            },
            cases=[
                {
                    "geometry_id": "line",
                    "geometry_contract": {**geometry, "scope": "drifted"},
                    "pattern_id": "sequential_stream",
                    "trace_summary": summary,
                    "runs": [normalize_stats(RAW_STATS), normalize_stats(RAW_STATS)],
                }
            ],
        )
        errors = " ".join(validate_report(report))
        self.assertIn("pattern case set is incomplete", errors)
        self.assertIn("geometry contract mismatch", errors)
