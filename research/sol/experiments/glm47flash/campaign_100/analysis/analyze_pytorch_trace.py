#!/usr/bin/env python3

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path


def kernel_family(name: str) -> str:
    lowered = name.lower()
    if "fused_moe_kernel" in lowered:
        return "moe_fused_expert"
    if any(part in lowered for part in ("moe_align", "gathertopk", "bitonicsort", "topk")):
        return "moe_routing_sort"
    if any(
        part in lowered
        for part in ("nvjet_", "fused_a_gemm", "cublas", "gemm", "dot_kernel", "reduce_1block")
    ):
        return "dense_gemm_gemv"
    if any(part in lowered for part in ("flashattn", "flash::", "mla", "set_mla")):
        return "attention_mla"
    if any(part in lowered for part in ("rmsnorm", "rope", "act_and_mul")):
        return "norm_rope_activation"
    if "copy" in lowered:
        return "copy_cast"
    return "other"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[int(fraction * (len(ordered) - 1))]


def region_summary(events: list[dict], prefix: str) -> dict:
    annotations = [
        event
        for event in events
        if event.get("cat") == "gpu_user_annotation"
        and event.get("ph") == "X"
        and event.get("name", "").startswith(prefix)
    ]
    kernels = [event for event in events if event.get("cat") == "kernel" and event.get("ph") == "X"]
    selected = []
    for kernel in kernels:
        midpoint = kernel["ts"] + kernel["dur"] / 2
        if any(annotation["ts"] <= midpoint <= annotation["ts"] + annotation["dur"] for annotation in annotations):
            selected.append(kernel)

    family_duration_us = Counter()
    family_count = Counter()
    exact_duration_us = Counter()
    for kernel in selected:
        family = kernel_family(kernel["name"])
        family_duration_us[family] += kernel["dur"]
        family_count[family] += 1
        exact_duration_us[kernel["name"]] += kernel["dur"]

    total_us = sum(family_duration_us.values())
    durations_ms = [annotation["dur"] / 1000 for annotation in annotations]
    return {
        "region_count": len(annotations),
        "region_duration_sum_ms": sum(durations_ms),
        "region_duration_p50_ms": percentile(durations_ms, 0.50),
        "region_duration_p95_ms": percentile(durations_ms, 0.95),
        "region_duration_max_ms": max(durations_ms),
        "kernel_count": len(selected),
        "kernel_duration_sum_ms": total_us / 1000,
        "kernel_families": [
            {
                "family": family,
                "kernel_count": family_count[family],
                "duration_ms": duration_us / 1000,
                "share_of_kernel_duration": duration_us / total_us,
            }
            for family, duration_us in family_duration_us.most_common()
        ],
        "top_exact_kernels": [
            {
                "name": name,
                "duration_ms": duration_us / 1000,
                "share_of_kernel_duration": duration_us / total_us,
            }
            for name, duration_us in exact_duration_us.most_common(20)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--source-artifact", required=True)
    parser.add_argument("--source-artifact-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with gzip.open(args.trace, "rt") as trace_file:
        events = json.load(trace_file)["traceEvents"]

    output = {
        "schema_version": 1,
        "evidence_label": "measured profiler trace",
        "source_artifact": args.source_artifact,
        "source_artifact_sha256": args.source_artifact_sha256,
        "trace_file": args.trace.name,
        "method": (
            "Kernel events are assigned to GPU user-annotation regions when their midpoint falls inside the region. "
            "Durations are summed and therefore are component-time attribution, not an additive latency model when streams overlap."
        ),
        "decode": region_summary(events, "step[DECODE"),
        "prefill": region_summary(events, "step[EXTEND"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
