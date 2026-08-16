import sys
import unittest
from pathlib import Path


ANALYSIS = Path(__file__).resolve().parents[1] / "analysis"
sys.path.insert(0, str(ANALYSIS))

from compare_trace_regions import compare  # noqa: E402


class TraceRegionComparisonTests(unittest.TestCase):
    def test_large_kernel_saving_without_region_change_is_flagged(self):
        stock = {"decode": {"region_duration_sum_ms": 100, "kernel_duration_sum_ms": 80, "kernel_families": [
            {"family": "attention_mla", "duration_ms": 50}, {"family": "dense", "duration_ms": 30}
        ]}}
        candidate = {"decode": {"region_duration_sum_ms": 101, "kernel_duration_sum_ms": 55, "kernel_families": [
            {"family": "attention_mla", "duration_ms": 25}, {"family": "dense", "duration_ms": 30}
        ]}}
        result = compare(stock, candidate, "decode")
        self.assertEqual(result["diagnosis"], "saved_component_work_not_transferred_to_region_span")
        self.assertEqual(result["largest_saved_family"], "attention_mla")
        self.assertEqual(result["largest_residual_candidate_family"], "dense")


if __name__ == "__main__":
    unittest.main()
