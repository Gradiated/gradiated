#!/usr/bin/env python3
"""Deterministic, metadata-only bound for the tied Gemma vocabulary matrix."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
V = 262_144
H = 5_376
I = 21_504
PROMPT = 4_214
OUTPUT = 358
VOCAB_PROJECTION_FLOPS_PER_TOKEN = 2 * H * V
TIED_PARAMS = V * H
BF16_BYTES = TIED_PARAMS * 2
ONE_BYTE_BYTES = TIED_PARAMS


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request_bound(prompt_tokens: int) -> dict:
    # One logits projection for the final prefill position plus one per output
    # token. This is the minimum required full-vocabulary correctness path.
    logits_positions = OUTPUT + 1
    sliding_attention = 2 * H * (32 * 256 + 2 * 16 * 256 + 32 * 256)
    global_attention = 2 * H * (32 * 512 + 2 * 4 * 512 + 32 * 512)
    mlp = 6 * H * I
    decoder_flops_per_token = 50 * (sliding_attention + mlp) + 10 * (
        global_attention + mlp
    )
    decoder_flops = (prompt_tokens + OUTPUT) * decoder_flops_per_token
    full_vocab_flops = logits_positions * VOCAB_PROJECTION_FLOPS_PER_TOKEN
    denominator = decoder_flops + full_vocab_flops
    rows = []
    for shortlist in (V, 131_072, 65_536, 32_768, 16_384, 8_192, 4_096):
        saved = (V - shortlist) * H * 2 * logits_positions
        rows.append(
            {
                "retained_rows": shortlist,
                "retained_matrix_bytes_one_byte": shortlist * H,
                "saved_matrix_bytes_one_byte": (V - shortlist) * H,
                "saved_logits_flops": saved,
                "saved_fraction_percent": 100 * saved / denominator,
                "semantic_status": (
                    "full_vocab_control"
                    if shortlist == V
                    else "proxy_requires_tokenizer_and_output_semantics_review"
                ),
            }
        )
    return {
        "prompt_tokens": prompt_tokens,
        "output_tokens": OUTPUT,
        "logits_positions": logits_positions,
        "decoder_flops_per_token": decoder_flops_per_token,
        "decoder_flops": decoder_flops,
        "full_vocab_projection_flops": full_vocab_flops,
        "whole_request_flop_denominator": denominator,
        "perfect_shortlist_saved_fraction_percent": 100 * full_vocab_flops / denominator,
        "shortlist_proxy_rows": rows,
    }


def main() -> None:
    geometry = ROOT.parent / "exact_geometry_runtime_opportunities" / "GEOMETRY.json"
    memory = ROOT.parent / "fp8_l40s_fit_economic_falsifier" / "MEMORY_ACCOUNTING.json"
    saturation = ROOT.parent / "l40s_saturation_economic_gate" / "SATURATION_GATE.json"
    inputs = {
        str(p.relative_to(ROOT.parent.parent.parent.parent)): sha256(p)
        for p in (geometry, memory, saturation)
    }
    current_weights = 34.35
    l40s_capacity = 44.704
    runtime_reservation = 5.0
    c8_kv = 5.696
    bf16_gib = BF16_BYTES / 2**30
    one_byte_gib = ONE_BYTE_BYTES / 2**30
    artifact = {
        "schema_version": 1,
        "evidence_type": "derived_exact_geometry_bound_no_cuda_no_provider",
        "target": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "inputs_sha256": inputs,
        "geometry": {
            "vocab_rows": V,
            "hidden_size": H,
            "tied_parameters": TIED_PARAMS,
            "bf16_bytes": BF16_BYTES,
            "bf16_gib": bf16_gib,
            "fp8_or_int8_one_byte_bytes": ONE_BYTE_BYTES,
            "fp8_or_int8_one_byte_gib": one_byte_gib,
            "logits_flops_per_token": VOCAB_PROJECTION_FLOPS_PER_TOKEN,
        },
        "representation_cases": {
            "output_only_fp8_or_int8_with_bf16_input_embedding": {
                "resident_delta_gib": one_byte_gib,
                "c8_total_conservative_gib": current_weights + runtime_reservation + one_byte_gib + c8_kv,
                "fits_l40s_envelope": current_weights + runtime_reservation + one_byte_gib + c8_kv <= l40s_capacity,
                "interpretation": "No: tied weights must be duplicated to use different representations; this worsens c8 residency.",
            },
            "joint_tied_fp8_or_int8_input_and_output": {
                "resident_delta_gib": -one_byte_gib,
                "c8_total_conservative_gib": current_weights + runtime_reservation - one_byte_gib + c8_kv,
                "fits_l40s_envelope": current_weights + runtime_reservation - one_byte_gib + c8_kv <= l40s_capacity,
                "interpretation": "Hypothetically yes, but it changes embedding lookup and output numerics and has no pinned execution-equivalent consumer.",
            },
            "perfect_shortlist": {
                "storage_status": "impossible_without_full_vocab_correctness_exception",
                "saved_storage_upper_bound_gib": bf16_gib,
                "interpretation": "Analytical ceiling only; full logits, logprobs, tokenizer coverage, and exact API semantics require all rows.",
            },
        },
        "whole_request_bounds": {
            "primary_4214_358": request_bound(PROMPT),
            "comparator_10000_358": request_bound(10_000),
        },
        "capacity_context": {
            "l40s_usable_envelope_gib": l40s_capacity,
            "current_fp8_decoder_plus_bf16_tied_weights_gib": current_weights,
            "runtime_reservation_gib": runtime_reservation,
            "primary_c8_kv_gib": c8_kv,
            "current_primary_c8_total_gib": current_weights + runtime_reservation + c8_kv,
            "joint_tied_one_byte_primary_c8_total_gib": current_weights + runtime_reservation - one_byte_gib + c8_kv,
            "capacity_interpretation": "Joint one-byte tied storage would cross c8, but output-only representation cannot and the joint consumer is unproven.",
        },
        "quality_and_consumer_constraints": [
            "Tied embedding/output weights cannot be independently represented without duplicate storage.",
            "Joint low-bit embedding changes prompt token vectors as well as logits.",
            "Shortlists risk tokenizer coverage, rare and multilingual/code/tool tokens, logprobs, sampling, and exact OpenAI-compatible outputs.",
            "No CUDA, quality, throughput, or endpoint-cost result is claimed.",
        ],
        "decision": {
            "nominee": None,
            "close": True,
            "reason": "No credible isolated candidate clears 5%; the only capacity-crossing case is a hypothetical joint tied one-byte consumer excluded by the pinned runtime.",
        },
    }
    (ROOT / "VOCAB_BOUND.json").write_text(json.dumps(artifact, indent=2) + "\n")


if __name__ == "__main__":
    main()
