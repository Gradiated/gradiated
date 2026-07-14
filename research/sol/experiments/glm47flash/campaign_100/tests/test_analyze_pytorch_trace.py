import sys
import unittest
from pathlib import Path


ANALYSIS = Path(__file__).resolve().parents[1] / "analysis"
sys.path.insert(0, str(ANALYSIS))

from analyze_pytorch_trace import classified_region_summary, kernel_family, region_summary  # noqa: E402


class PytorchTraceAnalysisTests(unittest.TestCase):
    def test_grouped_mla_stage_is_classified_as_attention(self):
        self.assertEqual(kernel_family("_fwd_grouped_kernel_stage1"), "attention_mla")

    def test_missing_region_is_explicit_not_an_exception(self):
        result = region_summary([], lambda name: name.startswith("missing"))
        self.assertEqual(result["region_count"], 0)
        self.assertEqual(result["status"], "unavailable_no_matching_annotations")

    def test_vllm_execution_annotations_separate_decode_from_mixed_prefill(self):
        events = [
            {"cat": "gpu_user_annotation", "ph": "X", "name": "execute_context_0(0)_generation_8(8)", "ts": 0, "dur": 100},
            {"cat": "kernel", "ph": "X", "name": "decode_kernel", "ts": 10, "dur": 20},
            {"cat": "gpu_user_annotation", "ph": "X", "name": "execute_context_6(49152)_generation_2(2)", "ts": 200, "dur": 100},
            {"cat": "kernel", "ph": "X", "name": "prefill_kernel", "ts": 210, "dur": 30},
        ]
        result = classified_region_summary(events)
        self.assertEqual(result["decode"]["kernel_count"], 1)
        self.assertEqual(result["prefill_or_mixed"]["kernel_count"], 1)


if __name__ == "__main__":
    unittest.main()
