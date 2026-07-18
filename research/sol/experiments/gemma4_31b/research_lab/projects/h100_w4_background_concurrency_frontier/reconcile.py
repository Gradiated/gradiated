#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "artifacts" / "gemma-h100-w4-frontier-20260717t22121784319137z"
CEILING = 0.5479752315195353


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    primary = json.loads((ARTIFACT / "REPAIRED_PRIMARY.json").read_text())
    with tarfile.open(ARTIFACT / "head-frontier.tar.gz") as bundle:
        member = next(item for item in bundle.getmembers() if item.name.endswith("/stage-terminal.json"))
        head = json.load(bundle.extractfile(member))["result"]
    head_rows = {str(row["m"]): row for row in head["rows"]}
    combined = {}
    for m, linear in primary["result"]["aggregation"]["by_concurrency"].items():
        head_s = head_rows[m]["per_request_head_seconds_at_358_steps"]
        total = linear["w4_decode_linear_seconds_per_request_at_358_steps"] + head_s
        combined[m] = {"w4_decode_linear_seconds_per_request": linear["w4_decode_linear_seconds_per_request_at_358_steps"], "actual_head_seconds_per_request": head_s, "combined_w4_linear_plus_actual_head_seconds_per_request": total, "residual_to_planning_ceiling_seconds": CEILING-total, "combined_batch_duration_proxy_seconds": linear["w4_decode_batch_duration_seconds_at_358_steps"] + head_s * int(m), "component_plausible_only": total < CEILING}
    cleanup = json.loads((ARTIFACT / "cleanup.json").read_text())
    summary = json.loads((ARTIFACT / "summary.json").read_text())
    result = {"schema_version": 1, "classification": "measured_h100_w4_background_component_frontier", "pass": bool(primary["pass"] and head["pass"] and cleanup.get("cleanup_pass") is True), "evidence_boundary": "Measured generated-token W4 linear plus actual tied-head components only; excludes prompt linears, attention, KV, scheduler, full-request throughput, checkpoint quality, and endpoint eligibility.", "planning_ceiling_seconds_per_request": CEILING, "primary": {"path": "REPAIRED_PRIMARY.json", "sha256": sha(ARTIFACT / "REPAIRED_PRIMARY.json"), "rows": len(primary["result"]["rows"])}, "head": {"path": "head-frontier.tar.gz", "sha256": sha(ARTIFACT / "head-frontier.tar.gz"), "rows": len(head["rows"])}, "combined_by_concurrency": combined, "ranked_survivors": sorted(combined, key=lambda m: combined[m]["residual_to_planning_ceiling_seconds"], reverse=True), "cleanup": cleanup, "provider_summary": {key: summary[key] for key in ("allocation_seconds", "cost_usd_derived", "instance_id", "cleanup_pass")}}
    target = ARTIFACT / "RECONCILED_FRONTIER_TERMINAL.json"; target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["pass"] else 1


if __name__ == "__main__": raise SystemExit(main())
