#!/usr/bin/env python3
"""Summarize trace-resident L40S decode residuals without treating sums as latency."""

import argparse
import bisect
import gzip
import json
from collections import defaultdict
from pathlib import Path


def kernel_family(name: str) -> str:
    lowered = name.lower()
    if "fused_moe_kernel" in lowered:
        return "moe_fused_expert"
    if any(part in lowered for part in ("moe_align", "gathertopk", "bitonicsort", "topk")):
        return "moe_routing_sort"
    if any(part in lowered for part in ("nvjet_", "fused_a_gemm", "cublas", "gemm", "dot_kernel", "reduce_1block")):
        return "dense_gemm_gemv"
    return "other"


def union_duration(intervals: list[tuple[float, float]]) -> float:
    end = None
    total = 0.0
    for start, stop in sorted(intervals):
        if end is None:
            previous_start, end = start, stop
        elif start > end:
            total += end - previous_start
            previous_start, end = start, stop
        else:
            end = max(end, stop)
    return total if end is None else total + end - previous_start


def overlaps(interval: tuple[float, float], regions: list[tuple[float, float]]) -> bool:
    start, stop = interval
    return any(start < region_stop and region_start < stop for region_start, region_stop in regions)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with gzip.open(args.trace, "rt") as source:
        events = json.load(source)["traceEvents"]
    cpu_by_thread: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for event in events:
        if event.get("cat") == "cpu_op" and event.get("ph") == "X":
            cpu_by_thread[(event["pid"], event["tid"])].append(event)
    cpu_starts = {}
    for thread, cpu_events in cpu_by_thread.items():
        cpu_events.sort(key=lambda event: event["ts"])
        cpu_starts[thread] = [event["ts"] for event in cpu_events]
    launch_sources = {
        event["id"]: (event["pid"], event["tid"], event["ts"])
        for event in events
        if event.get("cat") == "ac2g" and event.get("ph") == "s"
    }
    decode_regions = [
        (event["ts"], event["ts"] + event["dur"])
        for event in events
        if event.get("cat") == "gpu_user_annotation"
        and event.get("ph") == "X"
        and event.get("name", "").startswith("execute_context_0(0)_generation_")
    ]
    decode_union_us = union_duration(decode_regions)
    family_intervals: dict[str, list[tuple[float, float]]] = defaultdict(list)
    exact_intervals: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    exact_resources: dict[tuple[str, str], set[tuple]] = defaultdict(set)
    exact_cpu_attribution: dict[tuple[str, str], dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    for event in events:
        if event.get("cat") != "kernel" or event.get("ph") != "X":
            continue
        interval = (event["ts"], event["ts"] + event["dur"])
        if not overlaps(interval, decode_regions):
            continue
        family = kernel_family(event["name"])
        family_intervals[family].append(interval)
        key = (family, event["name"])
        exact_intervals[key].append(interval)
        resource = event.get("args", {})
        exact_resources[key].add((
            tuple(resource.get("grid", [])), tuple(resource.get("block", [])),
            resource.get("registers per thread"), resource.get("shared memory"),
            resource.get("stream"),
        ))
        source = launch_sources.get(resource.get("correlation"))
        if source:
            thread = (source[0], source[1])
            cpu_events = cpu_by_thread.get(thread, [])
            index = bisect.bisect_right(cpu_starts.get(thread, []), source[2]) - 1
            for cpu_event in reversed(cpu_events[max(0, index - 100):index + 1]):
                if cpu_event["ts"] <= source[2] <= cpu_event["ts"] + cpu_event["dur"]:
                    dims = json.dumps(cpu_event.get("args", {}).get("Input Dims", []), separators=(",", ":"))
                    exact_cpu_attribution[key][(cpu_event["name"], dims)] += 1
                    break
    families = []
    for family, intervals in family_intervals.items():
        union_us = union_duration(intervals)
        families.append({"family": family, "trace_resident_union_ms": union_us / 1000,
                         "trace_resident_fraction": union_us / decode_union_us})
    exact = []
    for (family, name), intervals in exact_intervals.items():
        union_us = union_duration(intervals)
        signatures = sorted(exact_resources[(family, name)])
        attribution = [
            {"cpu_operation": operation, "input_dims": json.loads(dims), "launch_count": count}
            for (operation, dims), count in sorted(
                exact_cpu_attribution[(family, name)].items(), key=lambda item: item[1], reverse=True
            )[:5]
        ]
        exact.append({"family": family, "name": name, "launch_count": len(intervals),
                      "trace_resident_union_ms": union_us / 1000,
                      "trace_resident_fraction": union_us / decode_union_us,
                      "resource_signature_count": len(signatures),
                      "resource_signature_samples": [list(value) for value in signatures[:3]],
                      "cpu_launch_attribution": attribution})
    output = {
        "schema_version": 1,
        "evidence_label": "derived from measured profiler trace",
        "claim_limit": "Interval unions avoid summed-kernel double counting, but profiler decode annotations are not matched c8 serving wall time; fractions are only optimistic trace-resident ceilings.",
        "decode_annotation_union_ms": decode_union_us / 1000,
        "families": sorted(families, key=lambda item: item["trace_resident_union_ms"], reverse=True),
        "exact_operations": sorted(exact, key=lambda item: item["trace_resident_union_ms"], reverse=True)[:30],
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
