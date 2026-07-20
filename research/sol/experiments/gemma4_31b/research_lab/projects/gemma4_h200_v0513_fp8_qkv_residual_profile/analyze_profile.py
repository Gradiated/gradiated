#!/usr/bin/env python3
from __future__ import annotations

import argparse
import heapq
import json
import pathlib
import sqlite3
import statistics


KERNEL_PATTERNS = (
    ("qkv_norm_rope", ("qkv_norm_rope", "rotary", "rope")),
    ("attention_kv", ("_fwd_kernel", "attention", "paged", "flash", "extend", "decode", "kv_cache", "kvcache")),
    ("fp8_linear", ("device_kernel", "per_token_quant_fp8", "gemm", "cutlass", "scaled_mm", "matmul", "cublas")),
    ("normalization_activation", ("norm", "silu", "gelu", "activation", "act_and_mul")),
    ("cache_conversion_write", ("cache", "cast", "convert", "copy")),
)


def kernel_family(name: str) -> str:
    lowered = name.lower()
    for family, patterns in KERNEL_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            return family
    return "other_gpu"


def column(columns: set[str], *names: str) -> str | None:
    return next((name for name in names if name in columns), None)


def load_strings(connection: sqlite3.Connection) -> dict[int, str]:
    tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}
    if "StringIds" not in tables:
        return {}
    return {int(row[0]): str(row[1]) for row in connection.execute("select id,value from StringIds")}


def intervals(
    connection: sqlite3.Connection,
    table: str,
    strings: dict[int, str],
) -> list[tuple[int, int, str]]:
    columns = {row[1] for row in connection.execute(f'pragma table_info("{table}")')}
    start = column(columns, "start", "startNs", "timestamp")
    end = column(columns, "end", "endNs")
    name = column(columns, "shortName", "demangledName", "name", "nameId")
    if not start or not end or not name:
        raise RuntimeError(f"unsupported_nsys_table_schema:{table}:{sorted(columns)}")
    rows = []
    for raw_start, raw_end, raw_name in connection.execute(
        f'select "{start}","{end}","{name}" from "{table}" where "{end}">"{start}"'
    ):
        resolved = strings.get(int(raw_name), str(raw_name)) if isinstance(raw_name, int) else str(raw_name)
        rows.append((int(raw_start), int(raw_end), resolved))
    return rows


def choose_window(kernels: list[tuple[int, int, str]], terminal: dict) -> tuple[int, int, str]:
    starts = [row["started_monotonic_s"] for row in terminal["rows"]]
    ends = [row["ended_monotonic_s"] for row in terminal["rows"]]
    requested = (int(min(starts) * 1e9), int(max(ends) * 1e9))
    trace = (min(row[0] for row in kernels), max(row[1] for row in kernels))
    overlap = min(requested[1], trace[1]) - max(requested[0], trace[0])
    if overlap > 0:
        return requested[0], requested[1], "terminal_monotonic"
    return trace[0], trace[1], "cuda_profiler_capture_range"


def clip(rows: list[tuple[int, int, str]], start: int, end: int) -> list[tuple[int, int, str]]:
    return [(max(a, start), min(b, end), name) for a, b, name in rows if b > start and a < end]


def attribution(
    kernels: list[tuple[int, int, str]],
    runtime: list[tuple[int, int, str]],
    start: int,
    end: int,
) -> tuple[dict[str, int], int]:
    kernels = clip(kernels, start, end)
    runtime = clip(runtime, start, end)
    # Sweep interval endpoints once.  The former implementation rescanned every
    # kernel and runtime row at every boundary, which is quadratic and cannot
    # consume a real endpoint trace containing hundreds of thousands of rows.
    # Ranking kernels up front preserves the original deterministic selection:
    # longest active duration first, then lexicographically greatest name.
    kernel_rank = {
        row_id: rank
        for rank, row_id in enumerate(
            sorted(
                range(len(kernels)),
                key=lambda index: (kernels[index][1] - kernels[index][0], kernels[index][2]),
                reverse=True,
            )
        )
    }
    events: dict[int, list[tuple[str, int]]] = {start: [], end: []}
    for row_id, (a, b, _) in enumerate(kernels):
        events.setdefault(a, []).append(("kernel_add", row_id))
        events.setdefault(b, []).append(("kernel_remove", row_id))
    runtime_kind: list[str] = []
    for row_id, (a, b, name) in enumerate(runtime):
        lowered = name.lower()
        kind = (
            "synchronization"
            if "synchron" in lowered or "streamwait" in lowered or "eventquery" in lowered
            else "launch"
            if "launch" in lowered
            else "other"
        )
        runtime_kind.append(kind)
        events.setdefault(a, []).append(("runtime_add", row_id))
        events.setdefault(b, []).append(("runtime_remove", row_id))

    totals: dict[str, int] = {}
    overlap_ns = 0
    active_kernels: set[int] = set()
    active_heap: list[tuple[int, int]] = []
    active_family_counts: dict[str, int] = {}
    active_runtime_counts = {"synchronization": 0, "launch": 0, "other": 0}
    previous = start
    for boundary in sorted(events):
        if boundary > previous:
            width = boundary - previous
            while active_heap and active_heap[0][1] not in active_kernels:
                heapq.heappop(active_heap)
            if active_heap:
                if len(active_family_counts) > 1:
                    overlap_ns += width
                family = kernel_family(kernels[active_heap[0][1]][2])
            elif active_runtime_counts["synchronization"]:
                family = "synchronization"
            elif active_runtime_counts["launch"]:
                family = "launch"
            else:
                family = "scheduler_gap"
            totals[family] = totals.get(family, 0) + width
        # Ends precede starts at the same timestamp, matching half-open [a,b)
        # overlap semantics in the original implementation.
        ordered_events = sorted(events[boundary], key=lambda item: item[0].endswith("add"))
        for action, row_id in ordered_events:
            if action == "kernel_remove":
                if row_id in active_kernels:
                    active_kernels.remove(row_id)
                    family = kernel_family(kernels[row_id][2])
                    active_family_counts[family] -= 1
                    if active_family_counts[family] == 0:
                        del active_family_counts[family]
            elif action == "kernel_add":
                active_kernels.add(row_id)
                heapq.heappush(active_heap, (kernel_rank[row_id], row_id))
                family = kernel_family(kernels[row_id][2])
                active_family_counts[family] = active_family_counts.get(family, 0) + 1
            elif action == "runtime_remove":
                active_runtime_counts[runtime_kind[row_id]] -= 1
            else:
                active_runtime_counts[runtime_kind[row_id]] += 1
        previous = boundary
    return totals, overlap_ns


