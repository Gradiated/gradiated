#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import sqlite3


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=pathlib.Path, required=True)
    parser.add_argument("--attribution", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    attribution = json.loads(args.attribution.read_text())
    decode_end = int(attribution["window"]["end_ns"])
    decode_start = int(
        decode_end - float(attribution["phases"]["decode"]["seconds"]) * 1e9
    )
    connection = sqlite3.connect(args.sqlite)
    connection.row_factory = sqlite3.Row
    strings = dict(connection.execute("select id,value from StringIds"))
    tables = {
        row[0]
        for row in connection.execute(
            "select name from sqlite_master where type='table'"
        )
    }

    runtimes = list(
        connection.execute(
            """
            select rowid,* from CUPTI_ACTIVITY_KIND_RUNTIME
            where end>? and start<?
            order by globalTid,start
            """,
            (decode_start, decode_end),
        )
    )
    runtime_by_thread: dict[int, list[sqlite3.Row]] = collections.defaultdict(list)
    for row in runtimes:
        runtime_by_thread[int(row["globalTid"])].append(row)
    runtime_aliases: dict[tuple[int, int], list[sqlite3.Row]] = collections.defaultdict(list)
    for row in runtimes:
        runtime_aliases[
            (int(row["globalTid"]), int(row["correlationId"]))
        ].append(row)

    copies = {
        int(row["correlationId"]): row
        for row in connection.execute(
            """
            select rowid,* from CUPTI_ACTIVITY_KIND_MEMCPY
            where end>? and start<?
            """,
            (decode_start, decode_end),
        )
    }
    kernels = list(
        connection.execute(
            """
            select rowid,* from CUPTI_ACTIVITY_KIND_KERNEL
            where end>? and start<?
            order by start
            """,
            (decode_start, decode_end),
        )
    )
    kernels_by_stream: dict[int, list[sqlite3.Row]] = collections.defaultdict(list)
    for row in kernels:
        kernels_by_stream[int(row["streamId"])].append(row)

    thread_names: dict[int, str] = {}
    if "ThreadNames" in tables:
        for row in connection.execute("select globalTid,nameId from ThreadNames"):
            thread_names[int(row["globalTid"])] = strings.get(
                int(row["nameId"]), str(row["nameId"])
            )

    occurrences: list[dict[str, object]] = []
    all_long_sync_seconds = 0.0
    all_long_sync_count = 0
    for global_tid, rows in runtime_by_thread.items():
        for index, row in enumerate(rows):
            name = strings.get(int(row["nameId"]), str(row["nameId"]))
            duration_ns = int(row["end"]) - int(row["start"])
            if name == "cudaStreamSynchronize_v3020" and duration_ns >= 10_000_000:
                all_long_sync_count += 1
                all_long_sync_seconds += duration_ns / 1e9
                # Nsight emits an instrumentation/base-name row immediately
                # before its versioned CUPTI runtime row with the *same*
                # correlation id when CUDA/Python backtraces are enabled.  That
                # alias must not hide the preceding distinct API operation.
                previous = next(
                    (
                        candidate
                        for candidate in reversed(rows[:index])
                        if int(candidate["correlationId"])
                        != int(row["correlationId"])
                    ),
                    None,
                )
                copy = (
                    copies.get(int(previous["correlationId"]))
                    if previous is not None
                    else None
                )
                if (
                    previous is not None
                    and copy is not None
                    and int(copy["copyKind"]) == 1
                    and int(copy["bytes"]) in {8, 16}
                ):
                    copy_aliases = runtime_aliases[
                        (global_tid, int(previous["correlationId"]))
                    ]
                    copy_callchain = next(
                        (
                            alias["callchainId"]
                            for alias in copy_aliases
                            if alias["callchainId"] is not None
                        ),
                        previous["callchainId"],
                    )
                    copy_api_names = sorted(
                        {
                            strings.get(int(alias["nameId"]), str(alias["nameId"]))
                            for alias in copy_aliases
                        }
                    )
                    sync_aliases = runtime_aliases[
                        (global_tid, int(row["correlationId"]))
                    ]
                    sync_callchain = next(
                        (
                            alias["callchainId"]
                            for alias in sync_aliases
                            if alias["callchainId"] is not None
                        ),
                        row["callchainId"],
                    )
                    stream = int(copy["streamId"])
                    next_kernel = next(
                        (
                            candidate
                            for candidate in kernels_by_stream[stream]
                            if int(candidate["start"]) >= int(copy["end"])
                        ),
                        None,
                    )
                    prior_kernel = next(
                        (
                            candidate
                            for candidate in reversed(kernels_by_stream[stream])
                            if int(candidate["end"]) <= int(copy["start"])
                        ),
                        None,
                    )
                    occurrences.append(
                        {
                            "bytes": int(copy["bytes"]),
                            "copy_kind": int(copy["copyKind"]),
                            "src_kind": int(copy["srcKind"]),
                            "dst_kind": int(copy["dstKind"]),
                            "runtime_api": strings.get(
                                int(previous["nameId"]), str(previous["nameId"])
                            ),
                            "runtime_api_aliases": copy_api_names,
                            "runtime_correlation_id": int(previous["correlationId"]),
                            "runtime_callchain_id": copy_callchain,
                            "sync_runtime_api_aliases": sorted(
                                {
                                    strings.get(
                                        int(alias["nameId"]), str(alias["nameId"])
                                    )
                                    for alias in sync_aliases
                                }
                            ),
                            "sync_runtime_correlation_id": int(row["correlationId"]),
                            "sync_runtime_callchain_id": sync_callchain,
                            "global_tid": global_tid,
                            "thread_name": thread_names.get(global_tid),
                            "stream_id": stream,
                            "copy_start_ns": int(copy["start"]),
                            "copy_end_ns": int(copy["end"]),
                            "sync_start_ns": int(row["start"]),
                            "sync_duration_seconds": duration_ns / 1e9,
                            "phase": "decode",
                            "prior_same_stream_kernel": None
                            if prior_kernel is None
                            else {
                                "name": strings.get(
                                    int(prior_kernel["shortName"]),
                                    str(prior_kernel["shortName"]),
                                ),
                                "correlation_id": int(prior_kernel["correlationId"]),
                                "gap_ns": int(copy["start"]) - int(prior_kernel["end"]),
                            },
                            "immediate_same_stream_gpu_consumer": None
                            if next_kernel is None
                            else {
                                "name": strings.get(
                                    int(next_kernel["shortName"]),
                                    str(next_kernel["shortName"]),
                                ),
                                "correlation_id": int(next_kernel["correlationId"]),
                                "gap_ns": int(next_kernel["start"]) - int(copy["end"]),
                            },
                        }
                    )

    grouped = collections.Counter(
        (
            row["bytes"],
            row["global_tid"],
            row["stream_id"],
            None
            if row["immediate_same_stream_gpu_consumer"] is None
            else row["immediate_same_stream_gpu_consumer"]["name"],
            tuple(row["runtime_api_aliases"]),
        )
        for row in occurrences
    )
    groups = [
        {
            "bytes": key[0],
            "global_tid": key[1],
            "stream_id": key[2],
            "immediate_same_stream_gpu_consumer": key[3],
            "runtime_api_aliases": list(key[4]),
            "runtime_callchain_ids": sorted(
                {
                    row["runtime_callchain_id"]
                    for row in occurrences
                    if row["bytes"] == key[0]
                    and row["global_tid"] == key[1]
                    and row["stream_id"] == key[2]
                    and (
                        None
                        if row["immediate_same_stream_gpu_consumer"] is None
                        else row["immediate_same_stream_gpu_consumer"]["name"]
                    )
                    == key[3]
                    and tuple(row["runtime_api_aliases"]) == key[4]
                }
            ),
            "count": count,
        }
        for key, count in grouped.most_common()
    ]

    stack_tables = {}
    for table in sorted(tables):
        if not any(token in table.upper() for token in ("BACKTRACE", "CALLCHAIN")):
            continue
        columns = [
            row[1] for row in connection.execute(f'pragma table_info("{table}")')
        ]
        stack_tables[table] = {"columns": columns, "row_count": connection.execute(
            f'select count(*) from "{table}"'
        ).fetchone()[0]}

    recurring = len(occurrences) >= 4 and any(
        group["count"] >= 4 for group in groups
    )
    result = {
        "schema_version": 1,
        "status": "source_review_required" if recurring else "terminal",
        "classification": (
            "repeated_current_stack_small_h2d_survives"
            if recurring
            else "no_repeated_current_stack_small_h2d_predecessor"
        ),
        "pass": True,
        "evidence_class": "measured_current_frontier_nsight_trace",
        "trace": {
            "path": str(args.sqlite),
            "sha256": sha256(args.sqlite),
            "decode_start_ns": decode_start,
            "decode_end_ns": decode_end,
        },
        "current_stack_path_proof_required": [
            "dynamic_fp8",
            "qkv_epilogue",
            "deferred_local_fp8_kv",
            "pinned_async_penalty_tokens",
            "host_required_dense_add",
            "producer_fused_swa_mapping",
        ],
        "measured": {
            "long_sync_count": all_long_sync_count,
            "long_sync_seconds": all_long_sync_seconds,
            "small_h2d_long_sync_predecessor_count": len(occurrences),
            "groups": groups,
            "occurrences": occurrences,
        },
        "stack_schema": stack_tables,
        "surviving_repeated_small_h2d": recurring,
        "independently_removable": None if recurring else False,
        "decision_note": (
            "Bind the captured CUDA/Python callchain to exact source and semantics before admitting one intervention."
            if recurring
            else "The prior 8-byte/16-byte signature does not survive as a repeated long-sync predecessor on the current producer-fused stack."
        ),
    }
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
