import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


NEBIUS = Path(__file__).resolve().parents[1] / "nebius"
sys.path.insert(0, str(NEBIUS))

from analyze_nsys_observer import (  # noqa: E402
    analyze_fixture,
    correlation_summary,
    interval_union_ns,
    load_sqlite_fixture,
    observer_effect,
    select_route,
)


class NsysObserverAnalysisTests(unittest.TestCase):
    def test_interval_union_clips_and_does_not_double_count_overlap(self):
        intervals = [(0, 20), (10, 30), (30, 40), (90, 120)]
        self.assertEqual(interval_union_ns(intervals), 70)
        self.assertEqual(interval_union_ns(intervals, window=(5, 100)), 45)

    def test_correlation_coverage_requires_request_scheduler_nvtx_and_cuda(self):
        fixture = {
            "requests": [
                {"request_id": "r1", "start_ns": 0, "end_ns": 100},
                {"request_id": "r2", "start_ns": 100, "end_ns": 200},
            ],
            "scheduler_iterations": [
                {
                    "iteration_id": "i1",
                    "request_ids": ["r1"],
                    "phase": "decode",
                    "start_ns": 0,
                    "end_ns": 100,
                },
                {
                    "iteration_id": "i2",
                    "request_ids": ["r2"],
                    "phase": "decode",
                    "start_ns": 100,
                    "end_ns": 200,
                },
            ],
            "nvtx_ranges": [
                {"iteration_id": "i1", "start_ns": 10, "end_ns": 90},
                {"iteration_id": "i2", "start_ns": 110, "end_ns": 190},
            ],
            "cuda_activities": [
                {
                    "iteration_id": "i1",
                    "correlation_id": "c1",
                    "family": "dense_gemm_gemv",
                    "start_ns": 20,
                    "end_ns": 60,
                },
                {
                    "iteration_id": "i1",
                    "correlation_id": "c2",
                    "family": "dense_gemm_gemv",
                    "start_ns": 50,
                    "end_ns": 80,
                },
                {
                    "iteration_id": "i1",
                    "correlation_id": "c3",
                    "family": "other",
                    "start_ns": 80,
                    "end_ns": 90,
                },
            ],
            "host_intervals": [
                {
                    "iteration_id": "i1",
                    "category": "launch_gap",
                    "start_ns": 0,
                    "end_ns": 20,
                }
            ],
        }

        result = correlation_summary(fixture)

        self.assertEqual(result["eligible_iterations"], 2)
        self.assertEqual(result["covered_iterations"], 1)
        self.assertEqual(result["coverage_fraction"], 0.5)
        self.assertEqual(result["covered_dependency_union_ns"], 90)
        self.assertEqual(result["dense_union_ns"], 60)
        self.assertAlmostEqual(result["dense_dependency_share"], 2 / 3)
        self.assertAlmostEqual(result["host_dependency_share"], 2 / 9)
        self.assertEqual(result["uncovered_iteration_ids"], ["i2"])

    def test_sqlite_fixture_loader_decodes_request_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.sqlite"
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE TABLE requests(request_id TEXT, start_ns INTEGER, end_ns INTEGER)"
            )
            connection.execute(
                "CREATE TABLE scheduler_iterations(iteration_id TEXT, request_ids TEXT, phase TEXT, start_ns INTEGER, end_ns INTEGER)"
            )
            connection.execute("INSERT INTO requests VALUES ('r1', 0, 100)")
            connection.execute(
                "INSERT INTO scheduler_iterations VALUES ('i1', '[\"r1\"]', 'decode', 0, 100)"
            )
            connection.commit()
            connection.close()

            fixture = load_sqlite_fixture(path)

        self.assertEqual(fixture["scheduler_iterations"][0]["request_ids"], ["r1"])
        self.assertEqual(fixture["nvtx_ranges"], [])

    def test_observer_effect_uses_bracket_mean_and_fixed_gates(self):
        passing = observer_effect(
            {"throughput": 100.0, "median_latency_ms": 10.0, "tail_latency_ms": 20.0},
            {"throughput": 98.0, "median_latency_ms": 10.2, "tail_latency_ms": 20.8},
            {"throughput": 102.0, "median_latency_ms": 10.0, "tail_latency_ms": 20.0},
        )
        self.assertTrue(passing["pass"])
        self.assertAlmostEqual(passing["effects"]["throughput_fraction"], -3 / 101)

        failing = observer_effect(
            {"throughput": 100.0, "median_latency_ms": 10.0, "tail_latency_ms": 20.0},
            {"throughput": 96.0, "median_latency_ms": 10.4, "tail_latency_ms": 21.2},
            {"throughput": 100.0, "median_latency_ms": 10.0, "tail_latency_ms": 20.0},
        )
        self.assertFalse(failing["pass"])
        self.assertEqual(
            failing["breached_gates"],
            ["median_latency", "tail_latency", "throughput"],
        )

    def test_route_selection_prioritizes_validity_then_host_then_dense(self):
        self.assertEqual(
            select_route(
                coverage_fraction=0.94,
                observer_valid=True,
                dense_dependency_share=0.8,
                host_dependency_share=0.0,
                adjusted_r_squared=0.0,
            )["route"],
            "instrumentation_failure",
        )
        self.assertEqual(
            select_route(
                coverage_fraction=0.99,
                observer_valid=True,
                dense_dependency_share=0.5,
                host_dependency_share=0.12,
                adjusted_r_squared=0.1,
            )["route"],
            "host_scheduler_route",
        )
        self.assertEqual(
            select_route(
                coverage_fraction=0.99,
                observer_valid=True,
                dense_dependency_share=0.1,
                host_dependency_share=0.05,
                adjusted_r_squared=0.1,
            )["route"],
            "not_dense_route",
        )
        self.assertEqual(
            select_route(
                coverage_fraction=0.99,
                observer_valid=True,
                dense_dependency_share=0.4,
                host_dependency_share=0.05,
                adjusted_r_squared=0.1,
                memory_throughput_normalized=0.75,
                sm_active_normalized=0.5,
            )["route"],
            "dense_memory_route",
        )
        self.assertEqual(
            select_route(
                coverage_fraction=0.99,
                observer_valid=True,
                dense_dependency_share=0.4,
                host_dependency_share=0.05,
                adjusted_r_squared=0.1,
                compute_or_occupancy_dominant=True,
            )["route"],
            "dense_compute_or_occupancy_route",
        )

    def test_cli_is_deterministic_for_json_fixture(self):
        fixture = {
            "requests": [{"request_id": "r1", "start_ns": 0, "end_ns": 100}],
            "scheduler_iterations": [
                {
                    "iteration_id": "i1",
                    "request_ids": ["r1"],
                    "phase": "decode",
                    "start_ns": 0,
                    "end_ns": 100,
                }
            ],
            "nvtx_ranges": [{"iteration_id": "i1", "start_ns": 0, "end_ns": 100}],
            "cuda_activities": [
                {
                    "iteration_id": "i1",
                    "correlation_id": "c1",
                    "family": "dense_gemm_gemv",
                    "start_ns": 0,
                    "end_ns": 100,
                }
            ],
            "host_intervals": [],
            "observer_arms": {
                "A1": {"throughput": 100, "median_latency_ms": 10, "tail_latency_ms": 20},
                "B1": {"throughput": 100, "median_latency_ms": 10, "tail_latency_ms": 20},
                "A2": {"throughput": 100, "median_latency_ms": 10, "tail_latency_ms": 20},
            },
            "resource_metrics": {"memory_throughput_normalized": 0.8, "sm_active_normalized": 0.5},
            "adjusted_r_squared": 0.0,
        }
        expected = analyze_fixture(fixture)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixture.json"
            output = Path(directory) / "result.json"
            source.write_text(json.dumps(fixture))
            subprocess.run(
                [sys.executable, str(NEBIUS / "analyze_nsys_observer.py"), "--json", str(source), "--output", str(output)],
                check=True,
            )
            observed = json.loads(output.read_text())
        self.assertEqual(observed, expected)


if __name__ == "__main__":
    unittest.main()
