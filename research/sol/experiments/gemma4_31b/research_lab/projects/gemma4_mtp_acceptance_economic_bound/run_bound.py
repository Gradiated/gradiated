#!/usr/bin/env python3
"""Deterministic, no-GPU economic bound for Gemma 4 native MTP."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADJ = ROOT.parent / "exact_geometry_runtime_opportunities"
MARKET = ROOT.parent / "exact_market_venue_decision_surface"
PRICES = Path(__file__).resolve().parents[7] / "research" / "factory" / "data" / "gpu_prices.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def threshold(whole_gain: float, decode_fraction: float, assistant_ratio: float, overhead: float) -> float | None:
    """Mean accepted draft tokens required; one verify pass yields 1+a tokens."""
    if whole_gain >= decode_fraction:
        return None
    return (1.0 + assistant_ratio + overhead) / (1.0 - whole_gain / decode_fraction) - 1.0


def ratio(accepted: float, decode_fraction: float, assistant_ratio: float, overhead: float) -> float:
    return (1.0 - decode_fraction) + decode_fraction * (1.0 + assistant_ratio + overhead) / (1.0 + accepted)


def main() -> None:
    geometry = json.loads((ADJ / "GEOMETRY.json").read_text())
    packet = json.loads((ADJ / "ADJACENT_ARM_PACKET.json").read_text())
    market = json.loads((MARKET / "MARKET_TARGET.json").read_text())
    prices = json.loads(PRICES.read_text())
    mix = market["campaign_mix"]
    retail = min(v["request_cost"] for v in market["campaign_mix_normalization_usd"].values() if isinstance(v, dict) and "request_cost" in v)
    # Same conservative utilization/headroom factors used by the completed L40S gate.
    factors = 1.10 * 1.05 * 1.03 * 1.03 / 0.85
    accelerator = {row["id"]: row for row in prices["accelerators"]}
    h100_rate = accelerator["nvidia-h100-sxm"]["production_planning_usd_per_gpu_hour"]
    l40s_rate = accelerator["nvidia-l40s"]["production_planning_usd_per_gpu_hour"]
    market_required_rps = {"h100_bf16": h100_rate * factors / (3600.0 * retail), "w4_l40s": l40s_rate * factors / (3600.0 * retail)}

    # Assistant compute is deliberately swept broadly.  0.02 is optimistic for four 1,024-wide
    # layers; 0.10 includes routing/launch tax.  Verification is one target pass per proposal.
    decode_fractions = [0.25, 0.50, 0.75]
    assistant_ratios = [0.02, 0.05, 0.10]
    overheads = [0.00, 0.05, 0.10, 0.20]
    gains = {"five_percent": 0.05, "ten_percent": 0.10}
    surfaces = []
    for hw in ("h100_bf16", "w4_l40s"):
        rows = []
        for f in decode_fractions:
            for ar in assistant_ratios:
                for oh in overheads:
                    row = {"decode_fraction": f, "assistant_to_target_verify_cost": ar, "proposer_verification_overhead": oh}
                    row["min_accepted_for_5pct"] = {k: threshold(v, f, ar, oh) for k, v in gains.items()}
                    row["one_token_upper_bound_gain"] = 1.0 - ratio(1.0, f, ar, oh)
                    rows.append(row)
        surfaces.append({"hardware": hw, "rows": rows})

    # Market threshold is conditional on a valid stock throughput; no unmeasured H100 result is invented.
    market_rows = []
    for hw, required in market_required_rps.items():
        for stock_rps in ([0.75, 1.0, 1.5, 1.8] if hw == "h100_bf16" else [0.40, 0.50, 0.60, 0.70]):
            required_gain = max(0.0, 1.0 - stock_rps / required)
            market_rows.append({"hardware": hw, "stock_completed_requests_per_second": stock_rps, "market_required_rps": required, "required_all_in_gain": required_gain, "min_accepted_at_f05_ar002_oh005": threshold(required_gain, 0.50, 0.02, 0.05)})

    # Residency is a capacity warning, not a throughput claim.  Assistant bytes are counted once per replica.
    assistant_gib = geometry["assistant_geometry_measured_from_config"]["weight_bytes"] / 2**30
    kv_gib = geometry["derived_geometry"]["primary_resident_kv_gib"]
    capacity = {"assistant_weight_gib": assistant_gib, "primary_target_kv_gib_per_request": kv_gib, "w4_l40s": {"c16": 31.158 + assistant_gib, "c32": 36.973 + assistant_gib}, "h100_bf16": {"c16_target_plus_assistant_approx": 58.256 + assistant_gib + 16 * kv_gib, "c32_target_plus_assistant_approx": 58.256 + assistant_gib + 32 * kv_gib}}

    output = {
        "schema_version": 1,
        "status": "matched_arm_candidate_with_hard_negative_gate",
        "evidence_type": "derived_and_synthetic; no provider/CUDA/quality execution",
        "question": "Can native four-layer Gemma 4 MTP clear 5% sustainable cost on 4214/358 background traffic?",
        "identities": packet["identities"],
        "inputs": {"prompt_tokens": mix["prompt_tokens"], "output_tokens": mix["output_tokens"], "cache_prompt_fraction": mix["prompt_cache_fraction"], "fresh_prompt_tokens": mix["fresh_prompt_tokens"], "assistant_weight_gib": assistant_gib, "target_bf16_weight_gib": geometry["target_text_geometry_measured_from_config"]["bf16_weight_gib_metadata"], "input_sha256": {"adjacent_packet": sha256(ADJ / "ADJACENT_ARM_PACKET.json"), "geometry": sha256(ADJ / "GEOMETRY.json"), "market": sha256(MARKET / "MARKET_TARGET.json"), "prices": sha256(PRICES)}},
        "model": {"baseline_target_calls": 358, "mtp_formula": "draft_calls=verify_calls=ceil(output_tokens/(1+accepted_tokens)); each proposal pays one target verification pass plus assistant work; rejected tokens are represented by accepted_tokens=0..1", "quality_policy": "exact-greedy output IDs must match stock; sampled operation remains a separate quality/acceptance measurement", "target_verification_not_elided": True},
        "economic_surface": surfaces,
        "market_break_even": {"retail_request_cost_usd": retail, "overhead_factor": factors, "required_completed_requests_per_second": market_required_rps, "conditional_rows": market_rows},
        "capacity": capacity,
        "async_fallback": {"status": "comparison_only", "extra_weight_gib": 0.0, "quality_risk": "none expected but output IDs and failures must be matched", "promotion_gate": "matched c8/c16 completed-request cost or throughput gain >=5%; otherwise no MTP retention"},
        "matched_arm": {"name": "native_mtp_num_speculative_tokens_1", "scope": "one later matched arm only", "telemetry": ["accepted_tokens", "draft_calls", "verify_calls", "output_ids", "complete_requests", "prefill_wall_s", "decode_wall_s", "request_wall_s", "HBM_GiB", "power_W"], "gate": "run only with exact target/assistant/runtime/image identities; exact-greedy output IDs equal stock; complete requests >=30 per arm; mean accepted_tokens >= threshold for measured decode fraction and overhead; all-in cost reduction >=5%", "hard_negative": "typed none if mean accepted_tokens < threshold, output IDs differ, any nested/empty result, or MTP all-in cost reduction <5%; do not claim 10% or market break-even from this bound"},
    }
    (ROOT / "MTP_BOUND.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"], "artifact": str(ROOT / "MTP_BOUND.json"), "market_required_rps": market_required_rps, "assistant_weight_gib": assistant_gib}, indent=2))


if __name__ == "__main__":
    main()
