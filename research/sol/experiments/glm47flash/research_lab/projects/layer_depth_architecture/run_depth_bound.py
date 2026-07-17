"""Exact checkpoint-header and trace bound for whole-block depth removal."""

from __future__ import annotations

import argparse
import glob
import json
import re
import struct
from collections import defaultdict
from pathlib import Path

GIB = 2**30


def tensor_headers(model_dir: Path) -> dict[str, tuple[str, list[int], int]]:
    tensors: dict[str, tuple[str, list[int], int]] = {}
    for path in sorted(model_dir.glob("*.safetensors")):
        with path.open("rb") as handle:
            header_size = struct.unpack("<Q", handle.read(8))[0]
            header = json.loads(handle.read(header_size))
        for name, value in header.items():
            if name != "__metadata__":
                start, end = value["data_offsets"]
                tensors[name] = (value["dtype"], value["shape"], end - start)
    return tensors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((args.model_dir / "config.json").read_text())
    tensors = tensor_headers(args.model_dir)
    configured_layers = int(config["num_hidden_layers"])
    by_layer: dict[int, int] = defaultdict(int)
    for name, (_, _, payload) in tensors.items():
        match = re.match(r"model\.layers\.(\d+)\.", name)
        if match:
            by_layer[int(match.group(1))] += payload
    actual_indices = sorted(by_layer)
    if actual_indices != list(range(actual_indices[-1] + 1)):
        raise ValueError("checkpoint headers do not cover every configured layer")
    layers = len(actual_indices)
    trace = json.loads(args.trace.read_text())
    decode = trace["decode"]
    repeated_layers = layers - 1
    patterns = {
        "even_5": [6, 15, 24, 33, 42],
        "even_4": [9, 20, 31, 42],
        "even_3": [12, 24, 36],
    }
    baseline_rate = 535.286
    planning_rate = 1.10
    measured_rate = 0.8581222
    baseline_cost = planning_rate / baseline_rate * 1e6 / 3600
    observed_c16_mib = 42827
    card_capacity_mib = 46068
    kv_per_layer_c16_gib = (512 + 64) * 2 * 16 * 8192 / GIB
    kv_per_layer_c32_gib = kv_per_layer_c16_gib * 2
    loaded_weight_per_layer_gib = sum(by_layer[i] for i in range(1, layers)) / (layers - 1) / GIB
    rows = []
    for name, skipped in patterns.items():
        weight_bytes = sum(by_layer[i] for i in skipped)
        repeated_fraction = len(skipped) / repeated_layers
        depth_fraction = len(skipped) / layers
        # Conservative endpoint bound uses all 47 layers, not the optimistic 46.
        upper_speed = baseline_rate / (1 - depth_fraction)
        cost = planning_rate / upper_speed * 1e6 / 3600
        rows.append({
            "pattern": name,
            "skipped_layers": skipped,
            "weight_bytes": weight_bytes,
            "weight_gib": weight_bytes / GIB,
            "kv_saved_gib_at_c16_8192": len(skipped) * (512 + 64) * 2 * 16 * 8192 / GIB,
            "repeated_layer_work_fraction": repeated_fraction,
            "conservative_speed_upper_bound_tok_s": upper_speed,
            "conservative_cost_lower_bound_usd_per_million_output": cost,
            "cost_reduction_upper_bound_pct": (cost / baseline_cost - 1) * -100,
        })
    result = {
        "evidence_class": "derived_exact_safetensor_headers_plus_measured_trace",
        "scope": "AWQ checkpoint; whole complete blocks; no provider or quality measurement",
        "checkpoint": str(args.model_dir),
        "config": {k: config[k] for k in ("num_hidden_layers", "hidden_size", "moe_intermediate_size", "n_routed_experts", "num_experts_per_tok", "kv_lora_rank", "v_head_dim")},
        "layer_identity_check": {"configured_num_hidden_layers": configured_layers, "checkpoint_layer_indices": actual_indices, "effective_complete_block_count": layers, "note": "Current checkpoint headers contain layers 0..47 (one dense plus 47 sparse), despite config num_hidden_layers=47; bounds use loaded tensor reality."},
        "checkpoint_payload_gib": sum(v[2] for v in tensors.values()) / GIB,
        "baseline": {"output_tok_s": baseline_rate, "planning_usd_per_gpu_hour": planning_rate, "measured_experiment_usd_per_gpu_hour": measured_rate, "planning_cost_usd_per_million_output": baseline_cost},
        "capacity": {"observed_c16_peak_mib": observed_c16_mib, "card_capacity_mib": card_capacity_mib, "kv_per_sparse_layer_c16_gib": kv_per_layer_c16_gib, "kv_per_sparse_layer_c32_gib": kv_per_layer_c32_gib, "c32_min_blocks_by_kv_only": max(0, int((observed_c16_mib / 1024 + (layers * kv_per_layer_c32_gib - layers * kv_per_layer_c16_gib) - card_capacity_mib / 1024) / kv_per_layer_c32_gib) + 1), "estimated_sparse_weight_gib_per_layer": loaded_weight_per_layer_gib, "note": "Capacity threshold is a derived lower-bound model using retained peak memory and MLA state; allocator and runtime overhead can only worsen it."},
        "trace": {k: decode[k] for k in ("kernel_count", "kernel_duration_sum_ms", "kernel_families")},
        "patterns": rows,
        "interpretation": "Weight and MLA state savings are real, but endpoint cost is an upper-bound proxy because summed kernel durations overlap and layer removal can expose launch/MLA bottlenecks.",
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
