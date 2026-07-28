import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import unittest


TOOL = pathlib.Path(__file__).parents[1] / "tools" / "detached-owner"


class DetachedOwnerTests(unittest.TestCase):
    def test_owner_survives_launcher_and_reports_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            state = root / "owner.json"
            log = root / "owner.log"
            done = root / "done"
            command = [
                sys.executable,
                "-c",
                (
                    "import pathlib,time;"
                    "time.sleep(0.2);"
                    f"pathlib.Path({str(done)!r}).write_text('done')"
                ),
            ]

            launched = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "start",
                    "--state",
                    str(state),
                    "--log",
                    str(log),
                    "--unit-manager",
                    "pid",
                    "--",
                    *command,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            owner = json.loads(launched.stdout)
            self.assertTrue(owner["live"])
            self.assertEqual(owner["unit_manager"], "pid")

            deadline = time.monotonic() + 3
            while not done.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(done.read_text(), "done")

            status = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "status",
                    "--state",
                    str(state),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.returncode, 3)
            self.assertFalse(json.loads(status.stdout)["live"])

    def test_live_owner_cannot_be_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            state = root / "owner.json"
            log = root / "owner.log"
            command = [sys.executable, "-c", "import time; time.sleep(2)"]
            start = [
                sys.executable,
                str(TOOL),
                "start",
                "--state",
                str(state),
                "--log",
                str(log),
                "--",
                *command,
            ]
            launched = subprocess.run(
                start, check=True, capture_output=True, text=True
            )
            process = json.loads(launched.stdout)
            self.assertEqual(process["unit_manager"], "remote-shell")
            try:
                duplicate = subprocess.run(
                    start, check=False, capture_output=True, text=True
                )
                self.assertEqual(duplicate.returncode, 2)
                self.assertIn("owner_already_live", duplicate.stderr)
            finally:
                if pathlib.Path(f"/proc/{process['pid']}").exists():
                    os.killpg(process["pid"], signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
