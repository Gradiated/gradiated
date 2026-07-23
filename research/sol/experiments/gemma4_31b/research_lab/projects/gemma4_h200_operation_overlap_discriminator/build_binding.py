#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
import collections
import hashlib
import json
import os
import pathlib
import sqlite3
import statistics
import struct
from typing import Any


PINNED_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
PINNED_IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
EXPECTED = {
    "profile.sqlite": "b81e812e9f1a005b8648c7bc151e19a38fb158f17521ba304d3a656b9f2996f3",
    "extend_attention.py": "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1",
    "triton_backend.py": "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
    "fp8_utils.py": "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9",
}
GATE_KEY = "model.language_model.layers.0.mlp.gate_proj.weight"
UP_KEY = "model.language_model.layers.0.mlp.up_proj.weight"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def safetensors_header(path: pathlib.Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        size = struct.unpack("<Q", handle.read(8))[0]
        return json.loads(handle.read(size))


def require_hash(path: pathlib.Path, expected: str) -> str:
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(
            f"content_identity_mismatch:{path.name}:{expected}:{actual}"
        )
    return actual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    paths = {
        "profile.sqlite": args.input_root / "evidence/control-profile.sqlite",
        "consumer_audit": args.input_root / "evidence/consumers.jsonl",
        "attribution": args.input_root / "evidence/ATTRIBUTION.json",
        "attention_map": args.input_root / "evidence/ATTENTION_SUBTYPE_MAP.json",
        "fp8_map": args.input_root / "evidence/FP8_LINEAR_SHAPE_MAP.json",
        "extend_attention.py": args.input_root / "source/extend_attention.py",
        "triton_backend.py": args.input_root / "source/triton_backend.py",
        "fp8_utils.py": args.input_root / "source/fp8_utils.py",
        "weights": args.input_root / "weights/layer0-gate-up.safetensors",
        "weight_manifest": args.input_root / "weights/MANIFEST.json",
    }
    hashes = {
        name: require_hash(paths[name], expected)
        for name, expected in EXPECTED.items()
    }
    for name in (
        "consumer_audit",
        "attribution",
        "attention_map",
        "fp8_map",
        "weights",
        "weight_manifest",
    ):
        hashes[name] = sha256(paths[name])

    attribution = json.loads(paths["attribution"].read_text())
    attention_map = json.loads(paths["attention_map"].read_text())
    fp8_map = json.loads(paths["fp8_map"].read_text())
    weight_manifest = json.loads(paths["weight_manifest"].read_text())
    if attribution.get("pass") is not True:
        raise RuntimeError("authoritative_attribution_invalid")
    if attention_map.get("pass") is not True:
        raise RuntimeError("attention_map_invalid")
    if (
        weight_manifest["snapshot"]["sha256"] != hashes["weights"]
        or weight_manifest["snapshot"]["path"]
        != str(paths["weights"].resolve())
    ):
        raise RuntimeError("weight_snapshot_manifest_mismatch")

    header = safetensors_header(paths["weights"])
    expected_weight_shape = [21504, 5376]
    for key in (GATE_KEY, UP_KEY):
        if header.get(key, {}).get("dtype") != "BF16":
            raise RuntimeError(f"weight_dtype_mismatch:{key}")
        if header[key]["shape"] != expected_weight_shape:
            raise RuntimeError(f"weight_shape_mismatch:{key}:{header[key]}")

    connection = sqlite3.connect(
        f"file:{paths['profile.sqlite'].resolve()}?mode=ro", uri=True
    )
    attention_rows = connection.execute(
        """
        SELECT k.gridX, k.gridY, k.gridZ, k.blockX, k.blockY, k.blockZ,
               k.dynamicSharedMemory, k.registersPerThread, k.end - k.start
        FROM CUPTI_ACTIVITY_KIND_KERNEL k
        JOIN StringIds s ON s.id = k.shortName
        WHERE s.value = '_fwd_kernel' AND k.dynamicSharedMemory = 81920
        ORDER BY k.start
        """
    ).fetchall()
    if len(attention_rows) != 3050:
        raise RuntimeError(
            f"local_attention_launch_count_mismatch:{len(attention_rows)}"
        )
    attention_groups: dict[tuple[int, int], list[tuple[Any, ...]]] = (
        collections.defaultdict(list)
    )
    for row in attention_rows:
        attention_groups[(row[0], row[2])].append(row)
    selected_key, selected_rows = max(
        attention_groups.items(),
        key=lambda item: (len(item[1]), sum(row[-1] for row in item[1])),
    )
    if selected_key != (1, 32):
        raise RuntimeError(f"unexpected_dominant_attention_geometry:{selected_key}")

    fp8_rows = connection.execute(
        """
        SELECT k.gridX, k.gridY, k.gridZ, k.blockX, k.blockY, k.blockZ,
               k.clusterX, k.clusterY, k.clusterZ, k.dynamicSharedMemory,
               k.registersPerThread, k.end - k.start
        FROM CUPTI_ACTIVITY_KIND_KERNEL k
        JOIN StringIds s ON s.id = k.demangledName
        WHERE s.value LIKE '%cutlass_3x_gemm_sm90_fp8%'
          AND s.value LIKE '%C<(int)128>%, cute::C<(int)128>%, cute::C<(int)128>>%'
        ORDER BY k.start
        """
    ).fetchall()
    if len(fp8_rows) != 14400:
        raise RuntimeError(f"dominant_fp8_launch_count_mismatch:{len(fp8_rows)}")
    gate_up_rows = fp8_rows[2::4]
    if len(gate_up_rows) != 3600:
        raise RuntimeError(f"gate_up_launch_count_mismatch:{len(gate_up_rows)}")
    gate_up_intervals = connection.execute(
        """
        SELECT k.start, k.end
        FROM CUPTI_ACTIVITY_KIND_KERNEL k
        JOIN StringIds s ON s.id = k.demangledName
        WHERE s.value LIKE '%cutlass_3x_gemm_sm90_fp8%'
          AND s.value LIKE '%C<(int)128>%, cute::C<(int)128>%, cute::C<(int)128>>%'
        ORDER BY k.start
        """
    ).fetchall()[2::4]
    gate_up_starts = [row[0] for row in gate_up_intervals]
    adjacency_gaps_ns = []
    selected_intervals = connection.execute(
        """
        SELECT k.start, k.end
        FROM CUPTI_ACTIVITY_KIND_KERNEL k
        JOIN StringIds s ON s.id = k.shortName
        WHERE s.value = '_fwd_kernel'
          AND k.dynamicSharedMemory = 81920
          AND k.gridX = 1 AND k.gridZ = 32
        ORDER BY k.start
        """
    ).fetchall()
    for _, attention_end in selected_intervals:
        index = bisect.bisect_left(gate_up_starts, attention_end)
        if index < len(gate_up_starts):
            adjacency_gaps_ns.append(gate_up_starts[index] - attention_end)
    if len(adjacency_gaps_ns) != len(selected_rows):
        raise RuntimeError(
            f"attention_gate_up_temporal_join_incomplete:{len(adjacency_gaps_ns)}"
        )

    consumers = [
        json.loads(line)
        for line in paths["consumer_audit"].read_text().splitlines()
        if line
    ]
    gate_up_consumers = [
        row for row in consumers if row["prefix"].endswith("gate_up_proj")
    ]
    if len(gate_up_consumers) != 60:
        raise RuntimeError(
            f"gate_up_consumer_count_mismatch:{len(gate_up_consumers)}"
        )
    if any(
        row["consumer"]
        != "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm"
        or row["weight"]["shape"] != [5376, 43008]
        or row["weight"]["dtype"] != "torch.float8_e4m3fn"
        or row["weight_scale"]["shape"] != [1, 43008]
        or row["out_dtype"] != "torch.bfloat16"
        for row in gate_up_consumers
    ):
        raise RuntimeError("gate_up_consumer_contract_mismatch")

    selected_attention = next(
        row
        for row in attention_map["subtypes"]
        if row["subtype"] == "local_sliding_extend"
    )
    if selected_attention["shape"] != {
        "block_m": 64,
        "block_n": 64,
        "kv_heads": 16,
        "q_heads": 32,
        "qk_head_dim": 256,
        "v_head_dim": 256,
        "window": 1024,
    }:
        raise RuntimeError("attention_shape_contract_mismatch")
    if fp8_map["dominant_exact_shape"]["projection"] != "gate_up_proj":
        raise RuntimeError("fp8_projection_contract_mismatch")

    value = {
        "schema_version": 1,
        "pass": True,
        "evidence_class": {
            "shape_and_launch_binding": "measured_profile_plus_derived_temporal_join",
            "consumer_binding": "measured_behavioral_audit",
            "source_and_weight_identity": "content_addressed",
            "overlap_hypothesis": "inferred_pending_h200_measurement",
        },
        "runtime": {
            "release": "sglang v0.5.13",
            "commit": PINNED_COMMIT,
            "image": PINNED_IMAGE,
            "accelerator": "nvidia-h200-sxm",
        },
        "workload": {
            "concurrency": 32,
            "nano_batches": 2,
            "independence": "attention/KV work and FP8-linear work use disjoint input, weight, cache, and output buffers",
        },
        "attention": {
            "consumer_symbol": "sglang.srt.layers.attention.triton_ops.extend_attention.extend_attention_fwd",
            "kernel_symbol": "_fwd_kernel",
            "phase": "dynamic-chunk prefill interleaved with c32 service",
            "selected_subtype": "local_sliding_extend",
            "query_rows": 2048,
            "request_rows": 1,
            "prefix_rows_per_request": 1024,
            "q_heads": 32,
            "kv_heads": 16,
            "qk_head_dim": 256,
            "v_head_dim": 256,
            "kv_dtype": "torch.float8_e5m2",
            "activation_dtype": "torch.bfloat16",
            "sliding_window_size": 1024,
            "measured_geometry": {
                "grid": [selected_key[0], 32, selected_key[1]],
                "block": list(selected_rows[0][3:6]),
                "dynamic_shared_memory_bytes": selected_rows[0][6],
                "registers_per_thread": selected_rows[0][7],
                "launches": len(selected_rows),
                "seconds": sum(row[-1] for row in selected_rows) / 1e9,
                "mean_microseconds": sum(row[-1] for row in selected_rows)
                / len(selected_rows)
                / 1e3,
            },
        },
        "fp8_linear": {
            "consumer_symbol": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
            "projection": "model.language_model.layers.0.mlp.gate_up_proj",
            "shape_mkn": [2048, 5376, 43008],
            "shape_m_binding": {
                "rule": "The selected grid-z=32 local-attention launch fixes the flattened model-forward token count at 32*BLOCK_M=2048; the next measured gate/up launch is joined within the same layer-forward sequence.",
                "joined_pairs": len(adjacency_gaps_ns),
                "median_attention_end_to_gate_up_start_microseconds": statistics.median(
                    adjacency_gaps_ns
                )
                / 1e3,
                "maximum_attention_end_to_gate_up_start_microseconds": max(
                    adjacency_gaps_ns
                )
                / 1e3,
                "evidence_class": "derived_from_measured_temporal_adjacency_and_pinned_layer_order",
            },
            "activation_dtype": "torch.float8_e4m3fn",
            "activation_scale": {
                "dtype": "torch.float32",
                "shape": [2048, 1],
            },
            "weight_dtype": "torch.float8_e4m3fn",
            "weight_layout": "column_major_KN",
            "weight_scale": {"dtype": "torch.float32", "shape": [1, 43008]},
            "output_dtype": "torch.bfloat16",
            "measured_geometry": {
                "grid": list(gate_up_rows[0][0:3]),
                "block": list(gate_up_rows[0][3:6]),
                "cluster": list(gate_up_rows[0][6:9]),
                "dynamic_shared_memory_bytes": gate_up_rows[0][9],
                "registers_per_thread": gate_up_rows[0][10],
                "launches": len(gate_up_rows),
                "seconds": sum(row[-1] for row in gate_up_rows) / 1e9,
                "mean_microseconds": sum(row[-1] for row in gate_up_rows)
                / len(gate_up_rows)
                / 1e3,
            },
        },
        "quality_contract": {
            "serial_and_concurrent_attention_bitwise_equal": True,
            "serial_and_concurrent_fp8_linear_bitwise_equal": True,
            "complete_outputs_consumed": True,
        },
        "decision_contract": {
            "promote_concurrent_ratio_lte": 0.8,
            "close_pair_concurrent_ratio_gte": 0.9,
            "overlap_efficiency": "(attention_ms + fp8_linear_ms - concurrent_ms) / min(attention_ms, fp8_linear_ms)",
        },
        "inputs": {
            "root": str(args.input_root.resolve()),
            "paths": {
                name: str(path.relative_to(args.input_root))
                for name, path in paths.items()
            },
            "sha256": hashes,
            "weight_keys": [GATE_KEY, UP_KEY],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
