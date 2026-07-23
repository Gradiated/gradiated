#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import pathlib
import sqlite3
import statistics


TRACE_SHA256 = "c42cebd67dff6147843c678a6b7524e75c8477b79bbb5515256b1e619d63a698"
SCHEDULE_BATCH_SHA256 = "eea77dac02f593da24e953f0a0ea03237f2874d0ef27522044e8fd6397fcb874"
HOST_GATE_SHA256 = "2779aae2c51c63ef3119edff9b57e39f09576975ec6e15fb66928e6069405c2a"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=pathlib.Path, required=True)
    parser.add_argument("--attribution", type=pathlib.Path, required=True)
    parser.add_argument("--schedule-batch", type=pathlib.Path, required=True)
    parser.add_argument("--host-gate", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    identities = {
        "sqlite": sha256(args.sqlite),
        "schedule_batch": sha256(args.schedule_batch),
        "host_gate": sha256(args.host_gate),
    }
    expected = {
        "sqlite": TRACE_SHA256,
        "schedule_batch": SCHEDULE_BATCH_SHA256,
        "host_gate": HOST_GATE_SHA256,
    }
    if identities != expected:
        raise RuntimeError(f"identity_mismatch:{identities}")

    attribution = json.loads(args.attribution.read_text())
    window_start = int(attribution["window"]["start_ns"])
    window_end = int(attribution["window"]["end_ns"])
    connection = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    strings = dict(connection.execute("select id,value from StringIds"))

    covered = [
        (max(int(start), window_start), min(int(end), window_end))
        for start, end in connection.execute(
            "select start,end from CUPTI_ACTIVITY_KIND_KERNEL where end>? and start<?",
            (window_start, window_end),
        )
    ]
    for start, end, name_id in connection.execute(
        "select start,end,nameId from CUPTI_ACTIVITY_KIND_RUNTIME where end>? and start<?",
        (window_start, window_end),
    ):
        lowered = str(strings[int(name_id)]).lower()
        if (
            "synchron" in lowered
            or "streamwait" in lowered
            or "eventquery" in lowered
            or "launch" in lowered
        ):
            covered.append(
                (max(int(start), window_start), min(int(end), window_end))
            )

    merged: list[list[int]] = []
    for start, end in sorted(covered):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    gaps: list[tuple[int, int]] = []
    cursor = window_start
    for start, end in merged:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < window_end:
        gaps.append((cursor, window_end))
    gap_starts = [row[0] for row in gaps]
    gap_ends = [row[1] for row in gaps]

    def gap_overlap(start: int, end: int) -> int:
        index = max(0, bisect.bisect_right(gap_ends, start) - 1)
        total = 0
        while index < len(gaps) and gap_starts[index] < end:
            total += max(
                0,
                min(end, gap_ends[index]) - max(start, gap_starts[index]),
            )
            index += 1
        return total

    kernels = [
        (
            int(start),
            int(end),
            str(strings[int(short_name)]),
            int(grid_x),
            int(block_x),
        )
        for start, end, short_name, grid_x, block_x in connection.execute(
            """
            select start,end,shortName,gridX,blockX
            from CUPTI_ACTIVITY_KIND_KERNEL
            where streamId=13 and end>? and start<?
            order by start
            """,
            (window_start, window_end),
        )
    ]
    matched: list[int] = []
    for previous, following in zip(kernels, kernels[1:]):
        if (
            previous[2:] == ("index_elementwise_kernel", 1, 128)
            and following[2:] == ("vectorized_elementwise_kernel", 8192, 128)
            and following[0] > previous[1]
        ):
            overlap = gap_overlap(previous[1], following[0])
            if overlap:
                matched.append(overlap)

    total_gap_ns = sum(end - start for start, end in gaps)
    matched_ns = sum(matched)
    result = {
        "schema_version": 1,
        "pass": (
            len(matched) == 358
            and matched_ns > 0
            and total_gap_ns == 1_142_505_439
        ),
        "evidence_classes": {
            "gap_geometry": "measured",
            "source_chain": "source_backed",
            "python_stack_mapping": "inferred_from_exact_count_and_kernel_geometry",
            "intervention": "frozen_causal_prediction",
        },
        "identities": identities,
        "window": {
            "start_ns": window_start,
            "end_ns": window_end,
            "scheduler_gap_ns": total_gap_ns,
        },
        "largest_repeated_gap_class": {
            "count": len(matched),
            "total_ns": matched_ns,
            "fraction_of_scheduler_gap": matched_ns / total_gap_ns,
            "median_us": statistics.median(matched) / 1e3,
            "maximum_us": max(matched) / 1e3,
            "stream_id": 13,
            "predecessor": {
                "short_name": "index_elementwise_kernel",
                "grid": [1, 1, 1],
                "block": [128, 1, 1],
            },
            "consumer": {
                "short_name": "vectorized_elementwise_kernel",
                "grid": [8192, 1, 1],
                "block": [128, 1, 1],
                "operation": "float32 logits.add_(stop_token_penalties)",
                "geometry": "32 requests by Gemma vocabulary, once per decode step",
            },
        },
        "pinned_source_call_stack": [
            "Scheduler.run_batch",
            "Scheduler._forward_isolation",
            "SamplingBatchInfo.copy_for_forward",
            "SamplingBatchInfo.update_penalties",
            "BatchedPenalizerOrchestrator.accumulate_additive_penalties",
            "BatchedMinNewTokensPenalizer._apply",
            "Tensor.add_",
        ],
        "source_paths": {
            "scheduler": "/sgl-workspace/sglang/python/sglang/srt/managers/scheduler.py",
            "sampling_info": "/sgl-workspace/sglang/python/sglang/srt/sampling/sampling_batch_info.py",
            "orchestrator": "/sgl-workspace/sglang/python/sglang/srt/sampling/penaltylib/orchestrator.py",
            "retained_min_new_tokens": str(args.host_gate),
        },
        "frozen_intervention": {
            "id": "schedule_stream_forward_penalty_snapshot",
            "causal_change": "Build the forward-only sampling penalty snapshot on the schedule stream before entering forward_stream_ctx, then substitute the already-built copy inside _forward_isolation.",
            "ordering": "The existing forward_stream.wait_stream(schedule_stream) remains after production and before resolve/forward consumption.",
            "lifetime": "record_batch_in_overlap pins the substituted sampling copy and its tensors in the existing two-iteration batch ring.",
            "prediction": "The 358 index-to-dense-add gaps move under prior forward-stream CUDA work; matched interval-union time decreases without a new synchronization predecessor.",
        },
    }
    atomic(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
