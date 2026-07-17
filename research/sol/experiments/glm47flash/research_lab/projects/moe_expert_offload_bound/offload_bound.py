#!/usr/bin/env python3
"""Zero-cost, exact-header residency and PCIe bound for GLM-4.7-Flash AWQ."""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
from collections import Counter
from pathlib import Path

BYTES_PER_GIB = 2**30
EXPERT_RE = re.compile(r"\.mlp\.experts\.\d+\.")
LAYER_RE = re.compile(r"model\.layers\.(\d+)")


def read_headers(model_dir: Path):
    index = json.loads((model_dir / "model.safetensors.index.json").read_text())
    tensors = []
    for shard in sorted(set(index["weight_map"].values())):
        with (model_dir / shard).open("rb") as f:
            header_len = struct.unpack("<Q", f.read(8))[0]
            header = json.loads(f.read(header_len))
        for name, value in header.items():
            if name != "__metadata__":
                tensors.append({"name": name, "bytes": value["data_offsets"][1] - value["data_offsets"][0], "dtype": value["dtype"], "shape": value["shape"]})
    return index, tensors


def category(name: str) -> str:
    if EXPERT_RE.search(name):
        return "routed_experts"
    if ".mlp.shared_experts." in name:
        return "shared_experts"
    if ".self_attn." in name:
        return "attention"
    if ".mlp." in name:
        return "mlp_router_and_dense"
    if "embed_tokens" in name or name == "lm_head.weight":
        return "embedding_head"
    return "norm_and_other"


def exact_model(model_dir: Path):
    index, tensors = read_headers(model_dir)
    totals = Counter()
    experts = Counter()
    layers = Counter()
    for tensor in tensors:
        cat = category(tensor["name"])
        totals[cat] += tensor["bytes"]
        match = LAYER_RE.search(tensor["name"])
        if match:
            layers[int(match.group(1))] += tensor["bytes"]
        expert = re.search(r"model\.layers\.(\d+)\.mlp\.experts\.(\d+)", tensor["name"])
        if expert:
            experts[(int(expert.group(1)), int(expert.group(2)))] += tensor["bytes"]
    unique_expert_sizes = sorted(set(experts.values()))
    assert len(unique_expert_sizes) == 1, unique_expert_sizes
    routed_layers = sorted({layer for layer, _ in experts})
    per_expert = unique_expert_sizes[0]
    return index, totals, experts, layers, routed_layers, per_expert


def fmt_gib(n: float) -> float:
    return round(n / BYTES_PER_GIB, 6)


