from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation.ramulator_adapter.run import run


class RunTests(unittest.TestCase):
    def test_source_validation_failure_writes_blocked_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "blocked.json"
            report = run(
                root / "missing-source",
                root / "raw",
                output,
                root,
            )
            persisted = json.loads(output.read_text())
            self.assertEqual(report, persisted)
            self.assertEqual(report["status"], "blocked")
            self.assertFalse(report["claims"]["native_oracle_operability"])
            self.assertIn("execution_error", report["build"])


if __name__ == "__main__":
    unittest.main()
