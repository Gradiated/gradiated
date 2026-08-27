from __future__ import annotations

import unittest

from kda_sweep import (
    KDAWorkload,
    Architecture,
    evaluate,
    pareto_frontier,
    required_local_bytes,
    run_sweep,
    workload_counts,
)


class KDASweepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workload = KDAWorkload()
        self.base = Architecture(
            name="base",
            kind="fpga",
            mac_units=256,
            clock_mhz=200,
            external_bandwidth_gbps=64.0,
            local_bandwidth_gbps=32.0,
            sram_kb=128,
            fused=False,
            local_state=False,
            weights_local=False,
            double_buffered=False,
            compute_efficiency=0.60,
            memory_efficiency=0.55,
            vector_lanes=32,
            launch_overhead_ns=0.0,
            static_power_w=2.5,
        )

    def test_workload_counts_are_deterministic_and_positive(self) -> None:
        first = workload_counts(self.workload)
        second = workload_counts(self.workload)
        self.assertEqual(first, second)
        self.assertGreater(first["macs"], 0)
        self.assertGreater(first["state_bytes"], 0)

    def test_local_state_reduces_external_bytes(self) -> None:
        local = Architecture(**{**self.base.__dict__, "local_state": True})
        base_result = evaluate(self.workload, self.base)
        local_result = evaluate(self.workload, local)
        self.assertLess(local_result["external_bytes"], base_result["external_bytes"])

    def test_fusion_and_double_buffering_reduce_or_match_latency(self) -> None:
        candidate = Architecture(
            **{
                **self.base.__dict__,
                "name": "candidate",
                "fused": True,
                "local_state": True,
                "weights_local": True,
                "double_buffered": True,
                "sram_kb": 128,
                "local_bandwidth_gbps": 128.0,
            }
        )
        base_result = evaluate(self.workload, self.base)
        candidate_result = evaluate(self.workload, candidate)
        self.assertTrue(candidate_result["fits_kv260"])
        self.assertLessEqual(candidate_result["latency_us"], base_result["latency_us"])

    def test_insufficient_sram_rejects_local_state_candidate(self) -> None:
        tiny = Architecture(**{**self.base.__dict__, "sram_kb": 32, "local_state": True})
        self.assertGreater(required_local_bytes(self.workload, tiny), tiny.sram_kb * 1024)
        self.assertFalse(evaluate(self.workload, tiny)["fits_kv260"])

    def test_sweep_has_controls_candidates_and_frontier(self) -> None:
        result = run_sweep()
        self.assertEqual(result["experiment"]["evidence_class"], "analytical")
        self.assertGreater(result["all_row_count"], result["candidate_count"])
        self.assertGreater(result["candidate_count"], 0)
        self.assertGreater(len(result["pareto_frontier"]), 0)
        self.assertEqual(result["controls"][0]["kind"], "gpu")

    def test_frontier_contains_only_feasible_fpga_rows(self) -> None:
        result = run_sweep()
        frontier = pareto_frontier(result["rows"]) if "rows" in result else result["pareto_frontier"]
        self.assertTrue(all(row["kind"] == "fpga" and row["fits_kv260"] for row in frontier))


if __name__ == "__main__":
    unittest.main()
