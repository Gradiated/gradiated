#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import struct
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any


MODEL = "moonshotai/Kimi-K3"
REVISION = "9f62e4e9fffbd0a83ddd60e1c209d828994b3569"
BASE = f"https://huggingface.co/{MODEL}/resolve/{REVISION}"
TREE = f"https://huggingface.co/api/models/{MODEL}/tree/{REVISION}?recursive=true&expand=false&limit=1000"
DTYPE_BYTES = {"BOOL": 1, "U8": 1, "I8": 1, "I16": 2, "U16": 2, "F16": 2, "BF16": 2, "I32": 4, "U32": 4, "F32": 4, "I64": 8, "U64": 8, "F64": 8}


def request_bytes(url: str, byte_range: tuple[int, int] | None = None) -> bytes:
    headers = {"User-Agent": "gradiated-kimi-k3-header-inventory/1"}
    if byte_range is not None:
        headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        expected = byte_range[1] - byte_range[0] + 1 if byte_range else None
        payload = response.read((expected + 1) if expected else None)
        if expected is not None and len(payload) != expected:
            raise RuntimeError(f"range request returned {len(payload)} bytes, expected {expected}: {url}")
        return payload


def category(name: str) -> str:
    if ".experts." in name:
        return "routed_experts"
    if ".shared_experts." in name:
        return "shared_experts"
    if "routed_expert_down_proj" in name or "routed_expert_up_proj" in name:
        return "latent_moe_projection"
    if ".gate." in name and "self_attn" not in name:
        return "router"
    if "self_attn" in name:
        return "attention"
    if ".mlp." in name or "block_sparse_moe" in name:
        return "dense_or_shared_ffn"
    if "embed_tokens" in name or "lm_head" in name:
        return "embedding_or_lm_head"
    if "vision" in name or "mm_projector" in name:
        return "vision"
    return "norm_bias_or_other"


def scan_shard(entry: dict[str, Any]) -> dict[str, Any]:
    url = f"{BASE}/{entry['path']}"
    prefix = request_bytes(url, (0, 7))
    header_len = struct.unpack("<Q", prefix)[0]
    if header_len <= 0 or header_len > 256_000_000:
        raise RuntimeError(f"implausible safetensors header length {header_len}: {entry['path']}")
    raw = request_bytes(url, (8, 7 + header_len))
    header = json.loads(raw)
    summaries: dict[str, dict[str, Any]] = defaultdict(lambda: {"tensor_count": 0, "logical_elements": 0, "storage_bytes": 0, "dtypes": defaultdict(int), "sample_shapes": []})
    max_end = 0
    tensor_count = 0
    for name, metadata in header.items():
        if name == "__metadata__":
            continue
        tensor_count += 1
        shape = metadata["shape"]
        elements = 1
        for dim in shape:
            elements *= dim
        start, end = metadata["data_offsets"]
        max_end = max(max_end, end)
        group = summaries[category(name)]
        group["tensor_count"] += 1
        group["logical_elements"] += elements
        group["storage_bytes"] += end - start
        group["dtypes"][metadata["dtype"]] += elements
        if len(group["sample_shapes"]) < 3:
            group["sample_shapes"].append({"name": name, "dtype": metadata["dtype"], "shape": shape})
    return {
        "path": entry["path"],
        "file_bytes": entry["size"],
        "header_bytes": header_len,
        "header_sha256": hashlib.sha256(raw).hexdigest(),
        "tensor_count": tensor_count,
        "payload_bytes_from_offsets": max_end,
        "expected_file_bytes_from_header": 8 + header_len + max_end,
        "categories": {key: {**value, "dtypes": dict(value["dtypes"])} for key, value in summaries.items()},
    }


def merge(shards: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, dict[str, Any]] = defaultdict(lambda: {"tensor_count": 0, "logical_elements": 0, "storage_bytes": 0, "dtypes": defaultdict(int), "sample_shapes": []})
    for shard in shards:
        for name, summary in shard["categories"].items():
            target = categories[name]
            target["tensor_count"] += summary["tensor_count"]
            target["logical_elements"] += summary["logical_elements"]
            target["storage_bytes"] += summary["storage_bytes"]
            for dtype, count in summary["dtypes"].items():
                target["dtypes"][dtype] += count
            for sample in summary["sample_shapes"]:
                if len(target["sample_shapes"]) < 5:
                    target["sample_shapes"].append(sample)
    return {key: {**value, "dtypes": dict(value["dtypes"])} for key, value in categories.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    tree = json.loads(request_bytes(TREE))
    entries = sorted(
        (entry for entry in tree if entry.get("type") == "file" and entry["path"].startswith("model-") and entry["path"].endswith(".safetensors")),
        key=lambda entry: entry["path"],
    )
    if len(entries) != 96:
        raise RuntimeError(f"expected 96 checkpoint shards, found {len(entries)}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        shards = list(pool.map(scan_shard, entries))
    mismatches = [shard["path"] for shard in shards if shard["expected_file_bytes_from_header"] != shard["file_bytes"]]
    result = {
        "schema_version": 1,
        "evidence_class": "measured_released_safetensors_headers",
        "model": MODEL,
        "revision": REVISION,
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "method": "HTTP byte ranges for 8-byte safetensors prefix and exact JSON header; tensor payloads not downloaded",
        "source_urls": [TREE, f"https://huggingface.co/{MODEL}/tree/{REVISION}"],
        "shard_count": len(shards),
        "checkpoint_bytes": sum(shard["file_bytes"] for shard in shards),
        "header_bytes": sum(shard["header_bytes"] for shard in shards),
        "tensor_count": sum(shard["tensor_count"] for shard in shards),
        "file_size_mismatches": mismatches,
        "categories": merge(shards),
        "shards": [{key: value for key, value in shard.items() if key != "categories"} for shard in shards],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("model", "revision", "shard_count", "checkpoint_bytes", "header_bytes", "tensor_count", "file_size_mismatches")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
