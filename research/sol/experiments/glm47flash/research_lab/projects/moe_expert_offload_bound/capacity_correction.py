#!/usr/bin/env python3
"""Reconcile MoE cache capacity with the pinned vLLM MLA/A40 memory bands."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from offload_bound import BYTES_PER_GIB, exact_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((args.model_dir / "config.json").read_text())
    index, totals, experts, layers, routed_layers, expert_bytes = exact_model(args.model_dir)

    # These values are bound to a40_exact_memory_admission/a40_admission.py.
    kv_bytes_per_token = 47 * (config["kv_lora_rank"] + config["qk_rope_head_dim"]) * 2
    block_size = 16
    block_bytes = kv_bytes_per_token * block_size
    redundancy_bytes = 150 * 2**20
    expected_overhead_gib = 5.799453125
    conservative_overhead_gib = 10.0
    nonexpert_bytes = sum(v for k, v in totals.items() if k != "routed_experts")
    routed_bytes = totals["routed_experts"]
    total_experts = len(experts)
    rates = {"A40_$0.44_h": 0.44, "RTX_A6000_$0.49_h": 0.49, "RTX_6000_Ada_$0.77_h": 0.77}
    links = {"PCIe4x16_conservative": 24.0, "PCIe4x16_optimistic": 28.0}
    traffic = []
    for link, gbps in links.items():
        for device, hourly in rates.items():
            for gate in (0.6365, 0.60):
                target = hourly * 1_000_000 / (gate * 3600)
                required_hit = max(0.0, 1.0 - gbps * 1e9 / (target * len(routed_layers) * config["num_experts_per_tok"] * expert_bytes))
                traffic.append({"link": link, "device": device, "gate_usd_per_million": gate, "target_tok_s": target, "required_hit_rate": required_hit})

    rows = []
    for device_gib in (24, 32):
        budget = device_gib * 0.90 * BYTES_PER_GIB
        for concurrency in (1, 8, 16):
            live_tokens = concurrency * (8192 + 1024)
            kv_blocks = math.ceil(live_tokens / block_size)
            kv_bytes = kv_blocks * block_bytes
            bands = {}
            for band, overhead_gib in (("hard", 0.0), ("source_expected", expected_overhead_gib), ("conservative", conservative_overhead_gib)):
                cache_bytes = max(0, budget - nonexpert_bytes - kv_bytes - redundancy_bytes - overhead_gib * BYTES_PER_GIB)
                cache_bytes = min(routed_bytes, cache_bytes)
                slots = min(total_experts, math.floor(cache_bytes / expert_bytes))
                absent_bytes = routed_bytes - slots * expert_bytes
                hit = slots / total_experts
                bands[band] = {"cache_slots": slots, "cache_gib": cache_bytes / BYTES_PER_GIB, "absent_expert_gib": absent_bytes / BYTES_PER_GIB, "uniform_hit_rate": hit, "total_allocation_gib": (nonexpert_bytes + kv_bytes + redundancy_bytes + overhead_gib * BYTES_PER_GIB + cache_bytes) / BYTES_PER_GIB}
            rows.append({"device_gib": device_gib, "concurrency": concurrency, "budget_gib_90pct": budget / BYTES_PER_GIB, "live_tokens": live_tokens, "kv_blocks": kv_blocks, "kv_gib": kv_bytes / BYTES_PER_GIB, "bands": bands})

    full_miss_bytes = len(routed_layers) * config["num_experts_per_tok"] * expert_bytes
    for row in rows:
        for band in row["bands"].values():
            absent_fraction = 1 - band["uniform_hit_rate"]
            band["decode_full_miss_bytes_per_token"] = full_miss_bytes
            band["decode_transfer_bytes_per_token_uniform"] = full_miss_bytes * absent_fraction
            band["pcie_no_overlap_tok_s_at_24GBps"] = 24e9 / max(1, band["decode_transfer_bytes_per_token_uniform"])
            band["pcie_no_overlap_tok_s_at_28GBps"] = 28e9 / max(1, band["decode_transfer_bytes_per_token_uniform"])

    economic = []
    for row in rows:
        for band_name, band in row["bands"].items():
            for link, gbps in links.items():
                pcie_capacity = gbps * 1e9 / band["decode_transfer_bytes_per_token_uniform"] if band["decode_transfer_bytes_per_token_uniform"] else float("inf")
                for device, hourly in rates.items():
                    for gate in (0.6365, 0.60):
                        target = hourly * 1_000_000 / (gate * 3600)
                        economic.append({"device_gib": row["device_gib"], "concurrency": row["concurrency"], "band": band_name, "link": link, "device": device, "gate_usd_per_million": gate, "target_tok_s": target, "pcie_no_overlap_capacity_tok_s": pcie_capacity, "pcie_bound_clears_target": pcie_capacity >= target})
    result = {"schema_version": 2, "claim_scope": "corrected offline capacity/PCIe bound; no GPU, provider, quality, or throughput measurement", "quality_invariance": "exact weights, routing, and top-k are unchanged; only expert residency is varied", "inputs": {"index_total_bytes": index["metadata"]["total_size"], "nonexpert_bytes": nonexpert_bytes, "routed_expert_bytes": routed_bytes, "expert_count": total_experts, "expert_bytes": expert_bytes, "routed_layers": routed_layers, "top_k": config["num_experts_per_tok"], "kv_bytes_per_token": kv_bytes_per_token, "kv_block_bytes": block_bytes, "allocation_fraction": 0.90, "redundancy_mib": 150, "source_expected_overhead_gib": expected_overhead_gib, "conservative_overhead_gib": conservative_overhead_gib, "campaign_rates_usd_per_hour": rates, "pcie_gbps": links}, "capacity": rows, "traffic_gates": traffic, "economic_comparison": economic, "prefill": {"tokens_per_request": 8192, "uniform_unique_experts_per_layer": 64, "empty_cache_transfer_gib": routed_bytes / BYTES_PER_GIB, "note": "At 8,192 tokens and top-4 uniform routing, all 64 experts/layer are touched; repeated prefill requests refill any absent set."}, "decision": {"24GiB_c1": "hard_fit_only; expected/conservative overhead bands do not fit all experts", "24GiB_c8": "offload_required; conservative hit rate is below PCIe economic gates", "32GiB_c8": "offload_required under conservative band; hit rate remains below gates", "32GiB_c16": "offload_required under conservative band; hit rate remains below gates", "prototype": "close: no existing GLM-4.7 validated expert-cache implementation clears the conservative gate with >=5% economic margin"}}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "capacity": result["capacity"], "decision": result["decision"]}, indent=2))


if __name__ == "__main__":
    main()
