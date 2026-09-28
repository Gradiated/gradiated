from pathlib import Path
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import adapter

EXPLICIT = ["--model", "org/small", "--revision", "r1", "--base", "org/base",
            "--base-revision", "b1", "--upstream-commit", "c1"]


def parse(*argv):
    with contextlib.redirect_stderr(io.StringIO()):
        return adapter.parse_options(list(argv))


class ReleaseOptionTests(unittest.TestCase):
    def test_no_release_flags_select_the_production_pin(self):
        self.assertEqual(parse().release, adapter.Release())

    def test_full_override_is_accepted(self):
        release = parse(*EXPLICIT, "--device", "cpu", "--dtype", "float32", "--allow-unpinned-source").release

        self.assertEqual(release, adapter.Release(model="org/small", revision="r1", base="org/base",
                                                  base_revision="b1", upstream_commit="c1", device="cpu",
                                                  dtype="float32", allow_unpinned=True))

    def test_empty_base_revision_declares_none(self):
        argv = [*EXPLICIT]
        argv[argv.index("b1")] = ""

        self.assertIsNone(parse(*argv).release.base_revision)

    def test_partial_override_is_rejected(self):
        for flag, value in zip(EXPLICIT[::2], EXPLICIT[1::2]):
            with self.subTest(flag), self.assertRaises(SystemExit) as exit:
                parse(flag, value)

            self.assertEqual(exit.exception.code, 2)

    def test_host_and_port_default_to_the_loopback_replica(self):
        options = parse()

        self.assertEqual((options.host, options.port, options.token), ("127.0.0.1", 8009, None))


class TokenFileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "token"

    def read(self, content):
        self.path.write_bytes(content)
        return adapter.read_token(self.path)

    def test_length_is_bounded(self):
        for length, accepted in ((15, False), (16, True), (4096, True), (4097, False)):
            with self.subTest(length):
                if accepted:
                    self.assertEqual(self.read(b"t" * length), b"t" * length)
                else:
                    self.assertRaises(ValueError, self.read, b"t" * length)

    def test_space_is_rejected(self):
        self.assertRaises(ValueError, self.read, b"test-only credential")

    def test_trailing_line_ending_is_stripped(self):
        self.assertEqual(self.read(b"test-only-credential\r\n"), b"test-only-credential")

    def test_invalid_token_file_is_a_usage_error(self):
        self.path.write_bytes(b"short")

        with self.assertRaises(SystemExit) as exit:
            parse("--token-file", str(self.path))

        self.assertEqual(exit.exception.code, 2)


class SourceVerificationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def git(self, *args):
        config = ["-c", "user.name=test", "-c", "user.email=test@invalid", "-c", "commit.gpgsign=false"]
        command = ["git", "-C", str(self.root), *config, *args]
        return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()

    def checkout(self):
        (self.root / "kev").mkdir()
        (self.root / "kev/__init__.py").write_text("")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "pin")
        return self.git("rev-parse", "HEAD")

    def test_clean_pinned_checkout_passes(self):
        adapter.verify_source(self.root, self.checkout(), False)

    def test_other_commit_fails(self):
        self.checkout()

        with self.assertRaisesRegex(RuntimeError, "clean pinned"):
            adapter.verify_source(self.root, "0" * 40, False)

    def test_dirty_kev_source_fails(self):
        commit = self.checkout()
        (self.root / "kev/__init__.py").write_text("changed = True\n")

        with self.assertRaisesRegex(RuntimeError, "clean pinned"):
            adapter.verify_source(self.root, commit, False)

    def test_git_install_at_the_pinned_commit_passes(self):
        adapter.verify_source(self.root, "a" * 40, False, installed="a" * 40)

    def test_git_install_at_another_commit_fails(self):
        with self.assertRaisesRegex(RuntimeError, "pinned commit"):
            adapter.verify_source(self.root, "a" * 40, False, installed="b" * 40)

    def test_missing_checkout_requires_an_explicit_weakening(self):
        with self.assertRaisesRegex(RuntimeError, "--allow-unpinned-source"):
            adapter.verify_source(self.root, "0" * 40, False)

        adapter.verify_source(self.root, "0" * 40, True)

    def test_installed_commit_is_read_from_the_git_install_record(self):
        record = '{"url": "https://github.com/jaredpalmer/kev", "vcs_info": {"vcs": "git", "commit_id": "%s"}}'
        distribution = mock.Mock(read_text=mock.Mock(return_value=record % ("a" * 40)))

        with mock.patch("importlib.metadata.distribution", return_value=distribution):
            self.assertEqual(adapter.installed_commit(), "a" * 40)

    def test_installed_commit_is_absent_without_a_git_install(self):
        distribution = mock.Mock(read_text=mock.Mock(return_value=None))

        with mock.patch("importlib.metadata.distribution", return_value=distribution):
            self.assertIsNone(adapter.installed_commit())

    def test_missing_kev_package_fails_before_any_kev_code_runs(self):
        with mock.patch("importlib.util.find_spec", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Kev is not importable"):
                adapter.load_engine()

    def test_unverified_checkout_fails_before_kev_is_imported(self):
        (self.root / "kev").mkdir()
        (self.root / "kev/__init__.py").write_text("raise AssertionError('kev executed')\n")
        modules = {name: module for name, module in sys.modules.items() if name.partition(".")[0] != "kev"}

        isolated = mock.patch.dict(sys.modules, modules, clear=True)
        on_path = mock.patch.object(sys, "path", [str(self.root), *sys.path])

        with isolated, on_path, self.assertRaisesRegex(RuntimeError, "neither a checkout"):
            adapter.load_engine()
