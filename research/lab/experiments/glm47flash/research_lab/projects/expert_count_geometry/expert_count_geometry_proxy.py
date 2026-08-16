#!/usr/bin/env python3
"""Header-bound, semantics-changing MoE expert-count geometry screen."""

import argparse
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path


ROOT = Path("/root/.cache/glm47flash-awq-ab31d120")
L40S_L2_BYTES = 96 * 1024 * 1024
SM_COUNT = 142
ACTIVE_ROWS = 16
ROUTED_LAYERS = 47
HIDDEN = 2048
MOE_WIDTH = 1536
BASELINE_TOK_S = 535.2861037029285
BASELINE_USD_PER_M = 0.5708266167229551
TARGET_USD_PER_M = 0.514


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def header(path: Path) -> dict:
    with path.open("rb") as source:
        size = struct.unpack("<Q", source.read(8))[0]
        return json.loads(source.read(size))


def binomial_histogram(assignments: int, experts: int) -> dict[str, float]:
    return {
        str(rows): experts * math.comb(assignments, rows) * (1 / experts) ** rows
        * (1 - 1 / experts) ** (assignments - rows)
        for rows in range(assignments + 1)
    }


def skew_histogram(assignments: int, experts: int) -> dict:
    hot_experts = math.ceil(experts * 0.2)
    cold_experts = experts - hot_experts
    hot_probability = 0.8 / hot_experts
    cold_probability = 0.2 / cold_experts

    def group(count: int, probability: float) -> dict[str, float]:
        return {
            str(rows): count * math.comb(assignments, rows) * probability**rows
            * (1 - probability) ** (assignments - rows)
            for rows in range(assignments + 1)
        }

    return {
        "label": "synthetic_80pct_assignment_mass_on_20pct_experts_not_checkpoint_trace",
        "hot_experts": hot_experts,
        "cold_experts": cold_experts,
        "hot_expected_rows_per_expert": assignments * hot_probability,
        "cold_expected_rows_per_expert": assignments * cold_probability,
        "expected_histogram": {
            "hot": group(hot_experts, hot_probability),
            "cold": group(cold_experts, cold_probability),
        },
    }


def expected_nonempty(histogram: dict[str, float], experts: int) -> float:
    return experts - histogram["0"]


def tensor_inventory() -> dict:
    config = json.loads((ROOT / "config.json").read_text())
    index_path = ROOT / "model.safetensors.index.json"
    weight_map = json.loads(index_path.read_text())["weight_map"]
    headers: dict[str, dict] = {}
    by_layer_expert: dict[tuple[int, int], int] = defaultdict(int)
    projection_shapes: dict[str, set[tuple[int, ...]]] = defaultdict(set)
    for name, filename in weight_map.items():
        parts = name.split(".")
        if len(parts) < 8 or parts[0:3] != ["model", "layers", parts[2]]:
            continue
        if parts[3:5] != ["mlp", "experts"]:
            continue
        layer, expert, projection = int(parts[2]), int(parts[5]), parts[6]
        if filename not in headers:
            headers[filename] = header(ROOT / filename)
        entry = headers[filename][name]
        start, end = entry["data_offsets"]
        by_layer_expert[(layer, expert)] += end - start
        if projection in {"gate_proj", "up_proj", "down_proj"} and name.endswith("weight_packed"):
            projection_shapes[projection].add(tuple(entry["shape"]))
    bytes_per_expert = set(by_layer_expert.values())
    layers = sorted({layer for layer, _ in by_layer_expert})
    counts = {layer: sum(1 for current, _ in by_layer_expert if current == layer) for layer in layers}
    if config["n_routed_experts"] != 64 or config["num_experts_per_tok"] != 4:
        raise ValueError("unexpected routed geometry")
    if len(layers) != ROUTED_LAYERS or set(counts.values()) != {64} or len(bytes_per_expert) != 1:
        raise ValueError("checkpoint sparse-expert inventory is not the expected 46x64 uniform layout")
    return {
        "config_sha256": sha256(ROOT / "config.json"),
        "index_sha256": sha256(index_path),
        "config_geometry": {
            key: config[key]
            for key in ("hidden_size", "moe_intermediate_size", "num_hidden_layers", "n_routed_experts", "num_experts_per_tok", "n_shared_experts")
        },
        "routed_layers": layers,
        "experts_per_layer": 64,
        "expert_bytes": bytes_per_expert.pop(),
        "packed_projection_shapes": {key: sorted(value) for key, value in projection_shapes.items()},
    }


