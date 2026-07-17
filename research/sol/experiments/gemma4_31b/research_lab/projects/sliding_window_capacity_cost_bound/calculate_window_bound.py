#!/usr/bin/env python3
"""Deterministic Gemma 4 local-window capacity and attention-work bound."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parent.parent
GEOMETRY = LAB / "projects/exact_geometry_runtime_opportunities/GEOMETRY.json"
MEMORY = LAB / "projects/fp8_l40s_fit_economic_falsifier/MEMORY_ACCOUNTING.json"
FP8_ARM = LAB / "projects/fp8_kv_c8_retained_arm/FP8_KV_ARM.json"
SOURCE = LAB / "projects/prefix_cache_primary_mix_bound/source_snapshot/vllm__v1__core__kv_cache_utils.py"
GiB = 1024**3

PROMPT, OUTPUT, TEN_K = 4214, 358, 10_000
CONCURRENCIES = (1, 4, 8, 16)
WINDOWS = (1024, 768, 512, 256)
HIDDEN, VOCAB = 5376, 262144
LOCAL_LAYERS, GLOBAL_LAYERS = 50, 10
LOCAL_HEADS, LOCAL_DIM, LOCAL_KV_HEADS = 32, 256, 16
GLOBAL_HEADS, GLOBAL_DIM, GLOBAL_KV_HEADS = 32, 512, 4


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gib(value: int | float) -> float:
    return value / GiB


def capped_sum(start: int, count: int, cap: int) -> int:
    """sum(min(t, cap) for t in range(start, start + count))."""
    end = start + count - 1
    below_end = min(end, cap)
    below = max(0, below_end * (below_end + 1) // 2 - (start - 1) * start // 2)
    above = max(0, end - max(start - 1, cap)) * cap
    return below + above


def attention_work(tokens_start: int, token_count: int, cap: int, heads: int, dim: int) -> dict:
    positions = capped_sum(tokens_start, token_count, cap)
    # QK and AV are each one FMA per score: 2 FLOPs each, hence 4 FLOPs/score.
    return {
        "attended_token_pairs_per_head": positions,
        "qk_av_flops": 4 * heads * dim * positions,
        # One BF16 score output for QK and one BF16 coefficient read for AV.
        # FlashAttention may avoid materializing this; this is a logical lower-bound
        # state movement, not an allocation or a bandwidth measurement.
        "qk_av_coefficient_bytes_bf16": 4 * heads * positions,
    }


def kv_bytes(tokens: int, window: int, value_bytes: int, scale_bytes_per_kv_head: int) -> dict:
    # The authoritative GEOMETRY packet fixes BF16 K+V payload at 8,192 bytes
    # per token/layer for both types. Preserve that packet rather than infer a
    # different layout from head metadata. FP8 changes only the scalar payload
    # from two bytes to one; its source-specified scales are added separately.
    local_per_token = 8192 * value_bytes // 2 + 2 * LOCAL_KV_HEADS * scale_bytes_per_kv_head
    global_per_token = 8192 * value_bytes // 2 + 2 * GLOBAL_KV_HEADS * scale_bytes_per_kv_head
    local = LOCAL_LAYERS * min(tokens, window) * local_per_token
    global_ = GLOBAL_LAYERS * tokens * global_per_token
    return {
        "local_bytes": local,
        "global_bytes": global_, "total_bytes": local + global_,
        "local_bytes_per_token_per_layer": local_per_token,
        "global_bytes_per_token_per_layer": global_per_token,
    }


def main() -> None:
    geometry = json.loads(GEOMETRY.read_text())
    memory = json.loads(MEMORY.read_text())
    fp8_arm = json.loads(FP8_ARM.read_text())
    bound_base_gib = memory["steady_state_bound"]["weights_and_scales_gib_conservative"] + memory["steady_state_bound"]["runtime_reservation_gib"]
    envelope_gib = memory["steady_state_bound"]["l40s_capacity_gib_assumed"]

    local_projection = 2 * HIDDEN * (LOCAL_HEADS * LOCAL_DIM + 2 * LOCAL_KV_HEADS * LOCAL_DIM + LOCAL_HEADS * LOCAL_DIM)
    global_projection = 2 * HIDDEN * (GLOBAL_HEADS * GLOBAL_DIM + 2 * GLOBAL_KV_HEADS * GLOBAL_DIM + GLOBAL_HEADS * GLOBAL_DIM)
    projection_per_token = LOCAL_LAYERS * local_projection + GLOBAL_LAYERS * global_projection
    mlp_per_token = 2 * LOCAL_LAYERS * 0  # makes the expression below visibly independent of window
    mlp_per_token = 2 * 60 * 3 * HIDDEN * 21504
    linear_per_token = projection_per_token + mlp_per_token
    vocab_per_sample = 2 * HIDDEN * VOCAB

    rows = []
    for window in WINDOWS:
        primary_input_bf16 = kv_bytes(PROMPT, window, 2, 0)
        primary_peak_bf16 = kv_bytes(PROMPT + OUTPUT, window, 2, 0)
        tenk_bf16 = kv_bytes(TEN_K, window, 2, 0)
        # Pinned FP8-per-token-head contract: one byte/value plus one 4-byte
        # scale per K and V token-head (not per scalar).
        primary_input_fp8 = kv_bytes(PROMPT, window, 1, 4)
        primary_peak_fp8 = kv_bytes(PROMPT + OUTPUT, window, 1, 4)
        tenk_fp8 = kv_bytes(TEN_K, window, 1, 4)

        residency = {}
        for label, item in (("primary_input_4214", primary_input_bf16), ("primary_peak_4572", primary_peak_bf16), ("aa_10k", tenk_bf16)):
            residency[label] = {"bf16": {}, "fp8_per_token_head": {}}
            fp8_item = {"primary_input_4214": primary_input_fp8, "primary_peak_4572": primary_peak_fp8, "aa_10k": tenk_fp8}[label]
            for c in CONCURRENCIES:
                for dtype, source in (("bf16", item), ("fp8_per_token_head", fp8_item)):
                    total = bound_base_gib + gib(c * source["total_bytes"])
                    residency[label][dtype][str(c)] = {
                        "kv_gib": gib(c * source["total_bytes"]), "total_conservative_gib": total,
                        "headroom_gib": envelope_gib - total, "fits_envelope": total <= envelope_gib,
                    }

        local_prefill = attention_work(1, PROMPT, window, LOCAL_HEADS, LOCAL_DIM)
        global_prefill = attention_work(1, PROMPT, PROMPT, GLOBAL_HEADS, GLOBAL_DIM)
        local_decode = attention_work(PROMPT + 1, OUTPUT, window, LOCAL_HEADS, LOCAL_DIM)
        global_decode = attention_work(PROMPT + 1, OUTPUT, PROMPT + OUTPUT, GLOBAL_HEADS, GLOBAL_DIM)
        control_local_prefill = attention_work(1, PROMPT, 1024, LOCAL_HEADS, LOCAL_DIM)
        control_local_decode = attention_work(PROMPT + 1, OUTPUT, 1024, LOCAL_HEADS, LOCAL_DIM)
        qkav = {
            "prefill": {"local": local_prefill, "global": global_prefill},
            "decode": {"local": local_decode, "global": global_decode},
        }
        candidate_qkav = LOCAL_LAYERS * (local_prefill["qk_av_flops"] + local_decode["qk_av_flops"]) + GLOBAL_LAYERS * (global_prefill["qk_av_flops"] + global_decode["qk_av_flops"])
        control_qkav = LOCAL_LAYERS * (control_local_prefill["qk_av_flops"] + control_local_decode["qk_av_flops"]) + GLOBAL_LAYERS * (global_prefill["qk_av_flops"] + global_decode["qk_av_flops"])
        denominator = linear_per_token * (PROMPT + OUTPUT) + vocab_per_sample * (1 + OUTPUT) + control_qkav
        saved = control_qkav - candidate_qkav
        rows.append({
            "window_tokens": window,
            "kv_per_request": {
                "primary_input_4214": {k: gib(v) if k.endswith("bytes") else v for k, v in primary_input_bf16.items()},
                "primary_peak_4572": {k: gib(v) if k.endswith("bytes") else v for k, v in primary_peak_bf16.items()},
                "aa_10k": {k: gib(v) if k.endswith("bytes") else v for k, v in tenk_bf16.items()},
                "fp8_primary_input_4214_gib": gib(primary_input_fp8["total_bytes"]),
            },
            "residency": residency, "qk_av": qkav,
            "whole_request_flop_denominator": {"linear_projection_and_mlp_flops": linear_per_token * (PROMPT + OUTPUT), "vocab_sampling_flops": vocab_per_sample * (1 + OUTPUT), "control_qk_av_flops": control_qkav, "total_flops": denominator},
            "saved_qk_av_flops_vs_1024": saved,
            "maximum_end_to_end_effect_fraction": saved / denominator,
            "maximum_end_to_end_effect_percent": 100 * saved / denominator,
            "capacity_discontinuity": {
                "bf16_primary_input_c8_crosses": residency["primary_input_4214"]["bf16"]["8"]["fits_envelope"] and not rows[0]["residency"]["primary_input_4214"]["bf16"]["8"]["fits_envelope"] if rows else False,
                "bf16_primary_peak_c8_fits": residency["primary_peak_4572"]["bf16"]["8"]["fits_envelope"],
                "bf16_10k_c1_fits": residency["aa_10k"]["bf16"]["1"]["fits_envelope"],
            },
        })

    control = rows[0]
    result = {
        "schema_version": 1,
        "classification": "derived deterministic residency and attention-work bound; no CUDA, endpoint timing, provider mutation, or quality result",
        "identities": {"model": geometry["identities"]["target_model"], "vllm_revision": geometry["identities"]["runtime"]["vllm_git_revision"], "inputs_sha256": {str(p.relative_to(LAB)): sha(p) for p in (GEOMETRY, MEMORY, FP8_ARM, SOURCE)}},
        "formulas": {
            "bf16_kv": "local=50*min(T,W)*(2*Kvh*D*2); global=10*T*(2*Kvh*D*2)",
            "fp8_per_token_head_kv": "value bytes use 1 byte/scalar; inline scales add 2*Kvh*4 bytes/token/layer",
            "qk_av_flops": "4*query_heads*head_dim*sum_t(min(t, attended_window)); QK and AV each contribute 2 FLOPs/score",
            "effect_upper_bound": "saved QK/AV FLOPs / (all attention projections + all MLPs + required vocab sampling + control QK/AV); this is not requests/s",
        },
        "allowances_gib": {"weights_and_scales_conservative": memory["steady_state_bound"]["weights_and_scales_gib_conservative"], "runtime_reservation": memory["steady_state_bound"]["runtime_reservation_gib"], "non_kv_base": bound_base_gib, "l40s_usable_envelope": envelope_gib},
        "runtime_note": "The pinned hybrid KV manager supports separate local/full groups by default. If --disable-hybrid-kv-cache-manager is set, source lines 1445-49 state local KV eviction is disabled; then none of these window-residency reductions may be claimed. This experiment has not observed the live launch flag.",
        "fp8_contract_reconciliation": {"source_exact_primary_1024_gib": gib(kv_bytes(PROMPT, 1024, 1, 4)["total_bytes"]), "prior_arm_reported_gib": fp8_arm["derived_memory_gib"]["fp8_per_token_head_primary_kv_per_request"], "finding": "The prior reported value is inconsistent with its own one-FP8-byte-plus-4-byte-per-token-head source contract. This bound uses the explicit source formula, but makes no change to the live owner or its conditional arm."},
        "rows": rows,
        "batching_sensitivity": {"useful_background_concurrencies": list(CONCURRENCIES), "result": "At a fixed per-request geometry, batching multiplies KV residency by concurrency but leaves FLOP-ratio upper bounds unchanged. It can change observed wall-time exposure, so only a later matched quality/performance run may turn these bounds into cost evidence."},
        "decision": {"nominee": "768-token local window, quality-gated capacity candidate only", "reason": "768 is the least semantic change that crosses the logical BF16 c8 peak residency envelope: 44.484 GiB versus 45.266 GiB for the control, under the unchanged 39.35 GiB non-KV allowance and 44.704 GiB envelope. Its 0.5440% FLOP bound does not clear 5%, so no speed/cost claim is made. 512/256 are not nominated because they add context risk without clearing 5% or creating an additional needed capacity tier.", "quality_requirement_if_reopened": ["long-context requests whose needed evidence lies 769-1024 tokens before the query", "multi-turn agent/tool traces with 769-1024-token dependencies", "primary prompt-length and 10K slices, paired against the 1024 control", "raw token/text quality scoring and feature regression, followed by matched endpoint memory/cost telemetry"]},
        "control_summary": {"bf16_primary_input_c8_total_gib": control["residency"]["primary_input_4214"]["bf16"]["8"]["total_conservative_gib"], "bf16_primary_peak_c8_total_gib": control["residency"]["primary_peak_4572"]["bf16"]["8"]["total_conservative_gib"], "bf16_10k_c1_total_gib": control["residency"]["aa_10k"]["bf16"]["1"]["total_conservative_gib"]},
    }
    (ROOT / "WINDOW_BOUND.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
