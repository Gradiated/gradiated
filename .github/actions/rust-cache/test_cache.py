"""Exercise cache identity and pruning against disposable Rust workspace trees."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ACTION = Path(__file__).resolve().parent


class RustCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, WORKSPACES="workspace", SCOPE="test", MODE="restore",
                        CONFIG_HASH="config", RUNNER_OS="Linux", RUNNER_ARCH="X64",
                        HOME=str(self.root / "home"), GITHUB_OUTPUT=str(self.root / "output"),
                        GITHUB_ENV=str(self.root / "env"))
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        rustc = bin_dir / "rustc"
        rustc.write_text("#!/bin/sh\necho 'rustc fixture-toolchain'\n")
        rustc.chmod(0o755)
        self.env["PATH"] = str(bin_dir) + os.pathsep + self.env["PATH"]
        self.git("init", "-q")
        (self.root / "workspace").mkdir()
        (self.root / "workspace/Cargo.lock").write_text("dependencies")
        self.commit()

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=Cache test", "-c",
                               "user.email=cache@example.invalid", *args], cwd=self.root,
                              check=True, capture_output=True, text=True).stdout

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def prepare(self):
        Path(self.env["GITHUB_OUTPUT"]).write_text("")
        subprocess.run(["bash", str(ACTION / "prepare.sh")], cwd=self.root,
                       env=self.env, check=True, capture_output=True)
        return Path(self.env["GITHUB_OUTPUT"]).read_text().splitlines()[0]

    def test_unrelated_commits_reuse_cache_but_build_assets_invalidate_it(self):
        key = self.prepare()
        (self.root / "README.md").write_text("unrelated commit")
        self.commit()
        self.assertEqual(key, self.prepare())
        (self.root / "workspace/schema.sql").write_text("build script input")
        self.commit()
        self.assertNotEqual(key, self.prepare())
        self.assertIn("CARGO_INCREMENTAL=0", Path(self.env["GITHUB_ENV"]).read_text())

    def test_generated_outputs_do_not_change_save_key(self):
        key = self.prepare()
        (self.root / "workspace/target").mkdir()
        (self.root / "workspace/target/binary").write_text("generated")
        self.env["MODE"] = "save"
        self.assertEqual(key, self.prepare())
        self.env["RUNNER_ARCH"] = "ARM64"
        self.assertNotEqual(key, self.prepare())

    def test_pruning_preserves_compiled_dependencies_and_registry_archives(self):
        removed = ["workspace/target/debug/incremental/state", "workspace/target/x86/release/incremental/state",
                   "home/.cargo/registry/src/crate/source.rs"]
        retained = ["workspace/target/debug/deps/lib.rlib", "workspace/target/debug/.fingerprint/hash",
                    "workspace/target/debug/build/output", "home/.cargo/registry/cache/crate.crate"]
        for name in removed + retained:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture")
        subprocess.run(["bash", str(ACTION / "prune.sh")], cwd=self.root, env=self.env, check=True)
        for name in removed:
            self.assertFalse((self.root / name).exists(), name)
        for name in retained:
            self.assertTrue((self.root / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
