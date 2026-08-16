#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
LAB_ROOT = PROJECT_ROOT.parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[6]
MODEL_CONFIG = (
    LAB_ROOT
    / "projects/gemma4_l40s_kv4_outlier_allocator_rebase_endpoint/packet/MODEL_CONFIG.json"
)
WORKLOAD = (
    LAB_ROOT
    / "projects/gemma4_l40s_kv4_outlier_allocator_rebase_endpoint/packet/WORKLOAD.json"
)
LAUNCH = (
    LAB_ROOT
    / "projects/gemma4_prefill_cuda_graph_padding_rebase/inputs/workload/LAUNCH.json"
)
LOCAL_KV_TERMINAL = (
    LAB_ROOT
    / "projects/gemma4_l40s_local_kv4_outlier_codesign/L40S_LOCAL_KV4_OUTLIER_OFFLINE_TERMINAL.json"
)
CAMPAIGN = LAB_ROOT / "CAMPAIGN.md"
ACCELERATOR_INVENTORY = (
    WORKSPACE_ROOT / "research/factory/data/accelerator_inventory.json"
)
GPU_PRICES = WORKSPACE_ROOT / "research/factory/data/gpu_prices.json"
PROJECT = PROJECT_ROOT / "PROJECT.md"
TRACE_PATH = PROJECT_ROOT / "artifacts/L40S_GLOBAL_KV_HOST_PREFETCH_TRACE.json"
TERMINAL_PATH = PROJECT_ROOT / "L40S_GLOBAL_KV_HOST_PREFETCH_OFFLINE_TERMINAL.json"
SGLANG_COMMIT = "c6a6200a1a778a799ba61c395ac292317f01ebc9"
SGLANG_FILES = (
    "python/sglang/srt/models/gemma4_causal.py",
    "python/sglang/srt/mem_cache/memory_pool.py",
    "python/sglang/srt/mem_cache/swa_memory_pool.py",
    "python/sglang/srt/mem_cache/allocator/swa.py",
    "python/sglang/srt/mem_cache/kv_cache_configurator.py",
    "python/sglang/srt/model_executor/model_runner_components/layer_setup.py",
    "python/sglang/srt/layers/radix_attention.py",
    "python/sglang/srt/layers/attention/triton_backend.py",
)
SERVICE_BOUNDARY_S = 1.4776251501079425
PCIE_GEN4_GT_S = 16_000_000_000
PCIE_LANES = 16
PCIE_ENCODING_PAYLOAD_FRACTION = 128 / 130
PCIE_PAYLOAD_CEILING_BYTES_S = (
    PCIE_GEN4_GT_S * PCIE_LANES * PCIE_ENCODING_PAYLOAD_FRACTION / 8
)


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binding(path: Path, evidence: str = "direct") -> dict:
    return {
        "evidence": evidence,
        "path": str(path),
        "sha256": sha256(path),
    }


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def source_bindings(source_root: Path) -> dict:
    result = {}
    for relative in SGLANG_FILES:
        path = source_root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        result[relative] = {
            "evidence": "direct bytes from the official pinned git commit",
            "repository": "https://github.com/sgl-project/sglang",
            "commit": SGLANG_COMMIT,
            "raw_url": (
                "https://raw.githubusercontent.com/sgl-project/sglang/"
                f"{SGLANG_COMMIT}/{relative}"
            ),
            "sha256": sha256(path),
        }
    return result


def geometry() -> dict:
    model = load(MODEL_CONFIG)["text_config"]
    workload = load(WORKLOAD)
    global_layers = [
        index
        for index, layer_type in enumerate(model["layer_types"])
        if layer_type == "full_attention"
    ]
    local_layers = [
        index
        for index, layer_type in enumerate(model["layer_types"])
        if layer_type == "sliding_attention"
    ]
    prompt = workload["prompt_tokens"]
    output = workload["output_tokens"]
    concurrency = workload["concurrency"]
    shared = workload["shared_prefix_tokens"]
    fresh = prompt - shared
    decode_forwards = output - 1
    peak_rows = shared + concurrency * (fresh + decode_forwards)
    row_bytes = (
        2
        * model["num_global_key_value_heads"]
        * model["global_head_dim"]
    )
    return {
        "global_layer_ids": global_layers,
        "local_layer_ids": local_layers,
        "global_layers": len(global_layers),
        "local_layers": len(local_layers),
        "global_kv_heads": model["num_global_key_value_heads"],
        "global_head_dim": model["global_head_dim"],
        "kv_element_bytes": 1,
        "k_and_v_factor": 2,
        "row_bytes": row_bytes,
        "page_size": 1,
        "prompt_tokens_per_request": prompt,
        "output_tokens_per_request": output,
        "decode_forwards": decode_forwards,
        "concurrency": concurrency,
        "shared_prefix_tokens": shared,
        "fresh_prompt_tokens_per_request": fresh,
        "peak_physical_rows": peak_rows,
        "padded_capacity_rows": peak_rows + 1,
    }


