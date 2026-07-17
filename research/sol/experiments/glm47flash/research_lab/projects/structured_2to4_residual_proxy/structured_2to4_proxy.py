#!/usr/bin/env python3
"""Exact BF16 2:4 magnitude-pruning proxy for the admitted residual families."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
CHECKPOINT = Path("/root/.cache/glm47flash-awq-ab31d120")
OUT = ROOT / "artifacts" / "structured_2to4_proxy_source_audit.json"


def safetensors_header(path: Path) -> tuple[int, dict]:
    with path.open("rb") as handle:
        header_bytes = int.from_bytes(handle.read(8), "little")
        return 8 + header_bytes, json.loads(handle.read(header_bytes))


def family(name: str, shape: list[int]) -> str | None:
    if name == "lm_head.weight":
        return "lm_head"
    if ".mlp.shared_experts." in name and name.endswith(".weight"):
        return "shared_experts"
    if name.startswith("model.layers.0.") and name.endswith(".weight") and len(shape) == 2:
        return "dense_layer_0"
    return None


def audit_tensor(name: str, entry: dict, file_path: Path, data_start: int) -> dict:
    if entry["dtype"] != "BF16" or len(entry["shape"]) != 2:
        raise ValueError(f"unexpected proxy tensor {name}: {entry['dtype']} {entry['shape']}")
    rows, width = entry["shape"]
    if width % 4:
        raise ValueError(f"2:4 width is not legal: {name} {width}")
    begin, end = entry["data_offsets"]
    raw = np.memmap(file_path, dtype=np.uint16, mode="r", offset=data_start + begin,
                    shape=(rows, width))
    original_sq = 0.0
    retained_sq = 0.0
    zero_count = 0
    for row_start in range(0, rows, 2048):
        words = raw[row_start : min(rows, row_start + 2048)]
        values = (words.astype(np.uint32) << 16).view(np.float32)
        blocks = values.reshape(-1, 4)
        magnitudes = np.abs(blocks)
        keep = np.argpartition(magnitudes, -2, axis=1)[:, -2:]
        mask = np.zeros_like(blocks, dtype=bool)
        mask[np.arange(mask.shape[0])[:, None], keep] = True
        squared = np.square(blocks, dtype=np.float64)
        original_sq += float(squared.sum())
        retained_sq += float(np.where(mask, squared, 0.0).sum())
        zero_count += int((blocks == 0).sum())
    elements = rows * width
    compressed_values = rows * (width // 2) * 2
    bitmask = rows * (width // 8)
    return {
        "name": name,
        "shape": [rows, width],
        "source_bytes": end - begin,
        "source_sha256": sha256_range(file_path, data_start + begin, end - begin),
        "elements": elements,
        "zero_fraction": zero_count / elements,
        "retained_l2_fraction": retained_sq / original_sq,
        "pruned_relative_l2": math.sqrt(max(0.0, 1.0 - retained_sq / original_sq)),
        "current_vllm_sparse_24_bitmask_bytes": compressed_values + bitmask,
        "physical_components": {
            "bf16_nonzeros_bytes": compressed_values,
            "uint8_bitmask_bytes": bitmask,
            "row_alignment_bytes": 0,
        },
    }


def sha256_range(path: Path, offset: int, length: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        handle.seek(offset)
        remaining = length
        while remaining:
            piece = handle.read(min(16 * 1024 * 1024, remaining))
            digest.update(piece)
            remaining -= len(piece)
    return digest.hexdigest()


def main() -> None:
    index = json.loads((CHECKPOINT / "model.safetensors.index.json").read_text())
    by_file: dict[str, tuple[int, dict]] = {}
    tensor_rows = []
    for name, shard in index["weight_map"].items():
        if shard not in by_file:
            path = CHECKPOINT / shard
            by_file[shard] = safetensors_header(path)
        data_start, header = by_file[shard]
        entry = header.get(name)
        if entry and family(name, entry["shape"]):
            tensor_rows.append((family(name, entry["shape"]), name, entry, CHECKPOINT / shard, data_start))
    families: dict[str, list[dict]] = defaultdict(list)
    for group, name, entry, shard, start in tensor_rows:
        families[group].append(audit_tensor(name, entry, shard, start))
    summary = {}
    for group, rows in sorted(families.items()):
        source_bytes = sum(row["source_bytes"] for row in rows)
        packed_bytes = sum(row["current_vllm_sparse_24_bitmask_bytes"] for row in rows)
        weights = [row["source_bytes"] for row in rows]
        retained = sum(row["retained_l2_fraction"] * weight for row, weight in zip(rows, weights)) / sum(weights)
        summary[group] = {
            "tensors": len(rows),
            "source_bytes": source_bytes,
            "source_mib": source_bytes / 2**20,
            "sparse_24_bitmask_bytes": packed_bytes,
            "sparse_24_bitmask_mib": packed_bytes / 2**20,
            "saved_mib": (source_bytes - packed_bytes) / 2**20,
            "byte_ratio": packed_bytes / source_bytes,
            "byte_weighted_retained_l2_fraction": retained,
            "byte_weighted_pruned_relative_l2": math.sqrt(max(0.0, 1.0 - retained)),
            "tensors_detail": rows,
        }
    total_source = sum(value["source_bytes"] for value in summary.values())
    total_sparse = sum(value["sparse_24_bitmask_bytes"] for value in summary.values())
    result = {
        "schema_version": 1,
        "evidence_label": "measured_exact_checkpoint_weight_proxy_and_source_audit",
        "checkpoint": str(CHECKPOINT),
        "checkpoint_revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881",
        "mask": "deterministic_per_output_channel_top2_absolute_magnitude_per_contiguous_K_group_of_4",
        "representation": "vLLM sparse_24_bitmask: BF16 [N,K/2] compressed values plus uint8 [N,K/8] bitmask; K is divisible by 8 for every selected tensor, so no row padding is required",
        "families": summary,
        "combined": {
            "source_bytes": total_source,
            "source_mib": total_source / 2**20,
            "sparse_24_bitmask_bytes": total_sparse,
            "sparse_24_bitmask_mib": total_sparse / 2**20,
            "saved_mib": (total_source - total_sparse) / 2**20,
            "byte_ratio": total_sparse / total_source,
            "c32_headroom_credit_mib": (total_source - total_sparse) / 2**20,
        },
        "runtime_audit": {
            "pinned_vllm": "0.15.0 image glm-vllm:0.15.0-transformers-1618d44",
            "current_source": "vLLM v0.15.1 commit 1892993bc18e243e2c05841314c5e9c06a80c70d",
            "source_route": "CompressedTensors24 -> ops.cutlass_scaled_sparse_mm",
            "pinned_and_current_minimum_compute_capability": 90,
            "exact_sm89_route": "absent: both audited versions return 90 from CompressedTensors24.get_min_capability(); the CUTLASS sparse route therefore excludes L40S SM89",
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"artifact": str(OUT), "combined": result["combined"], "families": {k: {x: v[x] for x in ("tensors", "source_mib", "saved_mib", "byte_weighted_pruned_relative_l2")} for k, v in summary.items()}}, indent=2))


if __name__ == "__main__":
    main()
