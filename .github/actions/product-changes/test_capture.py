import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "relevant/capture.sh"


class CaptureSelectionTest(unittest.TestCase):
    def capture(self, changed_path, event="pull_request"):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def git(*args):
                subprocess.run(
                    ["git", *args], cwd=root, check=True, capture_output=True
                )

            git("init")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Test")
            (root / "source.ts").write_text("initial")
            git("add", ".")
            git("commit", "-m", "initial")
            path = root / changed_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("changed")
            git("add", ".")
            git("commit", "-m", "arbitrary commit subject")
            output = root / "output"
            subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=root,
                check=True,
                env={**os.environ, "EVENT_NAME": event, "GITHUB_OUTPUT": str(output)},
            )
            return output.read_text().strip()

    def test_console_snapshot_skips_both_workflows(self):
        self.assertEqual(
            self.capture("product/services/console/screenshots/page.png"),
            "capture=false",
        )

    def test_website_snapshot_skips_both_workflows(self):
        self.assertEqual(
            self.capture("product/website/screenshots/page.png"), "capture=false"
        )

    def test_source_changes_capture(self):
        self.assertEqual(self.capture("product/website/src/page.tsx"), "capture=true")

    def test_non_snapshot_images_capture(self):
        self.assertEqual(
            self.capture("product/website/public/logo.png"), "capture=true"
        )

    def test_main_and_manual_events_capture(self):
        for event in ("push", "workflow_dispatch"):
            self.assertEqual(
                self.capture("product/website/screenshots/page.png", event),
                "capture=true",
            )


if __name__ == "__main__":
    unittest.main()
