#!/usr/bin/env python3
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "inputs" / "bound"
EXPECTED = {
    "DIRECTOR_BINDING.json": "ec9f865374d9f56b8342d81649dbddecd49594aaf9668cac856ea3a4ff8c5c6b",
    "canonical_ngram_launch.json": "8349853a7eac9e73211f5d3081c834c05f78e0fd292ddbe5acb921b1824a523d",
    "exact_semantic_rows.jsonl": "630d05bd860d1dd22c3e35ba2d8f792afc5051f0c68e0a74a9deda8140a02b36",
    "streamed_tail_binding.json": "b1934d88f5ea3e13944c1a26db3f59734096300380bc97311afc30f10cdcf7b2",
    "streamed_tail_rows.jsonl": "5658b431b4db0e445d320c5e90a1fcd7c50ae437e5a1809ee068ca068ada4deb",
    "streamed_tail_terminal.json": "8c92c806ff758fc9b6bc3f75ce6b2d3f3b8ac4cbcaf0b7d096fefc8cdd2c7b73",
    "tail_overlap_terminal.json": "ea83796c0ad6f5e366fc42b910db81a96f16ead3db921c830d0cfef91358f3b5",
}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def atomic(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)

def main():
    checks = {}
    for name, wanted in EXPECTED.items():
        path = ROOT / name if name == "DIRECTOR_BINDING.json" else INPUT / name
        actual = digest(path)
        checks[name] = {"path": str(path), "expected_sha256": wanted, "actual_sha256": actual, "matches": actual == wanted}
    inputs = json.loads((INPUT / "SHA256SUMS.json").read_text())
    for name, wanted in inputs.items():
        actual = digest(INPUT / name)
        checks[f"input:{name}"] = {"path": str(INPUT / name), "expected_sha256": wanted, "actual_sha256": actual, "matches": actual == wanted}
    result = "all_bound_identities_and_hashes_match" if all(row["matches"] for row in checks.values()) else "binding_mismatch"
    atomic(ROOT / "BINDING_VERIFIED.json", {"verified_at_utc": datetime.now(UTC).isoformat(), "result": result, "checks": checks, "local_input_snapshot": str(INPUT)})
    if result != "all_bound_identities_and_hashes_match":
        raise SystemExit(result)

if __name__ == "__main__":
    main()
