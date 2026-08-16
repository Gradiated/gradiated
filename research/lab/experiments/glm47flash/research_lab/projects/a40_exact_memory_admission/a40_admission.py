#!/usr/bin/env python3
"""Deterministic A40 capacity and physical-floor calculation for GLM-4.7 Flash."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path


GIB = 1 << 30
MIB = 1 << 20


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safetensor_headers(root: Path, weight_map: dict[str, str]) -> dict[str, dict]:
    headers: dict[str, dict] = {}
    for shard in sorted(set(weight_map.values())):
        path = root / shard
        with path.open("rb") as handle:
            header_len = struct.unpack("<Q", handle.read(8))[0]
            headers.update(json.loads(handle.read(header_len)))
    return {name: headers[name] for name in weight_map}


def tensor_bytes(header: dict) -> int:
    start, end = header["data_offsets"]
    return end - start


def gib(value: float) -> float:
    return value / GIB


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vllm-tarball", type=Path, required=True)
    args = parser.parse_args()

    root = args.model_root
    config_path = root / "config.json"
    index_path = root / "model.safetensors.index.json"
    manifest_path = root / "model-files-manifest.json"
    config = json.loads(config_path.read_text())
    index = json.loads(index_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    weight_map = index["weight_map"]
    headers = safetensor_headers(root, weight_map)

    family_bytes: dict[str, int] = defaultdict(int)
    sparse_expert_bytes: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for name, header in headers.items():
        nbytes = tensor_bytes(header)
        if ".mlp.experts." in name:
            pieces = name.split(".")
            layer = int(pieces[2])
            expert = int(pieces[5])
            sparse_expert_bytes[layer][expert] += nbytes
            family_bytes["routed_experts"] += nbytes
        elif ".mlp.shared_experts." in name:
            family_bytes["shared_experts"] += nbytes
        elif ".self_attn." in name:
            family_bytes["attention"] += nbytes
        elif ".mlp." in name:
            family_bytes["dense_mlp_and_router"] += nbytes
        elif name.startswith("model.embed_tokens") or name.startswith("lm_head"):
            family_bytes["embedding_and_lm_head"] += nbytes
        else:
            family_bytes["norms_and_other"] += nbytes

    payload_bytes = sum(tensor_bytes(header) for header in headers.values())
    nonexpert_bytes = payload_bytes - family_bytes["routed_experts"]
    active_expert_min = sum(sum(sorted(experts.values())[: config["num_experts_per_tok"]]) for experts in sparse_expert_bytes.values())
    active_expert_max = sum(sum(sorted(experts.values(), reverse=True)[: config["num_experts_per_tok"]]) for experts in sparse_expert_bytes.values())
    active_weight_bytes_min = nonexpert_bytes + active_expert_min
    active_weight_bytes_max = nonexpert_bytes + active_expert_max

    layers = config["num_hidden_layers"]
    kv_width = config["kv_lora_rank"] + config["qk_rope_head_dim"]
    bytes_per_token = layers * kv_width * 2
    block_size = 16
    bytes_per_block = bytes_per_token * block_size
    budget = int(48 * GIB * 0.90)
    historical_model_gib = 17.87
    historical_kv_gib = 16.82
    historical_requested_gib = (46068 * MIB * 0.90) / GIB
    historical_non_kv_gib = historical_requested_gib - historical_model_gib - historical_kv_gib
    redundancy_gib = 150 / 1024
    conservative_non_kv_gib = 10.0

    rows = []
    for concurrency in (1, 8, 16, 32):
        tokens = concurrency * (8192 + 1024)
        blocks = math.ceil(tokens / block_size)
        kv = blocks * bytes_per_block
        hard = payload_bytes + kv
        expected = historical_model_gib * GIB + historical_non_kv_gib * GIB + kv + redundancy_gib * GIB
        conservative = manifest["weight_bytes"] + conservative_non_kv_gib * GIB + kv + redundancy_gib * GIB
        conservative_headroom = budget - conservative
        if concurrency <= 16 and conservative_headroom >= 4 * GIB:
            classification = "safely_admissible"
        elif hard > budget:
            classification = "impossible"
        else:
            classification = "exact_load_required"
        rows.append(
            {
                "concurrency": concurrency,
                "live_tokens": tokens,
                "kv_blocks_16_tokens": blocks,
                "kv_gib": gib(kv),
                "hard_lower_gib": gib(hard),
                "source_derived_expected_gib": gib(expected),
                "conservative_upper_gib": gib(conservative),
                "conservative_headroom_gib": gib(conservative_headroom),
                "classification": classification,
            }
        )

    rate_rows = []
    listed_hourly = 0.3475
    for overhead, transfer_seconds in ((0.10, 0), (0.20, 0), (0.10, 97)):
        for target in (0.6365, 0.60):
            rate = (listed_hourly * (1 + overhead) * 1_000_000 / target) / 3600
            transfer_amortized_1000h = transfer_seconds / (1000 * 3600)
            rate_rows.append(
                {
                    "lifecycle_overhead_fraction": overhead,
                    "measured_setup_seconds_per_recovery": transfer_seconds,
                    "target_usd_per_million_output": target,
                    "required_output_tokens_per_second": rate,
                    "setup_time_fraction_if_1000h_productive": transfer_amortized_1000h,
                }
            )

    required_rate = max(x["required_output_tokens_per_second"] for x in rate_rows if x["target_usd_per_million_output"] == 0.60 and x["lifecycle_overhead_fraction"] == 0.10)
    # This deliberately counts only the minimum selected routed-expert tensors.
    c8_ideal_reuse_bytes = active_weight_bytes_min / 8
    c8_expert_diverse_bytes = nonexpert_bytes / 8 + active_expert_max
    c8_no_reuse_bytes = active_weight_bytes_min
    dense_hidden = config["hidden_size"]
    expert_hidden = config["moe_intermediate_size"]
    attention_params = (dense_hidden * config["q_lora_rank"] + config["q_lora_rank"] * config["num_attention_heads"] * config["qk_head_dim"] + dense_hidden * kv_width + config["kv_lora_rank"] * config["num_attention_heads"] * (config["qk_nope_head_dim"] + config["v_head_dim"]) + config["num_attention_heads"] * config["v_head_dim"] * dense_hidden)
    dense_mlp_params = 3 * dense_hidden * config["intermediate_size"]
    sparse_layer_params = attention_params + 3 * dense_hidden * expert_hidden * (config["num_experts_per_tok"] + config["n_shared_experts"])
    active_params = (2 * config["vocab_size"] * dense_hidden) + attention_params + dense_mlp_params + (layers - 1) * sparse_layer_params
    compute_floor_tflops = 2 * active_params * required_rate / 1e12

    result = {
        "schema_version": 1,
        "claim_scope": "offline capacity and physical lower-bound only; no A40 load, provider action, quality, or throughput measurement",
        "inputs": {
            "checkpoint_revision": manifest["revision"],
            "config_sha256": sha256(config_path),
            "index_sha256": sha256(index_path),
            "manifest_sha256": sha256(manifest_path),
            "vllm_0_15_0_source_tarball_sha256": sha256(args.vllm_tarball),
            "vllm_source_lines": [
                "vllm/attention/layer.py:532 sets MLA cache head_size=kv_lora_rank+qk_rope_head_dim",
                "vllm/v1/kv_cache_interface.py:196-206 sizes MLA pages as block_size*num_kv_heads*head_size*dtype_bytes",
                "vllm/v1/worker/gpu_worker.py:318-341 profiles non-KV use and allocates requested_memory-non_kv_cache_memory",
                "vllm/v1/worker/gpu_worker.py:467-505 reports 150 MiB redundancy buffer and non-KV terms",
            ],
            "a40_vendor_datasheet": "https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/a40/proviz-print-nvidia-a40-datasheet-us-nvidia-1469711-r8-web.pdf",
        },
        "checkpoint_tensor_payload": {
            "tensor_count": len(headers),
            "payload_bytes": payload_bytes,
            "index_total_size_bytes": index["metadata"]["total_size"],
            "manifest_weight_bytes": manifest["weight_bytes"],
            "family_bytes": dict(sorted(family_bytes.items())),
            "routed_layers": len(sparse_expert_bytes),
            "active_routed_expert_bytes_min": active_expert_min,
            "active_routed_expert_bytes_max": active_expert_max,
        },
        "kv_geometry": {
            "layers": layers,
            "kv_lora_rank": config["kv_lora_rank"],
            "qk_rope_head_dim": config["qk_rope_head_dim"],
            "mla_cache_width": kv_width,
            "bf16_bytes_per_element": 2,
            "bytes_per_token": bytes_per_token,
            "block_size_tokens": block_size,
            "bytes_per_block": bytes_per_block,
        },
        "allocation_bands": {
            "a40_total_gib_vendor": 48,
            "gpu_memory_utilization": 0.90,
            "requested_budget_gib": gib(budget),
            "historical_l40s_calibration": {
                "model_loading_gib": historical_model_gib,
                "available_kv_gib": historical_kv_gib,
                "requested_budget_gib": historical_requested_gib,
                "inferred_non_kv_gib": historical_non_kv_gib,
                "interpretation": "calibration only; differs in GPU/driver and is not performance-transferable",
            },
            "conservative_non_kv_gib": conservative_non_kv_gib,
            "redundancy_buffer_gib": redundancy_gib,
            "rows": rows,
        },
        "economics": {
            "tensordock_listed_hourly_usd": listed_hourly,
            "tensordock_all_in_hourly_usd_at_10pct_lifecycle": 0.38225,
            "measured_model_identity_setup_seconds": 97,
            "rate_sensitivity": rate_rows,
        },
        "physical_lower_bounds": {
            "active_weight_bytes_min_single_token": active_weight_bytes_min,
            "active_weight_bytes_max_single_token": active_weight_bytes_max,
            "required_rate_for_0_60_at_10pct_overhead": required_rate,
            "a40_vendor_hbm_gbs": 696,
            "a40_vendor_bf16_tensor_tflops": 149.7,
            "c8_weight_traffic_scenarios": {
                "ideal_all_weight_reuse_per_output_token_bytes": c8_ideal_reuse_bytes,
                "expert_diverse_per_output_token_bytes": c8_expert_diverse_bytes,
                "no_cross_request_reuse_per_output_token_bytes": c8_no_reuse_bytes,
                "ideal_hbm_gbs_at_required_rate": c8_ideal_reuse_bytes * required_rate / 1e9,
                "expert_diverse_hbm_gbs_at_required_rate": c8_expert_diverse_bytes * required_rate / 1e9,
                "no_reuse_hbm_gbs_at_required_rate": c8_no_reuse_bytes * required_rate / 1e9,
                "interpretation": "ideal reuse is the physical lower bound; expert-diverse and no-reuse values are traffic stress cases, not lower bounds",
            },
            "active_parameter_floor": active_params,
            "compute_floor_tflops_bf16_fma_counting": compute_floor_tflops,
            "compute_floor_fraction_of_a40_bf16_tensor_peak": compute_floor_tflops / 149.7,
        },
        "decision": {
            "c8": "admit: conservative headroom exceeds 4 GiB",
            "c16": "admit: conservative headroom exceeds 4 GiB",
            "c32": "exact_load_required: plausible in hard/expected bands but not conservative band",
            "a40": "retain one later exact-load measurement contingent on authenticated TensorDock account/funding and delete/direct-lookup authority",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
