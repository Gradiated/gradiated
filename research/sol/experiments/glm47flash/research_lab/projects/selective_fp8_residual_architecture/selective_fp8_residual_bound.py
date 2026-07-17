#!/usr/bin/env python3
"""Exact AWQ residual accounting and conservative FP8 cost bound.

This is header-only: it never loads model payloads.  The optional fixture is
run separately in the pinned vLLM container because the host has no torch.
"""
import argparse
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path


def headers(root: Path):
    index = json.loads((root / "model.safetensors.index.json").read_text())
    by_file = {}
    for filename in set(index["weight_map"].values()):
        with (root / filename).open("rb") as stream:
            size = struct.unpack("<Q", stream.read(8))[0]
            by_file[filename] = json.loads(stream.read(size))
    for name, filename in index["weight_map"].items():
        item = by_file[filename][name]
        yield name, item["dtype"], item["shape"], item["data_offsets"][1] - item["data_offsets"][0]


def family(name: str) -> str:
    if name == "lm_head.weight":
        return "lm_head"
    if name.startswith("model.layers.0."):
        return "dense_layer_0"
    if ".mlp.shared_experts." in name:
        return "shared_experts"
    if name.endswith(".weight_scale") or name.endswith(".weight_shape"):
        return "quant_metadata"
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    groups = defaultdict(lambda: {"bytes": 0, "tensors": 0, "dtypes": Counter(), "matmul_flops": 0, "scale_bytes": 0})
    rows = []
    for name, dtype, shape, size in headers(args.checkpoint):
        group = family(name)
        item = groups[group]
        item["bytes"] += size
        item["tensors"] += 1
        item["dtypes"][dtype] += 1
        if dtype == "BF16" and len(shape) == 2 and group in {"lm_head", "dense_layer_0", "shared_experts"}:
            item["matmul_flops"] += 2 * shape[0] * shape[1]
            # Per-output-channel FP32 scale, the more expensive common case.
            item["scale_bytes"] += 4 * shape[0]
            rows.append({"name": name, "shape": shape, "bytes": size, "flops": 2 * shape[0] * shape[1], "scale_bytes": 4 * shape[0]})
    selected = {key: groups[key] for key in ("lm_head", "dense_layer_0", "shared_experts")}
    selected_bytes = sum(x["bytes"] for x in selected.values())
    selected_fp8_bytes = selected_bytes // 2 + sum(x["scale_bytes"] for x in selected.values())
    baseline = 0.5708266167229551
    target = 0.514
    residual_ceiling = 0.1409 + 0.0710
    result = {
        "schema_version": 1,
        "evidence_label": "measured safetensors headers; derived FP8 storage and endpoint ceilings; no quality claim",
        "checkpoint": str(args.checkpoint),
        "checkpoint_index_total_bytes": json.loads((args.checkpoint / "model.safetensors.index.json").read_text())["metadata"]["total_size"],
        "families": {k: {**v, "dtypes": dict(v["dtypes"]), "mib": v["bytes"] / 2**20} for k, v in groups.items()},
        "selected_residual": {
            "families": list(selected),
            "bytes": selected_bytes,
            "mib": selected_bytes / 2**20,
            "checkpoint_fraction": selected_bytes / json.loads((args.checkpoint / "model.safetensors.index.json").read_text())["metadata"]["total_size"],
            "matrix_flops_per_single_token": sum(x["matmul_flops"] for x in selected.values()),
            "fp8_e4m3_payload_plus_per_output_channel_fp32_scales_bytes": selected_fp8_bytes,
            "fp8_mib": selected_fp8_bytes / 2**20,
            "saved_mib": (selected_bytes - selected_fp8_bytes) / 2**20,
            "tensor_rows": rows,
        },
        "economic_target": {"control_usd_per_million_output": baseline, "promotion_target_usd_per_million_output": target, "required_throughput_multiplier": baseline / target},
        "bound": {
            "retained_trace_ceiling_head_plus_shared": residual_ceiling,
            "best_case_if_every_selected_residual_wall_time_were_halved": residual_ceiling / 2,
            "best_case_usd_per_million_if_that_bound_transferred": baseline * (1 - residual_ceiling / 2),
            "interpretation": "An optimistic trace-resident ceiling only barely crosses 10%; FP8 halves representation bytes, not GEMM work, and no current trace proves residual wall-time is byte-limited. This is not a promotion bound.",
        },
        "c32": {"current_l40s_loaded_mib": 38985, "l40s_capacity_mib": 46068, "fp8_saved_mib": (selected_bytes - selected_fp8_bytes) / 2**20, "judgment": "insufficient for c32: doubling the observed c16 KV-resident band needs multiple GiB, while selective residual FP8 saves under 0.8 GiB"},
        "exact_runtime_status": "generic Ada FP8 primitive exists in pinned vLLM, but current compressed-tensors pack-quantized W4 config maps ignored residual modules to UnquantizedLinearMethod; no exact mixed W4-plus-selective-FP8 checkpoint/config path is present",
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