def candidate(experts: int, top_k: int, inventory: dict) -> dict:
    assignments = ACTIVE_ROWS * top_k
    expert_bytes = inventory["expert_bytes"]
    parameter_count = 3 * HIDDEN * MOE_WIDTH
    uniform = binomial_histogram(assignments, experts)
    active_flops_per_layer = 2 * parameter_count * assignments
    model_routed_bytes = ROUTED_LAYERS * experts * expert_bytes
    return {
        "experts": experts,
        "top_k": top_k,
        "assignments_per_sparse_layer_at_c16": assignments,
        "layer_expert_bytes": experts * expert_bytes,
        "layer_expert_mib": experts * expert_bytes / 1024**2,
        "fits_entire_layer_in_96MiB_l2": experts * expert_bytes <= L40S_L2_BYTES,
        "routed_checkpoint_bytes": model_routed_bytes,
        "routed_checkpoint_gib": model_routed_bytes / 1024**3,
        "routed_parameter_count": ROUTED_LAYERS * experts * parameter_count,
        "active_expert_flops_per_sparse_layer": active_flops_per_layer,
        "active_expert_flops_per_decode_step_all_sparse_layers": active_flops_per_layer * ROUTED_LAYERS,
        "router_score_flops_per_sparse_layer": 2 * ACTIVE_ROWS * HIDDEN * experts,
        "max_active_expert_groups_per_sm": experts / SM_COUNT,
        "uniform": {
            "expected_rows_per_expert": assignments / experts,
            "expected_nonempty_experts": expected_nonempty(uniform, experts),
            "expected_rows_per_nonempty_expert": assignments / expected_nonempty(uniform, experts),
            "expected_histogram_expert_count": uniform,
        },
        "balanced": {
            "rows_per_expert": assignments // experts if assignments % experts == 0 else None,
            "active_experts": min(experts, assignments),
        },
        "synthetic_skew": skew_histogram(assignments, experts),
        "semantics": "expert merging/selecting and router retraining required; this proxy does not preserve outputs",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = tensor_inventory()
    candidates = [candidate(experts, top_k, inventory) for experts, top_k in ((64, 4), (32, 4), (16, 4), (16, 2))]
    stock = candidates[0]
    trace_paths = [
        Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/allocations/nebius_l40s_vllm_awq_splits_ab_v24r2/trace-regions.json"),
        Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/allocations/nebius_l40s_vllm_awq_splits_ab_v25r1/trace-regions.json"),
    ]
    moe_shares = []
    routing_shares = []
    for path in trace_paths:
        trace = json.loads(path.read_text())["decode"]
        exact = trace["top_exact_kernels"]
        moe_shares.append(sum(item["share_of_kernel_duration"] for item in exact if "marlin_moe" in item["name"]))
        routing_shares.append(next(item["share_of_kernel_duration"] for item in trace["kernel_families"] if item["family"] == "moe_routing_sort"))
    required_wall_reduction = 1 - TARGET_USD_PER_M / BASELINE_USD_PER_M
    min_moe_share = min(moe_shares)
    min_routing_share = min(routing_shares)
    result = {
        "schema_version": 1,
        "evidence_label": "derived_exact_checkpoint_header_and_measured_summed_trace_proxy_not_gpu_result",
        "inventory": inventory,
        "chip": {"name": "L40S Ada", "sm_count": SM_COUNT, "l2_bytes": L40S_L2_BYTES},
        "c16": {"active_rows": ACTIVE_ROWS, "baseline_output_tokens_per_second": BASELINE_TOK_S},
        "economic_gate": {
            "baseline_usd_per_million_output": BASELINE_USD_PER_M,
            "target_usd_per_million_output": TARGET_USD_PER_M,
            "required_nonoverlapped_wall_time_reduction": required_wall_reduction,
            "required_output_tokens_per_second": BASELINE_TOK_S / (1 - required_wall_reduction),
        },
        "candidates": candidates,
        "comparisons": {
            "16_top4_vs_stock": {
                "active_flops_ratio": candidates[2]["active_expert_flops_per_sparse_layer"] / stock["active_expert_flops_per_sparse_layer"],
                "routed_weight_bytes_ratio": candidates[2]["routed_checkpoint_bytes"] / stock["routed_checkpoint_bytes"],
                "router_score_flops_ratio": candidates[2]["router_score_flops_per_sparse_layer"] / stock["router_score_flops_per_sparse_layer"],
                "l2_discontinuity": "only 16/top4 fits all routed experts from one sparse layer in L40S L2",
            },
            "16_top2_vs_stock": {
                "active_flops_ratio": candidates[3]["active_expert_flops_per_sparse_layer"] / stock["active_expert_flops_per_sparse_layer"],
                "routed_weight_bytes_ratio": candidates[3]["routed_checkpoint_bytes"] / stock["routed_checkpoint_bytes"],
                "uniform_rows_per_nonempty_expert_ratio": candidates[3]["uniform"]["expected_rows_per_nonempty_expert"] / stock["uniform"]["expected_rows_per_nonempty_expert"],
            },
        },
        "trace_bound": {
            "source_paths": [str(path) for path in trace_paths],
            "min_fused_routed_marlin_share_of_summed_decode_kernel_time": min_moe_share,
            "min_moe_routing_sort_share_of_summed_decode_kernel_time": min_routing_share,
            "16_top2_ideal_half_fused_moe_plus_half_routing_ceiling": 0.5 * (min_moe_share + min_routing_share),
            "interpretation": "These are non-additive summed-kernel attribution shares, not endpoint wall-time shares. Even an impossible full transfer of half the routed Marlin and routing-sort work is below the economic wall-time gate. They cannot credit 16/top4, which preserves assignment FLOPs; only a target-GPU A/B can establish whether L2 locality or better grouped-M geometry transfers to wall time.",
        },
        "decision": {
            "nomination": "none",
            "reason": "16/top4 is the sole geometry with an L2-fit and 2.58x higher uniform nonempty-group M than stock while preserving top-4 capacity, but it preserves all routed assignment FLOPs and lacks DRAM/occupancy counters. 16/top2 halves FLOPs and raises M, yet its routed-work-only trace ceiling remains below the 9.955% wall-time gate. Neither supplies a conservative >=10% c16 cost path at zero-spend fidelity.",
            "minimal_future_measurement_if_reopened": "One matched L40S c16 stock versus 16-expert/top-4 merged-and-retrained proxy, retaining per-layer expert-M histogram, MoE kernel grid/block/register/shared/occupancy, L2 hit rate, DRAM bytes, and endpoint wall time. Promote only at >=594.46 tok/s with a quality/recovery gate; a lower DRAM byte count without wall-time gain closes this route.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
