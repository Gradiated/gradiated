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
    parser.add_argument("--schedule-source", type=pathlib.Path, required=True)
    parser.add_argument("--intervention", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    if sha256(args.schedule_source) != "eea77dac02f593da24e953f0a0ea03237f2874d0ef27522044e8fd6397fcb874":
        raise RuntimeError("schedule_source_identity_mismatch")
    attribution = json.loads(args.attribution.read_text())
    decode_end = int(attribution["window"]["end_ns"])
    decode_start = int(decode_end - attribution["phases"]["decode"]["seconds"] * 1e9)

    connection = sqlite3.connect(args.sqlite)
    strings = dict(connection.execute("select id,value from StringIds"))
    rows = connection.execute(
        """
        select start,end,nameId,correlationId
        from CUPTI_ACTIVITY_KIND_RUNTIME
        where end>? and start<?
        order by start
        """,
        (decode_start, decode_end),
    ).fetchall()
    copies = {
        int(correlation): {
            "bytes": int(num_bytes),
            "copy_kind": int(copy_kind),
            "src_kind": int(src_kind),
            "dst_kind": int(dst_kind),
        }
        for correlation, num_bytes, copy_kind, src_kind, dst_kind in connection.execute(
            """
            select correlationId,bytes,copyKind,srcKind,dstKind
            from CUPTI_ACTIVITY_KIND_MEMCPY
            where end>? and start<?
            """,
            (decode_start, decode_end),
        )
    }

    predecessors = collections.Counter()
    long_sync_seconds = 0.0
    previous = None
    for start, end, name_id, correlation in rows:
        name = strings.get(name_id, str(name_id))
        if name == "cudaStreamSynchronize_v3020" and end - start >= 10_000_000:
            prior_name = "missing"
            prior_copy = None
            if previous is not None:
                prior_name = strings.get(previous[2], str(previous[2]))
                prior_copy = copies.get(int(previous[3]))
            predecessors[
                (
                    prior_name,
                    None if prior_copy is None else prior_copy["bytes"],
                    None if prior_copy is None else prior_copy["copy_kind"],
                )
            ] += 1
            long_sync_seconds += (end - start) / 1e9
        previous = (start, end, name_id, correlation)

    four_byte_d2h = predecessors[("cudaMemcpyAsync_v3020", 4, 2)]
    any_d2h = sum(
        count for (_, _, copy_kind), count in predecessors.items() if copy_kind == 2
    )
    long_syncs = sum(predecessors.values())
    result = {
        "schema_version": 1,
        "pass": four_byte_d2h == 0 and any_d2h == 0,
        "evidence_class": "measured_candidate_nsight_trace",
        "trace": {
            "sha256": sha256(args.sqlite),
            "decode_start_ns": decode_start,
            "decode_end_ns": decode_end,
        },
        "bound_source": {
            "schedule_batch_sha256": sha256(args.schedule_source),
            "intervention_sha256": sha256(args.intervention),
        },
        "prediction": {
            "four_byte_d2h_long_sync_predecessors": {"retained_control": 358, "candidate": 0},
            "replacement_d2h_scalar_predecessors": 0,
        },
        "measured": {
            "long_sync_count": long_syncs,
            "long_sync_seconds": long_sync_seconds,
            "four_byte_d2h_long_sync_predecessors": four_byte_d2h,
            "all_d2h_long_sync_predecessors": any_d2h,
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
    }
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