def rows_from_totals(totals: dict[str, int], wall_ns: int) -> list[dict[str, object]]:
    if wall_ns <= 0:
        return []
    return [
        {
            "boundary": name,
            "seconds": nanoseconds / 1e9,
            "wall_fraction": nanoseconds / wall_ns,
        }
        for name, nanoseconds in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=pathlib.Path, required=True)
    parser.add_argument("--terminal", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    terminal = json.loads(args.terminal.read_text())
    if terminal.get("pass") is not True or terminal.get("complete_requests") != 32:
        raise RuntimeError("profile_control_terminal_invalid")
    connection = sqlite3.connect(args.sqlite)
    tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}
    strings = load_strings(connection)
    kernel_table = next((name for name in ("CUPTI_ACTIVITY_KIND_KERNEL", "CUDA_GPU_KERNEL") if name in tables), None)
    if not kernel_table:
        raise RuntimeError(f"nsys_kernel_table_missing:{sorted(tables)}")
    runtime_table = next((name for name in ("CUPTI_ACTIVITY_KIND_RUNTIME", "CUDA_API") if name in tables), None)
    kernels = intervals(connection, kernel_table, strings)
    runtime = intervals(connection, runtime_table, strings) if runtime_table else []
    if not kernels:
        raise RuntimeError("nsys_kernel_rows_missing")
    start, end, window_source = choose_window(kernels, terminal)
    totals, overlap_ns = attribution(kernels, runtime, start, end)
    wall_ns = end - start
    rows = rows_from_totals(totals, wall_ns)
    terminal_start = min(row["started_monotonic_s"] for row in terminal["rows"])
    terminal_end = max(row["ended_monotonic_s"] for row in terminal["rows"])
    first_tokens = [row["first_token_monotonic_s"] for row in terminal["rows"] if row["first_token_monotonic_s"] is not None]
    ttft_fraction = (
        (statistics.median(first_tokens) - terminal_start) / (terminal_end - terminal_start)
        if first_tokens and terminal_end > terminal_start
        else 0.5
    )
    phase_split = start + int(max(0.0, min(1.0, ttft_fraction)) * wall_ns)
    prefill_totals, _ = attribution(kernels, runtime, start, phase_split)
    decode_totals, _ = attribution(kernels, runtime, phase_split, end)
    eligible = [row for row in rows if row["boundary"] not in {"scheduler_gap", "other_gpu"} and row["wall_fraction"] >= 0.05]
    output = {
        "schema_version": 1,
        "pass": sum(totals.values()) == wall_ns,
        "evidence_class": "measured",
        "profile_control_service_seconds_per_request": terminal["service_seconds_per_request"],
        "window": {"start_ns": start, "end_ns": end, "seconds": wall_ns / 1e9, "source": window_source},
        "attribution_rule": "Every wall interval is assigned once. Concurrent GPU intervals use the longest active kernel; idle intervals use active CUDA synchronization/launch APIs, then scheduler_gap.",
        "cross_family_gpu_overlap_seconds": overlap_ns / 1e9,
        "boundaries": rows,
        "phases": {
            "split_rule": "Non-overlapping median-TTFT proxy: prefill ends at the median first-token timestamp; the remainder is decode.",
            "prefill": {
                "seconds": (phase_split - start) / 1e9,
                "boundaries": rows_from_totals(prefill_totals, phase_split - start),
            },
            "decode": {
                "seconds": (end - phase_split) / 1e9,
                "boundaries": rows_from_totals(decode_totals, end - phase_split),
            },
        },
        "hottest_eligible_boundary": eligible[0] if eligible else None,
        "kernel_rows": len(kernels),
        "runtime_rows": len(runtime),
    }
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
