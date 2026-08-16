import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SOURCE = Path(__file__).with_name("service_boundary.py")
SPEC = SOURCE.parent.parent / "current_awq_frontier_v2" / "EXPERIMENT_SPEC_V2.json"
spec = importlib.util.spec_from_file_location("service_boundary", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ServiceBoundaryTests(unittest.TestCase):
    def test_spec_requires_current_fixed_frontier(self):
        value = json.loads(SPEC.read_text())
        self.assertEqual(value["frontier"], [1, 8, 16, 32])
        self.assertEqual(value["fixed"]["input_tokens"], 8192)

    def test_absolute_rejects_relative_paths(self):
        with self.assertRaises(RuntimeError):
            module.absolute(Path("relative"))

    def test_terminal_is_canonical_json(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            module.terminal(root, {"pass": True, "kind": "fixture"})
            self.assertEqual(json.loads((root / "precreate-terminal.json").read_text())["pass"], True)


if __name__ == "__main__":
    unittest.main()
