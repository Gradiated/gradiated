import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from simulate_verification_depth_oracle import load_bound_rows


class BoundInputTest(unittest.TestCase):
    def test_rejects_modified_input_before_parse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.jsonl"
            manifest_path = root / "manifest.json"
            original = b'{"request_id":"real"}\n'
            input_path.write_bytes(original)
            manifest_path.write_text(
                json.dumps(
                    {
                        "content": {
                            "sha256": hashlib.sha256(original).hexdigest(),
                        }
                    }
                )
            )
            input_path.write_bytes(b'{"request_id":"modified"}\n')
            with self.assertRaisesRegex(ValueError, "input hash"):
                load_bound_rows(input_path, manifest_path)


if __name__ == "__main__":
    unittest.main()
