#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sqlite3
import statistics


PINNED_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
EXTEND_SOURCE_SHA256 = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"
BACKEND_SOURCE_SHA256 = "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=pathlib.Path, required=True)
    parser.add_argument("--terminal", type=pathlib.Path, required=True)
    parser.add_argument("--attribution", type=pathlib.Path, required=True)
    parser.add_argument("--source-root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    extend = args.source_root / "python/sglang/srt/layers/attention/triton_ops/extend_attention.py"
    backend = args.source_root / "python/sglang/srt/layers/attention/triton_backend.py"
    if sha256(extend) != EXTEND_SOURCE_SHA256 or sha256(backend) != BACKEND_SOURCE_SHA256:
        raise RuntimeError("pinned_attention_source_mismatch")

    terminal = json.loads(args.terminal.read_text())
    attribution = json.loads(args.attribution.read_text())
    window = attribution["window"]
    terminal_start = min(row["started_monotonic_s"] for row in terminal["rows"])
    terminal_end = max(row["ended_monotonic_s"] for row in terminal["rows"])
    first_token = statistics.median(row["first_token_monotonic_s"] for row in terminal["rows"])
    split = window["start_ns"] + int(
        (first_token - terminal_start)
        / (terminal_end - terminal_start)
        * (window["end_ns"] - window["start_ns"])
    )

    connection = sqlite3.connect(args.sqlite)
    rows = connection.execute(
        """
        SELECT k.start, k.end, k.gridX, k.gridY, k.gridZ,
               k.dynamicSharedMemory, k.registersPerThread
        FROM CUPTI_ACTIVITY_KIND_KERNEL k
        JOIN StringIds s ON s.id = k.shortName
        WHERE s.value = '_fwd_kernel'
        """
    ).fetchall()
    subtypes = []
    for shared_memory, name, shape, layer_count in (
        (81920, "local_sliding_extend", {"qk_head_dim": 256, "v_head_dim": 256, "q_heads": 32, "kv_heads": 16, "window": 1024, "block_m": 64, "block_n": 64}, 50),
        (102400, "global_extend", {"qk_head_dim": 512, "v_head_dim": 512, "q_heads": 32, "kv_heads": 4, "window": None, "block_m": 32, "block_n": 64}, 10),
    ):
        selected = [row for row in rows if row[5] == shared_memory]
        phases = {}
        for phase, left, right in (
            ("pre_median_ttft", window["start_ns"], split),
            ("post_median_ttft", split, window["end_ns"]),
        ):
            phases[phase] = {
                "intersecting_launches": sum(row[0] < right and row[1] > left for row in selected),
                "seconds": sum(max(0, min(row[1], right) - max(row[0], left)) for row in selected) / 1e9,
            }
        subtypes.append(
            {
                "subtype": name,
                "source_semantics": "extend/prefill; post-median-TTFT launches are dynamic-chunk prefill interleaved with decode",
                "layers_per_model_forward": layer_count,
                "launches": len(selected),
                "seconds": sum(row[1] - row[0] for row in selected) / 1e9,
                "shape": shape,
                "launch_geometry": {
                    "grid_x_batch_sizes": sorted({row[2] for row in selected}),
                    "grid_y_q_heads": sorted({row[3] for row in selected}),
                    "grid_z_query_blocks": [min(row[4] for row in selected), max(row[4] for row in selected)],
                    "threads": 256,
                    "registers_per_thread": sorted({row[6] for row in selected}),
                    "dynamic_shared_memory_bytes": shared_memory,
                },
                "service_epoch": phases,
            }
        )
    total_ns = sum(row[1] - row[0] for row in rows)
    output = {
        "schema_version": 1,
        "pass": len(rows) == 3660 and total_ns == 6322473394,
        "evidence_class": "measured_trace_plus_pinned_source",
        "pinned_commit": PINNED_COMMIT,
        "source_hashes": {"extend_attention.py": EXTEND_SOURCE_SHA256, "triton_backend.py": BACKEND_SOURCE_SHA256},
        "kernel": "sglang.srt.layers.attention.triton_ops.extend_attention._fwd_kernel",
        "total_launches": len(rows),
        "total_seconds": total_ns / 1e9,
        "subtypes": sorted(subtypes, key=lambda row: row["seconds"], reverse=True),
        "selected_subtype": "local_sliding_extend",
        "causal_path": "For FP8 KV cache, TritonAttnBackend.forward_extend clones local K and V only because set_kv_buffer scales them in place before _fwd_kernel consumes the originals. Enqueueing the local cache quantize/store after _fwd_kernel preserves same-stream ordering and removes both full-tensor clones without gathering KV or changing model/kernel geometry.",
    }
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
