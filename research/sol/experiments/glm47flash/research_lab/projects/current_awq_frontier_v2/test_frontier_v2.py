import importlib.util
import tempfile
import unittest
from pathlib import Path
import subprocess


SOURCE = Path(__file__).with_name("frontier_v2.py")
spec = importlib.util.spec_from_file_location("frontier_v2", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FrontierV2Tests(unittest.TestCase):
    def test_current_hashes_replace_only_the_frozen_v21_hashes(self):
        script = module.transformed_remote()
        self.assertIn("353a3ff93723c098ac93fb593d4d1b93faede916fe502b005cd503871023e012", script)
        self.assertIn("b6b807f7bfaf4fb4bd3952f58a70d61442620df8e5d8a904dcf4bc6ca7946940", script)
        self.assertNotIn("19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d", script)

    def test_adjacent_ladder_admits_c32_only_with_capacity(self):
        self.assertEqual(module.validate_frontier((1, 8, 16, 32), 32), (1, 8, 16, 32))
        with self.assertRaises(RuntimeError):
            module.validate_frontier((1, 8, 16, 32), 16)

    def test_runner_preserves_two_full_batches_for_c32(self):
        runner = module.transformed_runner()
        self.assertIn("(1, 8, 16, 32)", runner)
        self.assertIn("return 4 if concurrency == 1 else concurrency * 2", runner)

    def test_staging_has_a_content_addressed_adapter(self):
        with tempfile.TemporaryDirectory() as raw:
            manifest = module.write_staging(Path(raw))
        self.assertEqual(len(manifest["staged_files"]), 4)
        self.assertEqual(set(manifest["current_tokenizer_hashes"]), module.TOKENIZER_HASHES)

    def test_create_failure_has_redacted_typed_diagnostic(self):
        with tempfile.TemporaryDirectory() as raw:
            result = subprocess.CompletedProcess(["fixture", "instance", "create"], 3, "token=abc", "capacity exhausted")
            value = module.write_create_diagnostic(Path(raw), result)
        self.assertEqual(value["stage"], "provider_create")
        self.assertEqual(value["returncode"], 3)
        self.assertIn("[REDACTED]", value["stdout"])
        self.assertIn("capacity exhausted", value["stderr"])


if __name__ == "__main__":
    unittest.main()
