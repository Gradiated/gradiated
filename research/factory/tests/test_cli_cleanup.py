from __future__ import annotations

import subprocess
import sys
import unittest


class CleanupCliTests(unittest.TestCase):
    def test_cleanup_verification_is_an_explicit_coordinator_command(self):
        completed = subprocess.run(
            [sys.executable, "-m", "grad_research", "mark-cleanup-verified", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        for option in (
            "--root",
            "--program",
            "--owner",
            "--allocation-id",
            "--verification-sha256",
            "--get-absent",
            "--inventory-absent",
        ):
            self.assertIn(option, completed.stdout)


if __name__ == "__main__":
    unittest.main()
