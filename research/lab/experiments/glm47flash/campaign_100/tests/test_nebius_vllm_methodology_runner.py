import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "nebius" / "vllm_methodology_runner.py"
spec = importlib.util.spec_from_file_location("vllm_methodology_runner", SOURCE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
with patch.dict(
    sys.modules,
    {"tiktoken": types.SimpleNamespace(get_encoding=lambda _name: object())},
):
    spec.loader.exec_module(module)


class VllmMethodologyRunnerTests(unittest.TestCase):
    def test_stream_token_ids_are_retained_as_an_order_free_histogram(self):
        histogram = {}
        self.assertEqual(module.accumulate_output_token_histogram(histogram, [7, 7, 3]), 3)
        self.assertEqual(histogram, {3: 1, 7: 2})
        with self.assertRaises(module.MethodologyError):
            module.accumulate_output_token_histogram(histogram, "invalid")
        source = SOURCE.read_text()
        self.assertIn('"output_token_histogram"', source)
        self.assertIn('"output_token_ids_complete"', source)


if __name__ == "__main__":
    unittest.main()
