#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def main() -> None:
    path = ROOT / "DIRECTOR_ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_BINDING.json"
    binding = json.loads(path.read_text())
    rows = []
    for name, item in binding["bound_inputs"].items():
        target = (ROOT / item["path"]).resolve()
        actual = sha(target) if target.exists() else None
        rows.append({"name": name, "path": str(target), "expected_sha256": item["sha256"], "actual_sha256": actual, "match": actual == item["sha256"]})
    result = {
        "schema_version": 1,
        "binding_path": str(path),
        "binding_sha256": sha(path),
        "expected_binding_sha256": "6168e592905625e593e759785e316ade538baa6c9de883c0855d6ad50c7c2a69",
        "binding_match": sha(path) == "6168e592905625e593e759785e316ade538baa6c9de883c0855d6ad50c7c2a69",
        "bound_inputs": rows,
        "all_bound_hashes_match": all(row["match"] for row in rows),
    }
    if not result["binding_match"] or not result["all_bound_hashes_match"]:
        raise SystemExit(json.dumps(result, indent=2))
    (ROOT / "ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_BINDING_VERIFIED.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == "__main__": main()
