import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEBIUS = ROOT / "nebius"
sys.path.insert(0, str(NEBIUS))

from launcher_retention import launcher_bytes, launcher_record, validate_file, write_launcher  # noqa: E402


class LauncherRetentionTests(unittest.TestCase):
    def test_exact_bytes_length_and_hash_round_trip(self):
        payload = b"#!/usr/bin/env bash\nset -Eeuo pipefail\necho A\n"
        record = launcher_record(payload)
        self.assertEqual(record["byte_length"], len(payload))
        self.assertEqual(record["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(launcher_bytes(record), payload)

    def test_fail_closed_mutation_missing_wrong_metadata_and_cross_identity(self):
        payload_a = b"#!/bin/bash\necho fixture-a\n"
        payload_b = b"#!/bin/bash\necho fixture-b\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "launcher.sh"
            record_path = root / "launcher.sh.json"
            record = write_launcher(path, payload_a, record_path)
            self.assertEqual(validate_file(path, record), payload_a)
            path.write_bytes(payload_a + b"#")
            with self.assertRaises(ValueError):
                validate_file(path, record)
            path.unlink()
            with self.assertRaises(ValueError):
                validate_file(path, record)
            path.write_bytes(payload_a)
            wrong_length = {**record, "byte_length": record["byte_length"] + 1}
            with self.assertRaises(ValueError):
                launcher_bytes(wrong_length)
            with self.assertRaises(ValueError):
                validate_file(path, launcher_record(payload_b))
            mutable_substitution = json.loads(record_path.read_text())
            mutable_substitution["bytes"] = launcher_record(payload_b)["bytes"]
            with self.assertRaises(ValueError):
                launcher_bytes(mutable_substitution)

    def test_partial_packaging_names_immutable_inputs(self):
        source = (ROOT / "nebius" / "remote_observer_diagnostic.sh").read_text()
        self.assertIn("host-bootstrap-launcher.sh", source)
        self.assertIn("host-bootstrap-launcher.json", source)


if __name__ == "__main__":
    unittest.main()
