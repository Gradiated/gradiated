import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "product/services/console/.storybook/ignore-build.sh"
)


class StorybookPreviewSelectionTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.commit("initial.txt")
        self.baseline = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout.strip()

    def commit(self, path):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("change")
        self.git("add", ".")
        self.git("commit", "-m", "change")

    def ignored(self, baseline=None):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=self.root,
            env={
                **os.environ,
                "VERCEL_GIT_PREVIOUS_SHA": self.baseline if baseline is None else baseline,
            },
            capture_output=True,
            text=True,
        )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode == 0

    def test_unrelated_changes_skip(self):
        self.commit("product/website/src/page.tsx")
        self.assertTrue(self.ignored())

    def test_console_source_builds_even_after_an_unrelated_commit(self):
        self.commit("product/services/console/src/page.tsx")
        self.commit("docs/unrelated.md")
        self.assertFalse(self.ignored())

    def test_shared_inputs_build(self):
        for path in (
            "product/packages/contracts/src/index.ts",
            "product/packages/analytics/src/index.ts",
            "product/pnpm-lock.yaml",
            "product/tsconfig.base.json",
            "product/services/console/vercel.json",
            "mise.toml",
        ):
            with self.subTest(path=path):
                self.commit(path)
                self.assertFalse(self.ignored())
                self.baseline = self.git("rev-parse", "HEAD")

    def test_screenshots_and_prose_skip(self):
        self.commit("product/services/console/screenshots/page.png")
        self.commit("product/services/console/README.md")
        self.assertTrue(self.ignored())

    def test_missing_baseline_builds(self):
        self.assertFalse(self.ignored(""))
        self.assertFalse(self.ignored("0" * 40))

    def test_renamed_source_builds(self):
        self.commit("product/services/console/src/old.tsx")
        self.baseline = self.git("rev-parse", "HEAD")
        self.git("mv", "product/services/console/src/old.tsx", "moved.tsx")
        self.git("commit", "-m", "move source out of console")
        self.assertFalse(self.ignored())


if __name__ == "__main__":
    unittest.main()