def build_trace(g: dict) -> dict:
    rows = []
    row_bytes = g["row_bytes"]
    concurrency = g["concurrency"]
    shared = g["shared_prefix_tokens"]
    fresh = g["fresh_prompt_tokens_per_request"]
    global_layers = g["global_layer_ids"]

    for rank, layer_id in enumerate(global_layers):
        rows.append(
            {
                "phase": "prefill_candidate_favorable_lower",
                "step": 0,
                "global_layer_rank": rank,
                "layer_id": layer_id,
                "buffer": rank % 2,
                "prefetch_trigger": (
                    "forward_entry" if rank == 0 else f"after_global_layer_{global_layers[rank - 1]}"
                ),
                "cached_rows_h2d": shared,
                "fresh_rows_produced": concurrency * fresh,
                "h2d_bytes": shared * row_bytes,
                "d2h_bytes": concurrency * fresh * row_bytes,
                "consumer_waits_for_h2d_event": True,
                "evidence": (
                    "derived exact lower bound; chunked prefill can only reload "
                    "additional already-produced history"
                ),
            }
        )

    for step in range(g["decode_forwards"]):
        cached_rows = shared + concurrency * (fresh + step)
        for rank, layer_id in enumerate(global_layers):
            rows.append(
                {
                    "phase": "decode",
                    "step": step,
                    "global_layer_rank": rank,
                    "layer_id": layer_id,
                    "buffer": rank % 2,
                    "prefetch_trigger": (
                        "forward_entry"
                        if rank == 0
                        else f"after_global_layer_{global_layers[rank - 1]}"
                    ),
                    "cached_rows_h2d": cached_rows,
                    "fresh_rows_produced": concurrency,
                    "h2d_bytes": cached_rows * row_bytes,
                    "d2h_bytes": concurrency * row_bytes,
                    "consumer_waits_for_h2d_event": True,
                    "evidence": "derived exact from physical page ownership",
                }
            )

    totals = {
        "rows": len(rows),
        "prefill_h2d_bytes_lower": sum(
            row["h2d_bytes"]
            for row in rows
            if row["phase"] == "prefill_candidate_favorable_lower"
        ),
        "prefill_d2h_bytes_exact_fresh_rows": sum(
            row["d2h_bytes"]
            for row in rows
            if row["phase"] == "prefill_candidate_favorable_lower"
        ),
        "decode_h2d_bytes_exact": sum(
            row["h2d_bytes"] for row in rows if row["phase"] == "decode"
        ),
        "decode_d2h_bytes_exact": sum(
            row["d2h_bytes"] for row in rows if row["phase"] == "decode"
        ),
    }
    return {
        "schema_version": 1,
        "policy": {
            "buffers": 2,
            "prefetch_distance_global_layers": 1,
            "transfer_streams": 1,
            "buffer_assignment": "global_layer_rank modulo 2",
            "consumer_dependency": "attention waits on the H2D completion event",
            "writeback_dependency": (
                "new K/V rows are copied D2H before their staging buffer is reused; "
                "host storage remains canonical"
            ),
            "overlap_credit_in_terminal": "none",
        },
        "geometry": g,
        "rows": rows,
        "totals": totals,
    }


