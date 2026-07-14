from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from grad_research.preflight import PreflightError, verify_identity_manifest, verify_recorded_fixture


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PreflightTests(unittest.TestCase):
    def test_checkpoint_index_closure_and_file_identity_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shard_one = root / "model-00001.safetensors"
            shard_two = root / "model-00002.safetensors"
            shard_one.write_bytes(b"one")
            shard_two.write_bytes(b"two")
            index = root / "model.safetensors.index.json"
            index.write_text(json.dumps({"weight_map": {"a": shard_one.name, "b": shard_two.name}}))
            manifest = root / "checkpoint.manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "index_path": index.name,
                "files": [
                    {"path": path.name, "size_bytes": path.stat().st_size, "sha256": digest(path)}
                    for path in (index, shard_one, shard_two)
                ],
            }, sort_keys=True))
            report = verify_identity_manifest(
                root,
                manifest,
                expected_manifest_sha256=digest(manifest),
                require_index_closure=True,
            )
            self.assertTrue(report["pass"])
            self.assertEqual(2, report["index_closure"]["referenced_shard_count"])

    def test_checkpoint_index_rejects_an_unbound_shard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "model.safetensors.index.json"
            index.write_text(json.dumps({"weight_map": {"a": "missing.safetensors"}}))
            manifest = root / "checkpoint.manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "index_path": index.name,
                "files": [{"path": index.name, "size_bytes": index.stat().st_size, "sha256": digest(index)}],
            }))
            with self.assertRaisesRegex(PreflightError, "unbound shards"):
                verify_identity_manifest(
                    root,
                    manifest,
                    expected_manifest_sha256=digest(manifest),
                    require_index_closure=True,
                )

    def test_changed_tokenizer_and_recorded_fixture_fail_locally(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tokenizer = root / "tokenizer.json"
            tokenizer.write_text("authoritative")
            manifest = root / "tokenizer.manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "files": [{"path": tokenizer.name, "size_bytes": tokenizer.stat().st_size, "sha256": digest(tokenizer)}],
            }))
            expected_manifest = digest(manifest)
            tokenizer.write_text("wrong repository tokenizer")
            with self.assertRaisesRegex(PreflightError, "size mismatch|hash mismatch"):
                verify_identity_manifest(root, manifest, expected_manifest_sha256=expected_manifest)

            fixture = root / "provider-response.json"
            fixture.write_text("{}")
            expected = digest(fixture)
            fixture.write_text('{"changed":true}')
            with self.assertRaisesRegex(PreflightError, "fixture hash mismatch"):
                verify_recorded_fixture(fixture, expected_fixture_sha256=expected, bound_sha256="a" * 64)


if __name__ == "__main__":
    unittest.main()
