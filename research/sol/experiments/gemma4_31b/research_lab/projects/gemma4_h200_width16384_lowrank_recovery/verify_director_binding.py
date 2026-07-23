#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BINDING = json.loads((ROOT / "DIRECTOR_BINDING.json").read_text())


def verify(entry: dict, path_key: str = "path", hash_key: str = "sha256") -> None:
    path = (ROOT / entry[path_key]).resolve()
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = entry[hash_key]
    if actual != expected:
        raise SystemExit(f"binding mismatch: {path}: expected {expected}, got {actual}")


verify(BINDING["width_selection"])
verify(BINDING["width_endpoint"])
verify(BINDING["cost_floor"])
verify(BINDING["qualified_ring_comparator"])
verify(BINDING["closed_mirrored_fa3_terminal"])
verify(BINDING["checkpoint"], "manifest_path", "manifest_sha256")
print(json.dumps({"binding": "valid", "schema_version": BINDING["schema_version"]}))
