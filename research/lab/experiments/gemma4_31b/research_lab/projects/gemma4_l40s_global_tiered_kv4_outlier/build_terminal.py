#!/usr/bin/env python3
"""Build the hash-bound offline terminal from the measured raw artifact."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
ROOT = Path("/root/workspace")
SGLANG = ROOT / ".agents/runtime/gemma4_global_kv_sglang"
RAW = PROJECT / "artifacts/OFFLINE_NUMERICAL.json"
TERMINAL = PROJECT / "L40S_GLOBAL_TIERED_KV4_OUTLIER_OFFLINE_TERMINAL.json"
IMPLEMENTATION_FILES = (
    "global_tiered_kv4_reference.py",
    "global_tiered_kv4_cuda.cu",
    "global_tiered_kv4_bindings.cpp",
    "sglang_global_tiered_kv4.py",
    "run_l40s_component.py",
    "offline_experiment.py",
    "test_global_tiered_kv4.py",
    "build_terminal.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path, evidence: str = "direct") -> dict:
    return {"path": str(path), "sha256": sha256(path), "evidence": evidence}


def main() -> int:
    raw = json.loads(RAW.read_text())
    rows = raw["full_history"]["rows"]
    numerical_pass = all(
        row["corrected_vs_high_precision"]["candidate_nonfinite"] == 0
        and row["corrected_vs_high_precision"]["relative_l2"] <= 0.08
        and row["corrected_vs_high_precision"]["cosine"] >= 0.995
        for row in rows
    )
    ownership = raw["ownership_and_transitions"]
    transition_pass = (
        ownership["empty_old_tier"]
        and ownership["first_old_token"]
        and ownership["padded_negative_page_noop"]
        and ownership["request_isolation"]["canonical_owner_mismatch_rejected"]
        and all(row["finite"] for row in ownership["transition_rows"])
    )
    memory_pass = (
        raw["memory"]["bytes_saved_exact_before_rounding"] > 0
        and raw["memory"]["lower_deficit_reduction_fraction"] >= 0.25
    )
    offline_pass = numerical_pass and transition_pass and memory_pass
    component_command = (
        "PYTHONPATH=/root/workspace/.agents/runtime/gemma4_global_kv_sglang/python "
        "python3 /root/workspace/research/lab/experiments/gemma4_31b/research_lab/"
        "projects/gemma4_l40s_global_tiered_kv4_outlier/run_l40s_component.py "
        "--source-root /root/workspace/.agents/runtime/gemma4_global_kv_sglang "
        "--output /root/workspace/research/lab/experiments/gemma4_31b/research_lab/"
        "projects/gemma4_l40s_global_tiered_kv4_outlier/artifacts/"
        "L40S_GLOBAL_TIERED_KV4_OUTLIER_COMPONENT.json --warmup 2 --repetitions 20"
    )
    host_terminal = (
        PROJECT.parent
        / "gemma4_l40s_global_kv_host_prefetch"
        / "L40S_GLOBAL_KV_HOST_PREFETCH_OFFLINE_TERMINAL.json"
    )
    local_terminal = (
        PROJECT.parent
        / "gemma4_l40s_local_kv4_outlier_codesign"
        / "L40S_LOCAL_KV4_OUTLIER_OFFLINE_TERMINAL.json"
    )
    packet = (
        PROJECT.parent / "gemma4_l40s_kv4_outlier_allocator_rebase_endpoint" / "packet"
    )
    source_paths = (
        "python/sglang/srt/layers/attention/triton_backend.py",
        "python/sglang/srt/mem_cache/swa_memory_pool.py",
        "python/sglang/srt/mem_cache/memory_pool.py",
        "python/sglang/srt/models/gemma4_causal.py",
    )
    terminal = {
        "schema_version": 1,
        "kind": "l40s_global_tiered_kv4_outlier_offline_terminal",
        "project": PROJECT.name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "decision": "admit_later_sm89_component" if offline_pass else "none",
        "classification": (
            "offline_representation_pass_allocator_margin_improved_endpoint_still_does_not_fit"
            if offline_pass
            else "typed_none_offline_gate_failed"
        ),
        "pass": offline_pass,
        "actual_spend_usd": 0.0,
        "prohibitions_observed": {
            "gpu_claimed": False,
            "cuda_run": False,
            "ssh_or_provider_used": False,
            "checkpoint_shards_read": False,
            "training_or_parameter_sweep": False,
            "d256_numerical_evidence_transferred": False,
        },
        "identities": {
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            },
            "runtime": {
                "repository": "https://github.com/sgl-project/sglang",
                "commit": "c6a6200a1a778a799ba61c395ac292317f01ebc9",
                "attention_backend": "current official Triton paged attention",
            },
            "hardware_target": {
                "model": "NVIDIA L40S",
                "architecture": "Ada Lovelace SM89",
                "sms": 142,
                "memory_bytes": 48_305_799_168,
            },
            "workload": {
                "concurrency": 32,
                "prompt_tokens": 4214,
                "output_tokens": 358,
                "shared_prefix_tokens": 535,
                "page_size": 1,
                "global_layers": 10,
                "global_kv_heads": 4,
                "query_heads": 32,
                "head_dim": 512,
            },
        },
        "representation": {
            "recent": {
                "tokens_per_request": 1024,
                "dtype": "finite E5M2 round-to-nearest-even satfinite",
                "row_bytes_per_k_or_v": 512,
            },
            "old": {
                "group_size": 64,
                "groups": 8,
                "signed_int4_range": [-7, 7],
                "scale_dtype": "BF16",
                "scale_statistic": "second-largest absolute source value per group",
                "outliers": 8,
                "outlier_index_dtype": "uint16",
                "residual_dtype": "finite E5M2",
                "row_bytes_per_k_or_v": 296,
                "layout_bytes": {
                    "0:256": "256 low-channel-first signed-nibble bytes",
                    "256:272": "eight little-endian BF16 scales",
                    "272:288": "eight little-endian uint16 channel indices in descending residual magnitude with channel-id tie break",
                    "288:296": "eight E5M2 residual bytes in matching order",
                },
            },
            "transition": "initial old prompt rows pack directly from BF16; a row aging past 1024 packs once from its retained E5M2 bytes, while the compact location remains bound to the canonical physical page id",
        },
        "acceptance": {
            "numerical_pass": numerical_pass,
            "ownership_and_transition_pass": transition_pass,
            "memory_margin_improvement_pass": memory_pass,
            "thresholds": {
                "relative_l2_max": 0.08,
                "cosine_min": 0.995,
                "query_positions": [4214, 4571],
            },
            "raw_rows": rows,
            "complete_output": raw["full_history"]["complete_output"],
            "current_e5m2_comparator": raw["full_history"][
                "current_e5m2_comparator"
            ],
        },
        "focused_checks": [
            {
                "command": "python3 -m py_compile global_tiered_kv4_reference.py offline_experiment.py test_global_tiered_kv4.py sglang_global_tiered_kv4.py run_l40s_component.py",
                "result": "pass",
            },
            {
                "command": "uv run --with numpy --with torch python -m unittest -v test_global_tiered_kv4.py",
                "result": "pass",
                "tests": 7,
            },
            {
                "command": "uv run --with numpy python offline_experiment.py --output artifacts/OFFLINE_NUMERICAL.json",
                "result": "pass",
            },
        ],
        "producer_consumer": {
            "producer_symbols": [
                "tiered_store_recent/store_recent_kernel",
                "tiered_pack_old/pack_old_kernel<..., false>",
                "tiered_retire_recent/pack_old_kernel<float, true>",
            ],
            "consumer_symbol": "tiered_paged_attention/mixed_tier_paged_attention_kernel",
            "source_complete": True,
            "consumer_contract": "one traversal of unchanged canonical kv_indices; cursor-relative tier selection; direct E5M2 or corrected packed-row loads feed one FP32 running-max/running-sum/per-channel online-softmax accumulator; no dequantized cache or output intermediate",
            "gqa": "query_head / (query_heads / kv_heads), exact 32Q:4KV",
            "padded_rows": "negative physical ids no-op before any directory or payload load",
            "ownership": "canonical physical ids remain ReqToTokenPool/SWATokenToKVPoolAllocator authority; compact directories add location only",
            "runtime_limit": "the fixed component layout is locked to c32, chunked-prefill-size 2048, page size one, and the exact peak row counts; production allocator hooks remain a later integration step",
        },
        "memory": raw["memory"],
        "physical": raw["physical"],
        "raw_numerical_evidence": {
            **binding(RAW, "measured deterministic synthetic CPU and analytical"),
            "stdout_log": binding(
                PROJECT / "artifacts/OFFLINE_NUMERICAL.stdout.log",
                "raw command stdout; empty because the accepted foreground rerun wrote to the terminal stream",
            ),
        },
        "later_component": {
            "type": "command",
            "command": component_command,
            "comparator": "pinned current SGLang decode_attention_fwd over the same exact c32 D512 page-one E5M2 cache",
            "candidate": "full producer plus mixed-tier consumer; complete output is consumed before CUDA-event timing",
            "required_evidence": [
                "first untimed baseline and candidate completion markers",
                "compiled registers, static shared memory, spills, and source identity",
                "warm profiler-off latency distributions",
                "relative L2, cosine, and finite-output checks",
                "candidate-path proof and exact peak layout",
            ],
            "not_run_reason": "the admitted action explicitly forbids claiming a GPU or running CUDA, and the shared inventory has no benches",
        },
        "direct_bindings": {
            "project": binding(PROJECT / "PROJECT.md"),
            "campaign": binding(LAB / "CAMPAIGN.md"),
            "host_prefetch_terminal": binding(host_terminal),
            "local_d256_terminal_identity_only": binding(
                local_terminal,
                "direct identity/memory binding only; its numerical rows were not transferred",
            ),
            "model_config": binding(packet / "MODEL_CONFIG.json"),
            "workload": binding(packet / "WORKLOAD.json"),
            "accelerator_inventory": binding(
                ROOT / "research/factory/data/accelerator_inventory.json"
            ),
            "sglang_source": {
                relative: {
                    **binding(
                        SGLANG / relative,
                        "direct bytes from clean pinned local git snapshot",
                    ),
                    "commit": "c6a6200a1a778a799ba61c395ac292317f01ebc9",
                }
                for relative in source_paths
            },
        },
        "implementation_hashes": {
            name: sha256(PROJECT / name) for name in IMPLEMENTATION_FILES
        },
        "uncertainty": [
            {
                "item": "Synthetic checkpoint-free D512 K/V are not production quality evidence.",
                "label": "measured synthetic",
                "effect": "both numerical positions pass the early discriminator, but GPQA/TauBench remain untested",
            },
            {
                "item": "The CUDA source was not compiled or executed on SM89 by prohibition.",
                "label": "unmeasured target execution",
                "effect": "registers, spills, occupancy, numerical parity, and producer-plus-consumer latency remain decision-bearing",
            },
            {
                "item": "Allocator rounding is unknown before target integration.",
                "label": "analytical one-sided interval",
                "effect": "the upper memory bound charges 16 MiB; even the exact lower bound remains 2.428 GB over physical capacity",
            },
            {
                "item": "No endpoint fit is claimed.",
                "label": "derived exact lower bound",
                "effect": "global compression removes 1.589 GB and 39.56% of the inherited lower deficit, but another allocator/residency intervention is still required",
            },
        ],
        "terminal_reasons": (
            [
                "fresh_d512_full_history_numerics_pass_both_bound_positions",
                "ownership_padding_and_1023_1024_1025_transitions_pass",
                "source_complete_one_pass_sm89_component_exists",
                "global_residency_reduced_by_1589350756_exact_bytes",
                "complete_l40s_fit_remains_negative_by_at_least_2428118480_bytes",
                "target_sm89_performance_and_compiler_resources_unmeasured_by_explicit_prohibition",
            ]
            if offline_pass
            else ["one_or_more_offline_acceptance_gates_failed"]
        ),
        "next_action": (
            "Preserve this offline pass for a later zero-question SM89 component comparison when the director admits a compatible shared L40S bench; do not claim fit or endpoint viability until another in-scope allocator/residency mechanism removes the remaining 2.428-3.396 GB interval."
            if offline_pass
            else "Close this fixed representation as typed none."
        ),
    }
    TERMINAL.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
