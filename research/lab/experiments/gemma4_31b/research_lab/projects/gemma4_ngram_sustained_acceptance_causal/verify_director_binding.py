#!/usr/bin/env python3
"""Mechanical hash check for the admitted request-local endpoint."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    binding = json.loads((ROOT / "DIRECTOR_BINDING.json").read_text())
    checks = {}
    for name, row in binding["evidence"].items():
        path = Path(row["path"])
        got = sha(path)
        checks[name] = {"path": str(path), "expected_sha256": row["sha256"], "actual_sha256": got, "matches": got == row["sha256"]}
    local = {
        "ngram-launch.json": binding["evidence"]["canonical_launch"]["sha256"],
        "exact_semantic_rows.jsonl": binding["evidence"]["exact_semantic_rows"]["sha256"],
        "ngram_worker.source.py": binding["source_identity"]["ngram_worker.py"],
    }
    for name, wanted in local.items():
        path = ROOT / "inputs" / "bound" / name
        got = sha(path)
        checks[f"local:{name}"] = {"path": str(path), "expected_sha256": wanted, "actual_sha256": got, "matches": got == wanted}
    result = "all_six_director_identities_and_local_snapshot_match" if all(x["matches"] for x in checks.values()) else "binding_mismatch"
    out = {"verified_at_utc": datetime.now(UTC).isoformat(), "result": result, "checks": checks}
    tmp = ROOT / ".DIRECTOR_BINDING_VERIFIED.json.part"
    tmp.write_text(json.dumps(out, sort_keys=True, indent=2) + "\n")
    tmp.replace(ROOT / "DIRECTOR_BINDING_VERIFIED.json")
    if result != "all_six_director_identities_and_local_snapshot_match":
        raise SystemExit(result)

if __name__ == "__main__":
    main()
