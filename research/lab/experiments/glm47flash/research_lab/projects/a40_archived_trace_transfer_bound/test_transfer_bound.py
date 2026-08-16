import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).parent


class TransferBoundTest(unittest.TestCase):
    def test_result_is_deterministic_and_preserves_partial_identification(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.json"
            completed = subprocess.run(
                [sys.executable, str(PROJECT / "analyze_transfer_bound.py"), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.stdout, "")
            result = json.loads(output.read_text())
        self.assertEqual(result["decision"], "CONDITIONAL_DIRECT_A40_C8_MEASUREMENT_ONLY")
        self.assertLess(result["bands"]["conservative_compute_bound"]["output_tokens_per_second"], result["economic_gates"]["five_percent_cost_gate_tok_s"])
        self.assertGreater(result["bands"]["central_trace_classification"]["output_tokens_per_second"], result["economic_gates"]["strong_0_60_per_million_tok_s"])
        self.assertFalse(result["identification"]["archive_can_promote_or_close"])
        self.assertEqual(result["next_decisive_signal"]["signal"], "matched_A40_c8_8192x1024_aggregate_output_tokens_per_second")

