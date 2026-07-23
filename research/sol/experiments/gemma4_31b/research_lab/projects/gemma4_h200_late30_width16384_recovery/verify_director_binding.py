#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
binding = json.loads((root / "DIRECTOR_BINDING.json").read_text())

checks = [
    ("checkpoint", "manifest_path", "manifest_sha256"),
    ("factor_archive", "path", "sha256"),
    ("factor_manifest", "path", "sha256"),
    ("full_recovery_terminal", "path", "sha256"),
    ("layer_results", "path", "sha256"),
    ("qualified_ring_comparator", "path", "sha256"),
    ("selection", "path", "sha256"),
    ("workload_runner", "path", "sha256"),
]
for section, path_key, hash_key in checks:
    path = (root / binding[section][path_key]).resolve()
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = binding[section][hash_key]
    if actual != expected:
        raise SystemExit(f"{section}: expected {expected}, got {actual}: {path}")

rows = json.loads((root / binding["layer_results"]["path"]).read_text())["rows"]
selected = [row for row in rows if 30 <= row["layer"] <= 59]
if len(selected) != 30 or any(row["rank"] != 256 or not row["finite"] for row in selected):
    raise SystemExit("late-30 factor rows are not exactly 30 finite rank-256 rows")
if any(row["residual_energy_recovered_fraction"] <= 0.91 for row in selected):
    raise SystemExit("late-30 residual recovery evidence no longer matches the director decision")
print(json.dumps({"binding": "valid", "late30_rows": len(selected)}))
