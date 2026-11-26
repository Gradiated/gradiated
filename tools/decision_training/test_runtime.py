import hashlib
import json
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from audit_tokens import terminating_pool, verify_tokenizer_directory
from runtime import runtime_fingerprint


class RuntimeIdentityTests(unittest.TestCase):
    def test_package_scan_checks_its_owner_deadline(self):
        def expired():
            raise TimeoutError("owner deadline")

        with self.assertRaisesRegex(TimeoutError, "owner deadline"):
            runtime_fingerprint(expired)

    def test_lazily_loaded_same_version_package_file_is_bound(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "lazy_adapter.py"
            path.write_text("# first implementation")
            specification = SimpleNamespace(submodule_search_locations=[str(root)])
            with patch("runtime.util.find_spec", return_value=specification):
                first = runtime_fingerprint()
                path.write_text(
                    "# different implementation not imported into sys.modules"
                )
                self.assertNotEqual(first, runtime_fingerprint())

    def test_token_workers_are_killed_instead_of_draining_after_timeout(self):
        started = time.monotonic()
        processes = []
        with self.assertRaises(TimeoutError), terminating_pool(max_workers=1) as pool:
            iterator = pool.map(time.sleep, [10, 10], timeout=0.05)
            processes = list(pool._processes.values())
            list(iterator)
        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse(any(process.is_alive() for process in processes))

    def test_package_version_and_same_version_implementation_changes_are_bound(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.py"
            path.write_text("# first implementation")
            package = SimpleNamespace(
                read_text=lambda name: json.dumps({"vcs_info": {"commit_id": "frozen"}})
            )
            with (
                patch("runtime.metadata.version", return_value="1"),
                patch("runtime.metadata.distribution", return_value=package),
                patch.dict(
                    sys.modules,
                    {"transformers.test_impl": SimpleNamespace(__file__=str(path))},
                ),
            ):
                first = runtime_fingerprint()
                path.write_text("# different same-version implementation")
                self.assertNotEqual(first, runtime_fingerprint())
                path.write_text("# first implementation")
                with patch("runtime.metadata.version", return_value="2"):
                    self.assertNotEqual(first, runtime_fingerprint())

    def test_tokenizer_rejects_unlisted_load_artifacts_and_modified_bytes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            files = []
            for name in (
                "tokenizer.json",
                "tokenizer_config.json",
                "chat_template.jinja",
            ):
                (root / name).write_text("{}")
                files.append(
                    {"file": name, "sha256": hashlib.sha256(b"{}").hexdigest()}
                )
            manifest = {"files": files}
            verify_tokenizer_directory(root, manifest)
            (root / "added_tokens.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "differ"):
                verify_tokenizer_directory(root, manifest)
            (root / "added_tokens.json").unlink()
            (root / "tokenizer_config.json").write_text("[]")
            with self.assertRaisesRegex(ValueError, "mismatch"):
                verify_tokenizer_directory(root, manifest)


if __name__ == "__main__":
    unittest.main()