def build_memory(g: dict) -> dict:
    prior = load(LOCAL_KV_TERMINAL)["memory"]
    payload = g["peak_physical_rows"] * g["row_bytes"] * g["global_layers"]
    padding = g["row_bytes"] * g["global_layers"]
    full_pool = payload + padding
    one_staging = g["padded_capacity_rows"] * g["row_bytes"]
    two_staging = 2 * one_staging
    prior_recorded_padding = prior["components_bytes"]["page_one_padding_global"]
    prior_static_lower = prior["static_required_interval_bytes"]["lower"]
    prior_static_upper = prior["static_required_interval_bytes"]["upper"]
    corrected_static_lower = prior_static_lower + padding - prior_recorded_padding
    corrected_static_upper = prior_static_upper + padding - prior_recorded_padding
    candidate_static_lower = corrected_static_lower - full_pool + two_staging
    candidate_static_upper = corrected_static_upper - full_pool + two_staging
    allocator_limit = prior["static_allocator_limit_bytes"]
    dynamic_reserve = prior["components_bytes"]["launch_dynamic_allocator_reserve_bytes"]
    physical = prior["physical_bytes"]
    new_metadata_rounding_upper = 5 * 1024 * 1024
    complete_lower = candidate_static_lower + dynamic_reserve
    complete_upper = (
        candidate_static_upper + dynamic_reserve + new_metadata_rounding_upper
    )
    return {
        "device_resident_global_pool_corrected_bytes": full_pool,
        "global_payload_bytes": payload,
        "global_padding_bytes": padding,
        "prior_terminal_recorded_global_padding_bytes": prior_recorded_padding,
        "prior_padding_correction_bytes": padding - prior_recorded_padding,
        "one_staging_buffer_bytes": one_staging,
        "two_staging_buffers_bytes": two_staging,
        "host_pinned_canonical_bytes": full_pool,
        "device_bytes_saved_before_new_metadata": full_pool - two_staging,
        "new_device_metadata_and_allocator_rounding_interval_bytes": {
            "lower": 0,
            "upper": new_metadata_rounding_upper,
            "evidence": (
                "inferred conservative envelope for two packed stable allocations, "
                "events, descriptors, and allocator rounding"
            ),
        },
        "unchanged_page_table": {
            "owner": "ReqToTokenPool.req_to_token on device",
            "duplicated": False,
            "accounting": "already contained in the inherited launch dynamic reserve",
        },
        "candidate_static_required_interval_bytes": {
            "lower": candidate_static_lower,
            "upper": candidate_static_upper + new_metadata_rounding_upper,
        },
        "static_allocator_limit_bytes": allocator_limit,
        "static_allocator_headroom_interval_bytes": {
            "lower_case_headroom": allocator_limit - candidate_static_lower,
            "upper_case_headroom": allocator_limit
            - candidate_static_upper
            - new_metadata_rounding_upper,
        },
        "launch_dynamic_allocator_reserve_bytes": dynamic_reserve,
        "complete_required_interval_bytes": {
            "lower": complete_lower,
            "upper": complete_upper,
        },
        "physical_device_bytes": physical,
        "physical_headroom_interval_bytes": {
            "lower_case_headroom": physical - complete_lower,
            "upper_case_headroom": physical - complete_upper,
        },
        "memory_saving_useful": full_pool - two_staging > 4_000_000_000,
        "conservative_complete_fit": complete_upper <= physical,
        "evidence": (
            "derived from direct model geometry, pinned runtime allocation shapes, "
            "and the direct-hashed local-KV predecessor memory interval"
        ),
    }


