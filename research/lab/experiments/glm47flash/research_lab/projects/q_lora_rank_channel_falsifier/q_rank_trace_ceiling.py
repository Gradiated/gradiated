#!/usr/bin/env python3
"""Derive the optimistic q-rank endpoint ceiling from the retained profiler trace."""

from __future__ import annotations

import gzip
import hashlib
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent.parent.parent / "campaign_100" / "allocations" / "nebius_l40s_vllm_awq_splits_ab_v25r1" / "vllm-awq-batch.tar.gz"
TRACE_TOTAL_MS = 3630.826889770508
CONTROL_TOK_S = 602.157121
LAYER_COUNT = 47
RANKS = (640, 512)


def union_us(intervals: list[tuple[float, float]]) -> float:
    start = None
    end = None
    total = 0.0
    for next_start, stop in sorted(intervals):
        if end is None:
            start = next_start
            end = stop
        elif next_start > end:
            total += end - start
            start, end = next_start, stop
        else:
            end = max(end, stop)
    return total + (end - start) if end is not None else 0.0


def main() -> None:
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        trace_name = next(name for name in archive.getnames() if name.endswith(".pt.trace.json.gz"))
        with gzip.GzipFile(fileobj=archive.extractfile(trace_name)) as trace_file:
            events = json.load(trace_file)["traceEvents"]

    operations = {
        "q_a_fused_with_kv_a": ("[[8192, 2048], [2048, 1344]", 121, 1344),
        "q_a_to_norm_bridge": ("[[8192, 1344], [8192]", 122, 1344),
        "q_rmsnorm_and_split": ("[[8192, 1344], [768], [512]", 123, 768),
        "q_b": ("[[8192, 768], [768, 5120]", 124, 768),
    }
    bindings = {}
    for name, (shape_prefix, external_id, width) in operations.items():
        cpu = next(
            event
            for event in events
            if event.get("cat") == "cpu_op"
            and event.get("args", {}).get("External id") == external_id
            and str(event.get("args", {}).get("Input Dims", "")).startswith(shape_prefix)
        )
        kernels = [
            event
            for event in events
            if event.get("cat") == "kernel"
            and event.get("args", {}).get("External id") == external_id
        ]
        intervals = [(event["ts"], event["ts"] + event["dur"]) for event in kernels]
        bindings[name] = {
            "external_id": external_id,
            "cpu_input_dims": cpu["args"]["Input Dims"],
            "kernel_names": [event["name"] for event in kernels],
            "kernel_interval_union_us": union_us(intervals),
            "reduced_channel_width": width,
        }

    rows = []
    for rank in RANKS:
        saved_us_per_layer = sum(
            binding["kernel_interval_union_us"] * (768 - rank) / binding["reduced_channel_width"]
            for binding in bindings.values()
        )
        endpoint_reduction = (saved_us_per_layer * LAYER_COUNT) / (TRACE_TOTAL_MS * 1000.0)
        rows.append(
            {
                "rank": rank,
                "optimistic_saved_trace_us_per_layer": saved_us_per_layer,
                "optimistic_saved_trace_us_47_layers": saved_us_per_layer * LAYER_COUNT,
                "impossible_endpoint_reduction_ceiling": endpoint_reduction,
                "optimistic_endpoint_tok_s": CONTROL_TOK_S / (1.0 - endpoint_reduction),
            }
        )
    result = {
        "schema_version": 1,
        "decision": "Q_RANK_CLOSE",
        "reason": "Even a 47-layer, no-overlap, no-overhead transfer of the retained profiler intervals is below the required 3.5% endpoint reduction.",
        "evidence_label": "derived from measured retained profiler trace; source-bound operation shapes",
        "archive": str(ARCHIVE),
        "archive_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
        "trace_member": trace_name,
        "trace_decode_annotation_union_ms": TRACE_TOTAL_MS,
        "control_tok_s": CONTROL_TOK_S,
        "required_impossible_endpoint_reduction": 0.035,
        "topology": "q-a (fused with KV-a) -> q-RMSNorm -> q-b; no overlapping intervals summed",
        "bindings": bindings,
        "rows": rows,
        "stop_rule": "No payload reconstruction, checkpoint/runtime mutation, CUDA, provider, or endpoint preparation after trace close.",
    }
    output = ROOT / "artifacts" / "Q_RANK_TRACE_CEILING_2026-07-16.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