def run(model_dir: Path):
    config = json.loads((model_dir / "config.json").read_text())
    index, totals, experts, layers, routed_layers, expert_bytes = exact_model(model_dir)
    routed_expert_count = len(experts)
    top_k = config["num_experts_per_tok"]
    n_routed = config["n_routed_experts"]
    kv_bytes_per_token = 2048  # conservative BF16 MLA latent+rotary/value envelope
    runtime_reserve_gib = 4.0
    devices = {"24GiB": 24.0, "32GiB": 32.0}
    static_bytes = sum(v for k, v in totals.items() if k != "routed_experts")
    rows = []
    for device, capacity in devices.items():
        for context in (1, 8):
            # c1/c8 means 8,192 input tokens times concurrent requests.
            kv = 8192 * context * kv_bytes_per_token
            available = capacity * BYTES_PER_GIB - static_bytes - kv - runtime_reserve_gib * BYTES_PER_GIB
            slots = max(0, math.floor(available / expert_bytes))
            hit_uniform = min(1.0, slots / (len(routed_layers) * n_routed))
            rows.append({"device": device, "concurrency": context, "kv_bytes": kv, "gpu_cache_slots": slots, "uniform_expert_hit_rate": hit_uniform, "all_experts_fit": slots >= routed_expert_count})

    # Each decode token activates top_k distinct routed experts in every routed layer.
    invocations = len(routed_layers) * top_k
    miss_bytes_token = invocations * expert_bytes
    pcie_gbps = {"PCIe4x16_conservative": 24.0, "PCIe4x16_optimistic": 28.0}
    rates = {"A40_$0.44_h": 0.44, "RTX_A6000_$0.49_h": 0.49, "A40_target_$0.60": 0.44, "RTX_A6000_target_$0.60": 0.49}
    targets = {"A40_$0.44_h": {"0.6365": 192.022, "0.60": 233.333}, "RTX_A6000_$0.49_h": {"0.6365": 213.843, "0.60": 233.333}}
    traffic = []
    for link, gbps in pcie_gbps.items():
        for name, target_set in targets.items():
            for gate, tok_s in target_set.items():
                required_hit = max(0.0, 1.0 - gbps * 1e9 / (tok_s * miss_bytes_token))
                traffic.append({"link": link, "device_rate": name, "gate_usd_per_million": float(gate), "target_tok_s": tok_s, "decode_miss_bytes_per_token": miss_bytes_token, "required_hit_rate": required_hit, "no_overlap_max_tok_s": gbps * 1e9 / miss_bytes_token})
    # Stable locality is represented as a hot-set fraction; this is a policy bound, not measured routing.
    locality = []
    for hot_fraction in (0.90, 0.95, 0.99, 1.0):
        hot_experts = math.ceil(routed_expert_count * hot_fraction)
        locality.append({"hot_set_fraction": hot_fraction, "hot_expert_slots": hot_experts, "hot_set_gib": fmt_gib(hot_experts * expert_bytes), "decode_hit_rate_if_cached": hot_fraction, "decode_transfer_gib_per_token": (1 - hot_fraction) * miss_bytes_token / BYTES_PER_GIB})
    prefill_unique = n_routed * (1 - (1 - 1 / n_routed) ** (top_k * 8192))
    output = {"evidence_class": "derived_exact_header_and_analytical", "quality_invariance": "weights, routing, and top-k unchanged; only residency changes", "inputs": {"model_dir": str(model_dir), "index_total_bytes": index["metadata"]["total_size"], "config": {k: config[k] for k in ("n_routed_experts", "n_shared_experts", "num_experts_per_tok", "hidden_size", "moe_intermediate_size")}, "routed_layers": routed_layers, "routed_expert_count": routed_expert_count, "expert_bytes": expert_bytes, "kv_bytes_per_token_conservative": kv_bytes_per_token, "runtime_reserve_gib": runtime_reserve_gib, "pcie_assumptions_gbps": pcie_gbps}, "weight_bytes": {k: {"bytes": v, "gib": fmt_gib(v)} for k, v in totals.items()}, "residency": rows, "traffic": traffic, "locality": locality, "prefill": {"tokens": 8192, "expected_unique_experts_per_layer_uniform": prefill_unique, "expected_transfer_gib_if_empty_cache": fmt_gib(prefill_unique * len(routed_layers) * expert_bytes)}, "reuse": {"per_expert_probability_per_token_uniform": top_k / n_routed, "mean_tokens_to_reuse_uniform": n_routed / top_k}, "host": {"full_routed_expert_pinned_ram_gib": fmt_gib(totals["routed_experts"]), "full_model_pinned_ram_gib": fmt_gib(index["metadata"]["total_size"]), "double_buffer_miss_gib": fmt_gib(2 * n_routed * expert_bytes)}, "runtime_support": {"path": "vLLM cpu_offload_gb plus proposed MoE expert cache RFC/PR", "status": "generic CPU offload exists; expert cache is proposed/current-source work, not GLM-4.7 validated", "source_urls": ["https://github.com/vllm-project/vllm/issues/33869", "https://github.com/vllm-project/vllm/issues/38256", "https://github.com/vllm-project/vllm/blob/main/vllm/entrypoints/llm.py"]}}
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.model_dir)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "weight_bytes": result["weight_bytes"], "residency": result["residency"], "traffic_sample": result["traffic"][:2]}, indent=2))
