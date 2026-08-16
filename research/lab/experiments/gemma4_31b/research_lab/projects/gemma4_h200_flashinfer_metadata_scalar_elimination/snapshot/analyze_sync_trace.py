#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import sqlite3
import statistics


PINNED_SOURCE_SHA256 = (
    "eea77dac02f593da24e953f0a0ea03237f2874d0ef27522044e8fd6397fcb874"
)
CALLSITE_NEEDLE = "latest_output_ids = torch.tensor("


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
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--expected-matched", type=int, default=358)
    args = parser.parse_args()

    source_hash = sha256(args.source)
    if source_hash != PINNED_SOURCE_SHA256:
        raise RuntimeError(f"pinned_source_identity_mismatch:{source_hash}")
    source_lines = args.source.read_text().splitlines()
    callsite_lines = [
        index + 1
        for index, line in enumerate(source_lines)
        if CALLSITE_NEEDLE in line
    ]
    if len(callsite_lines) != 1:
        raise RuntimeError(f"callsite_not_unique:{callsite_lines}")

    attribution = json.loads(args.attribution.read_text())
    window = attribution["window"]
    decode_seconds = attribution["phases"]["decode"]["seconds"]
    decode_start = int(window["end_ns"] - decode_seconds * 1e9)
    decode_end = int(window["end_ns"])

    connection = sqlite3.connect(args.sqlite)
    strings = dict(connection.execute("select id,value from StringIds"))
    runtime_rows = connection.execute(
        """
        select start,end,nameId,correlationId
        from CUPTI_ACTIVITY_KIND_RUNTIME
        where end>? and start<?
        order by start
        """,
        (decode_start, decode_end),
    ).fetchall()
    copies = {
        int(correlation_id): {
            "bytes": int(num_bytes),
            "copy_kind": int(copy_kind),
            "src_kind": int(src_kind),
            "dst_kind": int(dst_kind),
        }
        for correlation_id, num_bytes, copy_kind, src_kind, dst_kind in connection.execute(
            """
            select correlationId,bytes,copyKind,srcKind,dstKind
            from CUPTI_ACTIVITY_KIND_MEMCPY
            where end>? and start<?
            """,
            (decode_start, decode_end),
        )
    }

    long_syncs = []
    predecessors: collections.Counter[tuple[str, int | None, int | None]] = (
        collections.Counter()
    )
    previous = None
    for start, end, name_id, correlation_id in runtime_rows:
        name = str(strings.get(name_id, name_id))
        duration = int(end) - int(start)
        if name == "cudaStreamSynchronize_v3020" and duration >= 10_000_000:
            predecessor_name = None
            predecessor_copy = None
            gap_ns = None
            if previous is not None:
                predecessor_name = str(strings.get(previous[2], previous[2]))
                predecessor_copy = copies.get(int(previous[3]))
                gap_ns = int(start) - int(previous[1])
            predecessors[
                (
                    predecessor_name or "missing",
                    None if predecessor_copy is None else predecessor_copy["bytes"],
                    None
                    if predecessor_copy is None
                    else predecessor_copy["copy_kind"],
                )
            ] += 1
            long_syncs.append(
                {
                    "duration_ns": duration,
                    "gap_from_predecessor_ns": gap_ns,
                    "predecessor": predecessor_name,
                    "predecessor_copy": predecessor_copy,
                }
            )
        previous = (start, end, name_id, correlation_id)

    matched = [
        row
        for row in long_syncs
        if row["predecessor"] == "cudaMemcpyAsync_v3020"
        and row["predecessor_copy"] == {
            "bytes": 256,
            "copy_kind": 1,
            "src_kind": 0,
            "dst_kind": 2,
        }
    ]
    matched_seconds = sum(row["duration_ns"] for row in matched) / 1e9
    all_long_seconds = sum(row["duration_ns"] for row in long_syncs) / 1e9
    gaps = [
        row["gap_from_predecessor_ns"]
        for row in matched
        if row["gap_from_predecessor_ns"] is not None
    ]
    result = {
        "schema_version": 1,
        "evidence_classes": {
            "nsight_runtime_and_memcpy_rows": "measured",
            "pinned_source_identity_and_unique_callsite": "source_backed",
            "callsite_mapping": "inferred_from_exact_count_geometry_and_api_adjacency",
            "candidate_counter_prediction": "causal_prediction",
        },
        "trace": {
            "path": str(args.sqlite),
            "sha256": sha256(args.sqlite),
            "decode_start_ns": decode_start,
            "decode_end_ns": decode_end,
            "decode_seconds": (decode_end - decode_start) / 1e9,
        },
        "dominant_mechanism": {
            "api": "cudaStreamSynchronize_v3020",
            "long_threshold_ms": 10,
            "long_calls": len(long_syncs),
            "long_seconds": all_long_seconds,
            "matched_32x_int64_h2d_calls": len(matched),
            "matched_32x_int64_h2d_seconds": matched_seconds,
            "matched_fraction_of_long_calls": (
                len(matched) / len(long_syncs) if long_syncs else 0.0
            ),
            "predecessor_gap_median_us": (
                statistics.median(gaps) / 1e3 if gaps else None
            ),
            "predecessor_groups": [
                {
                    "runtime_api": key[0],
                    "bytes": key[1],
                    "copy_kind": key[2],
                    "count": count,
                }
                for key, count in predecessors.most_common()
            ],
        },
        "source_callsite": {
            "path": str(args.source),
            "sha256": source_hash,
            "line": callsite_lines[0],
            "symbol": "ScheduleBatch.prepare_for_decode",
            "operation": "torch.tensor(latest_output_ids, dtype=int64, device=self.device)",
            "workload_trigger": "min_tokens=358 activates BatchedMinNewTokensPenalizer",
            "geometry": "32 requests * 8-byte int64 = 256 bytes",
        },
        "causal_patch": {
            "id": "pinned_async_penalty_token_h2d",
            "change": "materialize latest token ids in pinned host memory and enqueue non_blocking H2D on the schedule stream",
            "semantics": "the existing forward_stream.wait_stream(schedule_stream) orders penalizer accumulation before model forward",
            "predicted_counter_change": {
                "matched_long_cudaStreamSynchronize_calls": {"control": 358, "candidate": 0},
                "matched_256_byte_h2d_calls": {"control": 358, "candidate": 358},
                "candidate_path_runtime_records_minimum": 1,
            },
            "falsifier": "candidate retains long stream synchronizations immediately after 256-byte H2D copies or violates exact output/accounting gates",
        },
        "expected_matched_long_sync_calls": args.expected_matched,
        "pass": (
            len(matched) == args.expected_matched
            and source_hash == PINNED_SOURCE_SHA256
        ),
    }
    atomic(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
