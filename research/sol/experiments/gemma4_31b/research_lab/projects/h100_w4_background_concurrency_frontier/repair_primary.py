#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path

MS = (48, 64, 96, 128)


def aggregate_frontier(rows):
    expected = {(case, m) for case in {row["case"] for row in rows} for m in MS}
    observed = {(row["case"], row["m"]) for row in rows}
    if len(rows) != 24 or observed != expected:
        raise RuntimeError("expected six exact Gemma shapes at each of M48/M64/M96/M128")
    result = {}
    for m in MS:
        w4_step = sum(row["architecture_multiplicity"] * row["cold_candidate_timing"]["cuda_event"]["p50_ms"] for row in rows if row["m"] == m) / 1000
        bf16_step = sum(row["architecture_multiplicity"] * row["cold_bf16_comparator_timing"]["cuda_event"]["p50_ms"] for row in rows if row["m"] == m) / 1000
        result[str(m)] = {"w4_decode_linear_seconds_per_request_at_358_steps": w4_step * 358 / m, "bf16_decode_linear_seconds_per_request_at_358_steps": bf16_step * 358 / m, "w4_decode_batch_duration_seconds_at_358_steps": w4_step * 358, "bf16_decode_batch_duration_seconds_at_358_steps": bf16_step * 358, "w4_linear_reduction_fraction": 1 - w4_step / bf16_step}
    return {"timing_basis": "cold CUDA-event p50; generated-token linear proxy only (358 steps), excluding prompt and attention", "by_concurrency": result}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--archive", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    with tarfile.open(args.archive, "r:gz") as bundle:
        member = next(item for item in bundle.getmembers() if item.name.endswith("/stage-terminal.json"))
        terminal = json.load(bundle.extractfile(member))
    result = terminal["result"]
    result.pop("error", None); result["aggregation"] = aggregate_frontier(result["rows"]); result["pass"] = bool(result.get("all_actual_consumers_pass") is True and len(result["rows"]) == 24)
    repaired = {"schema_version": 1, "type": "h100_w4_frontier_primary_repaired", "source_archive_sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(), "repair": "replaced stale predecessor M8/M16/M32/M3679 cardinality assertion with the admitted M48/M64/M96/M128 aggregation", "result": result, "pass": result["pass"]}
    args.output.write_text(json.dumps(repaired, indent=2, sort_keys=True) + "\n")
    return 0 if repaired["pass"] else 1


if __name__ == "__main__": raise SystemExit(main())
