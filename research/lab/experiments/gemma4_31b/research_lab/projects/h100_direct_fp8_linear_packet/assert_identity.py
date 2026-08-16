#!/usr/bin/env python3
import hashlib
import json
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


packet = json.loads((HERE / "START_PACKET.json").read_text())
audit = json.loads((HERE / "BEHAVIORAL_AUDIT.json").read_text())
manifest = json.loads((HERE / "STAGED_MANIFEST.json").read_text())
files = {
    "h100_contract.py": HERE / "h100_contract.py",
    "h100_direct_fp8_kernel.py": HERE / "h100_direct_fp8_kernel.py",
    "remote_stage.sh": HERE / "remote_stage.sh",
    "SOURCE_MANIFEST.json": HERE / "SOURCE_MANIFEST.json",
    "STAGED_MANIFEST.json": HERE / "STAGED_MANIFEST.json",
}
observed = {name: sha(path) for name, path in files.items()}
checks = {
    "packet_pass": packet.get("pass") is True,
    "behavioral_audit_pass": audit.get("pass") is True,
    "manifest_matches_files": all(manifest["remote_files"].get(name) == observed[name] for name in manifest["remote_files"]),
    "packet_matches_files": packet["identity"]["program_sha256"] == observed["h100_direct_fp8_kernel.py"]
    and packet["identity"]["wrapper_sha256"] == observed["remote_stage.sh"],
    "exact_h100_identity": packet["identity"]["gpu"] == "NVIDIA H100 80GB HBM3"
    and packet["identity"]["compute_capability"] == [9, 0],
    "one_allocation_no_repair": packet["budgets"]["allocation_count"] == 1
    and packet["budgets"]["repair_count"] == 0,
    "sentinel_first": packet["lifecycle"]["primary"]["arm"] == "sliding_qkv M8 sentinel",
}
result = {
    "schema_version": 1,
    "type": "h100_direct_fp8_identity_assertion",
    "packet_sha256": sha(HERE / "START_PACKET.json"),
    "audit_sha256": sha(HERE / "BEHAVIORAL_AUDIT.json"),
    "observed_sha256": observed,
    "checks": checks,
    "pass": all(checks.values()),
}
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path)
args = parser.parse_args()
rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
else:
    print(rendered, end="")
raise SystemExit(0 if result["pass"] else 1)