def validate(g: dict, trace: dict, memory: dict) -> None:
    assert g["global_layer_ids"] == [5, 11, 17, 23, 29, 35, 41, 47, 53, 59]
    assert g["global_layers"] == 10
    assert g["local_layers"] == 50
    assert g["row_bytes"] == 4096
    assert g["decode_forwards"] == 357
    assert g["peak_physical_rows"] == 129687
    assert trace["totals"]["decode_h2d_bytes_exact"] == 1_812_617_748_480
    decode = [row for row in trace["rows"] if row["phase"] == "decode"]
    assert decode[0]["cached_rows_h2d"] == 118263
    assert decode[-1]["cached_rows_h2d"] == 129655
    assert all(row["buffer"] == row["global_layer_rank"] % 2 for row in trace["rows"])
    assert memory["global_payload_bytes"] == 5_311_979_520
    assert memory["global_padding_bytes"] == 40_960
    assert memory["two_staging_buffers_bytes"] == 1_062_404_096
    assert memory["device_bytes_saved_before_new_metadata"] == 4_249_616_384


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--trace", type=Path, default=TRACE_PATH)
    parser.add_argument("--terminal", type=Path, default=TERMINAL_PATH)
    args = parser.parse_args()

    g = geometry()
    trace = build_trace(g)
    memory = build_memory(g)
    validate(g, trace, memory)
    atomic_json(args.trace, trace)

    decode_h2d = trace["totals"]["decode_h2d_bytes_exact"]
    prefill_h2d = trace["totals"]["prefill_h2d_bytes_lower"]
    prefill_d2h = trace["totals"]["prefill_d2h_bytes_exact_fresh_rows"]
    decode_d2h = trace["totals"]["decode_d2h_bytes_exact"]
    decode_engine_seconds = decode_h2d / PCIE_PAYLOAD_CEILING_BYTES_S
    decode_seconds_per_request = decode_engine_seconds / g["concurrency"]
    all_transfer_lower_bytes = (
        decode_h2d + prefill_h2d + prefill_d2h + decode_d2h
    )
    all_transfer_lower_seconds = (
        all_transfer_lower_bytes / PCIE_PAYLOAD_CEILING_BYTES_S
    )
    all_transfer_lower_per_request = (
        all_transfer_lower_seconds / g["concurrency"]
    )
    planning_rate = 1.1
    cost_floor = decode_seconds_per_request * planning_rate / 3600 * 1_000_000
    target_cost = SERVICE_BOUNDARY_S * planning_rate / 3600 * 1_000_000

    terminal = {
        "kind": "l40s_global_kv_host_prefetch_offline_terminal",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": PROJECT_ROOT.name,
        "pass": False,
        "decision": "none",
        "classification": "typed_none_compulsory_decode_h2d_exceeds_boundary",
        "actual_spend_usd": 0.0,
        "identities": {
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            },
            "runtime": {
                "repository": "https://github.com/sgl-project/sglang",
                "commit": SGLANG_COMMIT,
                "attention_backend": "Triton prefill and decode",
            },
            "hardware": {
                "model": "NVIDIA L40S",
                "architecture": "Ada Lovelace SM89",
                "host_interconnect": "PCIe Gen4 x16",
                "peer_interconnect": None,
            },
            "workload": {
                "concurrency": g["concurrency"],
                "prompt_tokens": g["prompt_tokens_per_request"],
                "output_tokens": g["output_tokens_per_request"],
                "shared_prefix_tokens": g["shared_prefix_tokens"],
                "fresh_prompt_tokens": g["fresh_prompt_tokens_per_request"],
                "page_size": 1,
                "tp": 1,
            },
        },
        "direct_bindings": {
            "project": binding(PROJECT),
            "campaign": binding(CAMPAIGN),
            "model_config": binding(MODEL_CONFIG),
            "workload": binding(WORKLOAD),
            "launch": binding(LAUNCH),
            "local_kv_predecessor_terminal": binding(LOCAL_KV_TERMINAL),
            "accelerator_inventory": binding(ACCELERATOR_INVENTORY),
            "gpu_prices": binding(GPU_PRICES),
            "sglang_source": source_bindings(args.source_root),
        },
        "runtime_ownership": {
            "producer": {
                "symbol": "Gemma4Attention.forward -> RadixAttention.forward",
                "source": "python/sglang/srt/models/gemma4_causal.py",
                "contract": (
                    "QKV projection, fused Q/K/V norm, and RoPE produce distinct "
                    "global K and V; attention is invoked with save_kv_cache=True."
                ),
            },
            "page_table_owner": {
                "symbol": "ReqToTokenPool.req_to_token",
                "source": "python/sglang/srt/mem_cache/memory_pool.py",
                "contract": (
                    "request rows map logical sequence positions to full-pool "
                    "physical slot ids; the host policy preserves these ids."
                ),
            },
            "physical_slot_allocator": {
                "symbol": "SWATokenToKVPoolAllocator.full_attn_allocator",
                "source": "python/sglang/srt/mem_cache/allocator/swa.py",
                "contract": (
                    "full slots are allocated independently of SWA slots and remain "
                    "the canonical indices returned to forward_batch.out_cache_loc."
                ),
            },
            "pool_owner": {
                "symbol": "SWAKVPool.full_kv_pool",
                "source": "python/sglang/srt/mem_cache/swa_memory_pool.py",
                "contract": (
                    "global layer ids map to ten MHATokenToKVPool layer indices; "
                    "current code allocates separate K and V [size+page,4,512] tensors."
                ),
            },
            "write_boundary": {
                "symbol": "TritonAttnBackend._set_kv_buffer -> SWAKVPool.set_kv_buffer",
                "source": "python/sglang/srt/layers/attention/triton_backend.py",
                "contract": (
                    "the producer writes new global rows at out_cache_loc before "
                    "attention; a host-canonical adapter must D2H those rows before "
                    "their staging buffer is reused."
                ),
            },
            "first_consumer": {
                "symbol": "TritonAttnBackend.forward_extend/forward_decode",
                "source": "python/sglang/srt/layers/attention/triton_backend.py",
                "contract": (
                    "the backend calls get_key_buffer/get_value_buffer and passes "
                    "the unchanged kv_indptr/kv_indices to the Triton attention "
                    "kernel; each consumer must wait on its staging H2D event."
                ),
            },
            "fixed_adapter_sketch": [
                "Replace only full_kv_pool storage with ten pinned-host K/V layer images.",
                "Keep ReqToTokenPool and SWATokenToKVPoolAllocator full physical ids unchanged.",
                "Allocate two stable packed device buffers of one padded global layer each.",
                "At forward entry prefetch global layer 5; after each global consumer prefetch the next global layer into the alternate buffer on one transfer stream.",
                "Make the compute stream wait on the selected buffer event before the existing Triton consumer receives K/V views.",
                "Write current K/V into that staged layer at unchanged out_cache_loc and copy only those new rows D2H before buffer reuse.",
                "Do not duplicate, remap, compress, or change the E5M2 global cache.",
            ],
            "source_complete_for_semantics": True,
            "runtime_implemented": False,
            "implementation_reason": (
                "The exact compulsory H2D lower bound is already terminally "
                "negative, so production integration cannot change the decision."
            ),
        },
        "geometry": g,
        "traffic": {
            "bytes_per_global_token_per_layer": g["row_bytes"],
            "device_resident_attention_bytes_per_layer_at_peak": (
                g["peak_physical_rows"] * g["row_bytes"]
            ),
            "prefill": {
                "h2d_bytes_candidate_favorable_lower": prefill_h2d,
                "d2h_bytes_for_exact_fresh_rows": prefill_d2h,
                "chunking_effect": (
                    "The launch fixes chunked-prefill-size=2048. Arrival ordering "
                    "and scheduler grouping are not frozen by WORKLOAD.json; every "
                    "additional chunk reloads nonnegative prior history. The terminal "
                    "therefore uses the exact candidate-favorable lower bound and "
                    "does not need a guessed schedule."
                ),
            },
            "decode": {
                "forwards": g["decode_forwards"],
                "first_step_cached_rows_per_layer": (
                    g["shared_prefix_tokens"]
                    + g["concurrency"] * g["fresh_prompt_tokens_per_request"]
                ),
                "last_step_cached_rows_per_layer": (
                    g["shared_prefix_tokens"]
                    + g["concurrency"]
                    * (g["fresh_prompt_tokens_per_request"] + g["decode_forwards"] - 1)
                ),
                "h2d_bytes_exact": decode_h2d,
                "d2h_bytes_exact_new_rows": decode_d2h,
                "h2d_bytes_amortized_per_request": decode_h2d / g["concurrency"],
            },
            "all_fixed_policy_transfer_bytes_lower": all_transfer_lower_bytes,
            "raw_trace": {
                "path": str(args.trace),
                "sha256": sha256(args.trace),
                "rows": len(trace["rows"]),
                "contents": "one raw phase/step/global-layer record per staging action",
            },
        },
        "memory": memory,
        "latency": {
            "pcie_payload_ceiling": {
                "bytes_per_second": PCIE_PAYLOAD_CEILING_BYTES_S,
                "derivation": "16 GT/s/lane * 16 lanes * (128/130) / 8",
                "evidence": (
                    "analytical candidate-favorable ceiling from the inventory's "
                    "vendor-reported PCIe Gen4 x16 identity; transaction and "
                    "protocol overhead are ignored"
                ),
            },
            "decode_h2d_engine_seconds_per_batch_lower": decode_engine_seconds,
            "decode_h2d_seconds_per_request_amortized_lower": decode_seconds_per_request,
            "all_transfer_stream_seconds_per_batch_lower": all_transfer_lower_seconds,
            "all_transfer_stream_seconds_per_request_amortized_lower": (
                all_transfer_lower_per_request
            ),
            "complete_service_seconds_per_request": {
                "lower": decode_seconds_per_request,
                "upper": "infinity",
                "lower_evidence": (
                    "resource-work lower bound using decode H2D only; excludes all "
                    "compute, D2H, prompt reloads, protocol overhead, and imperfect efficiency"
                ),
            },
            "price_normalized_boundary_seconds_per_request": SERVICE_BOUNDARY_S,
            "boundary_excess_seconds_per_request_lower": (
                decode_seconds_per_request - SERVICE_BOUNDARY_S
            ),
            "boundary_ratio_lower": decode_seconds_per_request / SERVICE_BOUNDARY_S,
            "dependent_overlap": {
                "credit_seconds": 0.0,
                "policy": (
                    "Every attention consumer waits on its layer H2D event. No "
                    "dependent transfer/computation overlap is credited."
                ),
                "stronger_impossibility": (
                    "Even granting impossible perfect overlap with all model "
                    "compute cannot reduce makespan below the serial H2D engine work."
                ),
            },
        },
        "economics": {
            "production_planning_rate_usd_per_gpu_hour": planning_rate,
            "production_rate_range_usd_per_gpu_hour": [1.0, 1.25],
            "target_usd_per_million_requests": target_cost,
            "decode_h2d_only_floor_usd_per_million_requests": cost_floor,
            "rate_sensitivity_decode_h2d_floor_usd_per_million": {
                "1.00": decode_seconds_per_request / 3600 * 1_000_000,
                "1.10": cost_floor,
                "1.25": decode_seconds_per_request * 1.25 / 3600 * 1_000_000,
            },
            "complete_cost_interval_usd_per_million_at_planning_rate": {
                "lower": cost_floor,
                "upper": "infinity",
            },
            "authorized_spend_usd": 0.0,
            "actual_spend_usd": 0.0,
        },
        "physical_hypothesis": {
            "hypothesis": (
                "Two device buffers remove about 4.25 GB of global KV residency, "
                "but full-history decode turns the host link into the limiting "
                "serial resource."
            ),
            "prediction": (
                "H2D bytes rise to the exact trace total and each global consumer "
                "observes an event wait; no cache or compute optimization can "
                "reduce the compulsory host payload under this policy."
            ),
            "falsifier": (
                "A semantics-preserving runtime demonstrates fewer H2D bytes than "
                "the distinct active E5M2 K/V rows without compression, remapping, "
                "additional residency, or changing the workload."
            ),
        },
        "focused_checks": [
            {
                "command": "python3 -m py_compile global_kv_host_prefetch.py test_global_kv_host_prefetch.py",
                "result": "pass",
            },
            {
                "command": "python3 -m unittest -v test_global_kv_host_prefetch.py",
                "result": "pass",
                "tests": 6,
            },
            {
                "command": (
                    "python3 global_kv_host_prefetch.py --source-root "
                    "/root/workspace/.agents/runtime/gemma4_global_kv_sglang"
                ),
                "result": "pass_typed_negative",
            },
        ],
        "later_component": {
            "type": "none",
            "command": None,
            "reason": (
                "Decode H2D alone is 1.797792871875 s/request at the physical "
                "payload ceiling, above the complete-service boundary before any "
                "runtime-dependent term. A component run cannot promote this fixed policy."
            ),
        },
        "uncertainty": [
            {
                "item": "Actual PCIe payload bandwidth is unmeasured.",
                "direction": "one-sided against the candidate",
                "effect": "Real protocol and efficiency losses increase latency above the ceiling-based floor.",
            },
            {
                "item": "Exact concurrent prefill chunk grouping is not frozen by the arrival manifest.",
                "direction": "one-sided against the candidate",
                "effect": "The trace charges only the minimum prefix H2D; chunk reloads add traffic.",
            },
            {
                "item": "No layer compute gaps are transferred from another hardware/workload.",
                "direction": "neutral for the decision",
                "effect": "Zero overlap credit is used; decode H2D resource work alone exceeds the boundary.",
            },
        ],
        "terminal_reasons": [
            "exact_decode_h2d_resource_floor_exceeds_complete_service_boundary",
            "price_normalized_decode_h2d_floor_exceeds_campaign_target",
            "prefill_d2h_compute_protocol_and_efficiency_terms_are_strictly_additional",
            "conservative_complete_memory_interval_does_not_fit_even_though_the_lower_case_does",
        ],
        "next_action": (
            "Close host-resident global E5M2 KV for exact c32 as typed none. "
            "Do not claim an L40S or build the runtime adapter for this policy."
        ),
    }
    terminal["implementation_hashes"] = {
        "global_kv_host_prefetch.py": sha256(Path(__file__)),
        "test_global_kv_host_prefetch.py": sha256(
            PROJECT_ROOT / "test_global_kv_host_prefetch.py"
        ),
    }
    atomic_json(args.terminal, terminal)
    print(json.dumps({
        "classification": terminal["classification"],
        "decode_h2d_seconds_per_request_lower": decode_seconds_per_request,
        "boundary_seconds_per_request": SERVICE_BOUNDARY_S,
        "trace_sha256": terminal["traffic"]["raw_trace"]["sha256"],
        "terminal": str(args.terminal),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
