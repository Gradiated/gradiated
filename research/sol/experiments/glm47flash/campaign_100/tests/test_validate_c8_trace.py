import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from validate_c8_trace import validate  # noqa: E402


class ValidateC8TraceTests(unittest.TestCase):
    def test_true_c8_geometry_and_grid_pass(self):
        admission = {"profile_scope": "fixed_8k_128_c8", "concurrency": 8, "requests": 8, "exact_geometry_pass": True}
        event = {"cat": "kernel", "ph": "X", "name": "_fwd_grouped_kernel_stage1", "dur": 4, "args": {"grid": [8, 2, 4], "block": [128, 1, 1], "registers per thread": 202, "shared memory": 89088}}
        result = validate(admission, [event] * 10)
        self.assertTrue(result["pass"])
        self.assertIn("not phase-scoped wall-time", result["claim_limit"])

    def test_old_c1_capture_fails_closed(self):
        admission = {"profile_scope": "fixed_8k_128_c1", "concurrency": 1, "requests": 1, "exact_geometry_pass": True}
        event = {"cat": "kernel", "ph": "X", "name": "_fwd_grouped_kernel_stage1", "dur": 4, "args": {"grid": [1, 2, 4]}}
        self.assertFalse(validate(admission, [event])["pass"])


if __name__ == "__main__":
    unittest.main()
