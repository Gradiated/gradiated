"""Reproduce the $0 depth42 background-concurrency memory gate."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "DEPTH42_BACKGROUND_FRONTIER.json"

DEVICE_MIB = 46_068.0
ROBUST_HEADROOM_MIB = 1_536.0
C32_PEAK_MIB = 43_666.023104858396
KV_BYTES_PER_TOKEN = 48_384
PROMPT_TOKENS = 8_192
BASE_CONCURRENCY = 32


def main() -> None:
    kv_per_sequence_mib = KV_BYTES_PER_TOKEN * PROMPT_TOKENS / 2**20
    fixed_mib = C32_PEAK_MIB - BASE_CONCURRENCY * kv_per_sequence_mib
    robust_limit_mib = DEVICE_MIB - ROBUST_HEADROOM_MIB
    rows = []
    for concurrency in (32, 40, 48, 64):
        kv_mib = concurrency * kv_per_sequence_mib
        nominal_peak_mib = fixed_mib + kv_mib
        rows.append(
            {
                "concurrency": concurrency,
                "kv_block_reservation_mib": kv_mib,
                "nominal_peak_mib": nominal_peak_mib,
                "nominal_headroom_mib": DEVICE_MIB - nominal_peak_mib,
                "adverse_peak_mib": nominal_peak_mib + ROBUST_HEADROOM_MIB,
                "robust_admitted": nominal_peak_mib <= robust_limit_mib,
                "future_c32_throughput_trigger_tok_s": None,
                "reason": (
                    "baseline" if concurrency == BASE_CONCURRENCY else
                    "memory-rejected before a future-c32 throughput trigger can be decision-relevant"
                ),
            }
        )
    result = {
        "schema_version": 1,
        "decision": "MEMORY_CLOSE",
        "decision_reason": "c40 adds eight exact 8K BF16-KV reservations (3,024 MiB) to the checksum-closed c32 projection, exceeding the 46,068-MiB envelope; no higher concurrency retains the 1,536-MiB robust-headroom convention.",
        "evidence_class": "derived_from_fixed_model_geometry_and_historical_memory_projection",
        "candidate": {
            "contract_sha256": "5dbf26dc16a1cabbdb36eb256a996a11cf44c71c702b72686806a68a3bb1a290",
            "serving_layers": 42,
            "runtime": "vLLM 0.15.0-derived; BF16 KV; num_kv_splits=4; prefix cache off",
        },
        "geometry": {
            "input_tokens_per_request": PROMPT_TOKENS,
            "output_tokens_per_request": 1024,
            "page_size_tokens": 16,
            "pages_per_sequence_at_prompt": PROMPT_TOKENS // 16,
            "kv_bytes_per_token": KV_BYTES_PER_TOKEN,
            "kv_bytes_per_sequence": KV_BYTES_PER_TOKEN * PROMPT_TOKENS,
            "kv_block_reservation_per_sequence_mib": kv_per_sequence_mib,
        },
        "memory_model": {
            "c32_projection_mib": C32_PEAK_MIB,
            "fixed_model_runtime_graph_scheduler_mib": fixed_mib,
            "interpretation": "The fixed term is the c32 projection after subtracting exact prompt-length KV reservation. It includes checkpoint/runtime, graph/capture, scheduler, allocator, and all unseparated historical fragmentation; no unsupported decomposition is asserted.",
            "device_envelope_mib": DEVICE_MIB,
            "robust_headroom_convention_mib": ROBUST_HEADROOM_MIB,
            "robust_admission_limit_mib": robust_limit_mib,
            "adverse_case": "nominal peak plus the campaign 1,536-MiB fragmentation/graph/scheduler allowance",
        },
        "frontier": rows,
        "throughput_gate": {
            "economic_gate_tok_s": 594.466,
            "robust_nomination_gate_tok_s": 606.355,
            "background_envelope_seconds": 300,
            "future_c32_trigger": None,
            "trigger_reason": "No c40/c48/c64 arm survives memory; a c32 endpoint cannot make an inadmissible higher-concurrency arm informative.",
            "historical_sensitivity_only": {
                "student39_c16_tok_s": 674.423576364909,
                "student39_c24_tok_s": 661.6607656099549,
                "student39_c32_tok_s": 734.5565331529764,
                "treatment": "not transferred to depth42 throughput or used for nomination",
            },
        },
        "quality": "architecture-cost and scheduling evidence only; quality remains mandatory before deployment",
        "live_owner": "not inspected or used",
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
