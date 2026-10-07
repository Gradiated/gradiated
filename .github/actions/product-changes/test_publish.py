import os
import subprocess
import tempfile
import unittest
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / "workflows"


def publisher(name):
    workflow = (WORKFLOWS / f"{name}.yml").read_text()
    commit = workflow.split("      - name: Commit informative screenshots\n", 1)[1]
    script = commit.split("        run: |\n", 1)[1].split("      - name:", 1)[0]
    return "\n".join(line[10:] for line in script.splitlines()) + "\n"


class ScreenshotPublicationTest(unittest.TestCase):
    def publish_after_branch_change(self, changed_path):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote, capture, sibling = [root / name for name in ("remote", "capture", "sibling")]

            def git(cwd, *args):
                return subprocess.run(
                    ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
                ).stdout.strip()

            git(root, "init", "--bare", str(remote))
            git(root, "clone", str(remote), str(capture))
            git(capture, "config", "user.email", "test@example.com")
            git(capture, "config", "user.name", "Test")
            (capture / "source.ts").write_text("initial")
            git(capture, "add", ".")
            git(capture, "commit", "-m", "initial")
            git(capture, "push", "origin", "HEAD:refs/heads/pr")
            initial = git(capture, "rev-parse", "HEAD")
            git(root, "clone", "--branch", "pr", str(remote), str(sibling))
            git(sibling, "config", "user.email", "test@example.com")
            git(sibling, "config", "user.name", "Test")
            path = sibling / changed_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("sibling change")
            git(sibling, "add", ".")
            git(sibling, "commit", "-m", "branch advanced during capture")
            git(sibling, "push", "origin", "pr")
            screenshots = capture / "product/website/screenshots"
            screenshots.mkdir(parents=True)
            (screenshots / "home.png").write_text("website capture")
            output = root / "output"
            script = root / "publish.sh"
            script.write_text(publisher("website-screenshots"))
            subprocess.run(
                ["bash", str(script)], cwd=capture, check=True, capture_output=True,
                env={**os.environ, "PR_BRANCH": "pr", "PR_SHA": initial,
                     "SCREENSHOT_PATH": "product/website/screenshots",
                     "COMMIT_MESSAGE": "website screenshots", "GITHUB_OUTPUT": str(output)},
            )
            git(sibling, "pull", "--ff-only")
            return (sibling / "product/website/screenshots/home.png").exists(), path.read_text(), output.exists()

    def test_publishers_share_the_same_race_handling(self):
        self.assertEqual(publisher("storybook"), publisher("website-screenshots"))

    def test_sibling_capture_is_preserved_and_both_sets_publish(self):
        published, sibling, output = self.publish_after_branch_change(
            "product/services/console/screenshots/page.png"
        )
        self.assertTrue(published)
        self.assertEqual(sibling, "sibling change")
        self.assertTrue(output)

    def test_changed_source_discards_outdated_capture(self):
        published, source, output = self.publish_after_branch_change("source.ts")
        self.assertFalse(published)
        self.assertEqual(source, "sibling change")
        self.assertFalse(output)


if __name__ == "__main__":
    unittest.main()
