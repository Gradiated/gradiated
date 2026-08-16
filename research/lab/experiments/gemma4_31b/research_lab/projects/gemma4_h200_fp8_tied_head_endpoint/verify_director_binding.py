#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
binding = json.loads((root / "DIRECTOR_BINDING.json").read_text())
checks = [
    ("checkpoint", "manifest_path", "manifest_sha256"),
    ("historical_exact_shape_evidence", "path", "sha256"),
    ("qualified_ring_comparator", "path", "sha256"),
    ("settled_graph_topology", "path", "sha256"),
    ("workload_runner", "path", "sha256"),
]
for section, path_key, hash_key in checks:
    path = (root / binding[section][path_key]).resolve()
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = binding[section][hash_key]
    if actual != expected:
        raise SystemExit(f"{section}: expected {expected}, got {actual}: {path}")
print(json.dumps({"binding": "valid", "geometry": binding["candidate"]}))
