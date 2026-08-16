#!/usr/bin/env python3

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
PROJECTS = PROJECT.parent
LAB = PROJECTS.parent
REPO = PROJECT.parents[6]

PACKET_PROJECT = PROJECTS / "gemma4_h100_v0515_ngram_price_normalized"
PACKET = PACKET_PROJECT / "packet" / "candidate-v0.5.15"
CONFIG = PACKET_PROJECT / "inputs" / "checkpoint" / "config.json"
REQUESTS = PACKET / "inputs" / "requests.jsonl"
SEMANTIC_ROWS = PACKET / "inputs" / "exact_semantic_rows.jsonl"
GEMMA_SOURCE = PACKET / "source/python/sglang/srt/models/gemma4_causal.py"
HYBRID_SOURCE = (
    PACKET / "source/python/sglang/srt/layers/attention/hybrid_attn_backend.py"
)
TRITON_BACKEND = (
    PACKET / "source/python/sglang/srt/layers/attention/triton_backend.py"
)
PACKET_MANIFEST = PACKET_PROJECT / "PACKET_MANIFEST.json"
EXTEND_SOURCE = (
    PROJECTS
    / "gemma4_b200_v0515_price_normalized_fit"
    / "evidence/official-v0.5.15/python/sglang/srt/layers/attention"
    / "triton_ops/extend_attention.py"
)
EXTEND_SOURCE_BINDING = (
    PROJECTS / "gemma4_b200_v0515_price_normalized_fit" / "B200_SUPPORT_FIT.json"
)
RING_TERMINAL = (
    PROJECTS
    / "gemma4_h200_swa_contiguous_ring_cache"
    / "artifacts/RING_PRODUCER_BINDING_FINAL_TERMINAL.json"
)
ACCELERATOR_INVENTORY = REPO / "research/factory/data/accelerator_inventory.json"

MIB = 1024**2
GIB = 1024**3


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_jsonl(path: Path):
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def find_accelerator(node, accelerator_id: str):
    if isinstance(node, dict):
        if node.get("id") == accelerator_id:
            return node
        for value in node.values():
            match = find_accelerator(value, accelerator_id)
            if match is not None:
                return match
    elif isinstance(node, list):
        for value in node:
            match = find_accelerator(value, accelerator_id)
            if match is not None:
                return match
    return None


def source_binding():
    paths = {
        "analysis_script": Path(__file__).resolve(),
        "test_script": Path(__file__).resolve().with_name(
            "test_analyze_l2_residency.py"
        ),
        "packet_manifest": PACKET_MANIFEST,
        "checkpoint_config": CONFIG,
        "requests": REQUESTS,
        "exact_semantic_rows": SEMANTIC_ROWS,
        "gemma4_causal": GEMMA_SOURCE,
        "hybrid_attn_backend": HYBRID_SOURCE,
        "triton_backend": TRITON_BACKEND,
        "extend_attention_auxiliary_same_commit_snapshot": EXTEND_SOURCE,
        "extend_attention_auxiliary_binding": EXTEND_SOURCE_BINDING,
        "prior_contiguous_ring_terminal_mechanism_separation": RING_TERMINAL,
        "accelerator_inventory": ACCELERATOR_INVENTORY,
    }
    return {
        name: {
            "path": str(path.relative_to(REPO)),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
        for name, path in paths.items()
    }


def request_geometry():
    requests = load_jsonl(REQUESTS)
    semantic_rows = load_jsonl(SEMANTIC_ROWS)
    if len(requests) != len(semantic_rows):
        raise ValueError("request and semantic row counts differ")

    usages = [row["usage"] for row in requests]
    unique_usage = {
        (row["prompt_tokens"], row["completion_tokens"], row["total_tokens"])
        for row in usages
    }
    if len(unique_usage) != 1:
        raise ValueError("bound request token geometry is not constant")
    prompt_tokens, completion_tokens, total_tokens = unique_usage.pop()

    release_groups = Counter(row["released_s"] for row in semantic_rows)
    release_group_histogram = Counter(release_groups.values())
    group_sizes = sorted(release_groups.values(), reverse=True)
    representative_indices = [0, 31, len(semantic_rows) // 2, len(semantic_rows) - 12, len(semantic_rows) - 1]
    representative_rows = []
    for index in representative_indices:
        row = semantic_rows[index]
        representative_rows.append(
            {
                "row_index": index,
                "request_id": row["i"],
                "arrival_s": row["arrival_s"],
                "released_s": row["released_s"],
                "server_seconds": row["server_seconds"],
                "prompt_tokens": row["semantic"]["usage"]["prompt_tokens"],
                "completion_tokens": row["semantic"]["usage"]["completion_tokens"],
            }
        )

    return {
        "rows": len(requests),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "release_group_count": len(release_groups),
        "release_group_size_histogram": {
            str(size): count for size, count in sorted(release_group_histogram.items())
        },
        "full_group_size": group_sizes[0],
        "tail_group_size": group_sizes[-1],
        "representative_rows": representative_rows,
    }


def model_geometry():
    config = json.loads(CONFIG.read_text())
    text = config["text_config"]
    layer_types = text["layer_types"]
    local_ids = [
        layer_id
        for layer_id, layer_type in enumerate(layer_types)
        if layer_type == "sliding_attention"
    ]
    global_ids = [
        layer_id
        for layer_id, layer_type in enumerate(layer_types)
        if layer_type == "full_attention"
    ]
    expected_global_ids = list(range(5, len(layer_types), 6))
    if global_ids != expected_global_ids:
        raise ValueError("layer cadence is not five-local/one-global")
    if text.get("num_kv_shared_layers") != 0:
        raise ValueError("local layers unexpectedly share KV")

    return {
        "layers": len(layer_types),
        "local_layer_ids": local_ids,
        "global_layer_ids": global_ids,
        "cadence": [
            {
                "group": group,
                "local_layer_ids": list(range(group * 6, group * 6 + 5)),
                "global_layer_id": group * 6 + 5,
            }
            for group in range(len(layer_types) // 6)
        ],
        "query_heads": text["num_attention_heads"],
        "local_kv_heads": text["num_key_value_heads"],
        "local_head_dim": text["head_dim"],
        "global_kv_heads": text["num_global_key_value_heads"],
        "global_head_dim": text["global_head_dim"],
        "configured_semantic_window_tokens": text["sliding_window"],
        "runtime_prefix_window_tokens": text["sliding_window"] - 1,
        "kv_shared_layers": text["num_kv_shared_layers"],
        "kv_dtype": "fp8_e5m2",
        "kv_element_bytes": 1,
        "page_size_tokens": 1,
        "ngram_verify_depth": 12,
        "hopper_extend_block_m": 64,
        "hopper_extend_block_n": 64,
    }


def synthetic_address_examples(geometry, batch_size: int, seq_len: int):
    window = geometry["runtime_prefix_window_tokens"]
    kv_heads = geometry["local_kv_heads"]
    head_dim = geometry["local_head_dim"]
    row_bytes_one_tensor = kv_heads * head_dim
    ring_slots_per_request = geometry["configured_semantic_window_tokens"]
    suffix_start = seq_len - window

    examples = []
    for lane in (0, batch_size - 1):
        for logical_position in (suffix_start, suffix_start + 1, seq_len - 1):
            stock_slot = logical_position * batch_size + lane + 1
            ring_slot = lane * ring_slots_per_request + (
                logical_position % ring_slots_per_request
            )
            examples.append(
                {
                    "request_lane": lane,
                    "logical_position": logical_position,
                    "stock_synthetic_physical_slot": stock_slot,
                    "stock_k_byte_address_offset": stock_slot
                    * row_bytes_one_tensor,
                    "ring_physical_slot": ring_slot,
                    "ring_k_byte_address_offset": ring_slot
                    * row_bytes_one_tensor,
                }
            )

    return {
        "classification": "synthetic",
        "dependency_note": (
            "The stock round-robin slot formula is an explicit deterministic "
            "fragmentation fixture, not a claim about realized allocator order. "
            "All promotion decisions below depend only on unique bytes and source "
            "ownership, which are invariant to this permutation."
        ),
        "stock_layout": (
            "page-size-one layer buffers addressed as "
            "buffer[req_to_token[request_slot, logical_position], kv_head, dim]"
        ),
        "candidate_layout_considered": (
            "local-only request-owned circular "
            "buffer[layer, request_generation, ring_token, kv_head, dim]"
        ),
        "stock_chronological_k_address_stride_bytes_in_fixture": batch_size
        * row_bytes_one_tensor,
        "ring_chronological_k_address_stride_bytes": row_bytes_one_tensor,
        "examples": examples,
        "trace_sha256": canonical_sha256(examples),
    }


def batch_working_set(geometry, batch_size: int, l2_mib: int):
    prefix_tokens = geometry["runtime_prefix_window_tokens"]
    semantic_tokens = geometry["configured_semantic_window_tokens"]
    local_layers = len(geometry["local_layer_ids"])
    local_token_bytes = (
        2
        * geometry["local_kv_heads"]
        * geometry["local_head_dim"]
        * geometry["kv_element_bytes"]
    )
    global_token_bytes = (
        2
        * geometry["global_kv_heads"]
        * geometry["global_head_dim"]
        * geometry["kv_element_bytes"]
    )

    local_prefix_per_request_layer = prefix_tokens * local_token_bytes
    local_semantic_per_request_layer = semantic_tokens * local_token_bytes
    local_prefix_per_layer_batch = batch_size * local_prefix_per_request_layer
    local_prefix_all_layers_batch = local_layers * local_prefix_per_layer_batch

    index_output_bytes = batch_size * prefix_tokens * 8 * local_layers
    metadata_upper_bytes = batch_size * prefix_tokens * 24 * local_layers
    persistent_upper_bytes = min(l2_mib * MIB, local_prefix_all_layers_batch)

    per_kv_head_request = (
        prefix_tokens
        * 2
        * geometry["local_head_dim"]
        * geometry["kv_element_bytes"]
    )
    paired_head_reuse_footprint = batch_size * per_kv_head_request

    return {
        "batch_size": batch_size,
        "local_kv_bytes_per_token": local_token_bytes,
        "global_kv_bytes_per_token": global_token_bytes,
        "local_prefix_hot_bytes_per_request_per_layer": local_prefix_per_request_layer,
        "local_prefix_hot_mib_per_request_per_layer": local_prefix_per_request_layer
        / MIB,
        "local_semantic_window_bytes_per_request_per_layer": local_semantic_per_request_layer,
        "local_semantic_window_mib_per_request_per_layer": local_semantic_per_request_layer
        / MIB,
        "local_prefix_hot_bytes_per_layer_batch": local_prefix_per_layer_batch,
        "local_prefix_hot_mib_per_layer_batch": local_prefix_per_layer_batch / MIB,
        "local_prefix_hot_bytes_all_50_layers_batch": local_prefix_all_layers_batch,
        "local_prefix_hot_gib_all_50_layers_batch": local_prefix_all_layers_batch
        / GIB,
        "page_index_output_bytes_all_50_layers": index_output_bytes,
        "page_index_output_to_kv_fraction": index_output_bytes
        / local_prefix_all_layers_batch,
        "all_ownership_metadata_upper_bytes": metadata_upper_bytes,
        "all_ownership_metadata_upper_to_kv_fraction": metadata_upper_bytes
        / local_prefix_all_layers_batch,
        "paired_query_head_reuse_footprint_bytes": paired_head_reuse_footprint,
        "paired_query_head_reuse_footprint_mib": paired_head_reuse_footprint
        / MIB,
        "paired_query_head_reuse_fits_l2": paired_head_reuse_footprint
        <= l2_mib * MIB,
        "ideal_persistent_l2_saved_bytes_upper": persistent_upper_bytes,
        "ideal_persistent_l2_saved_fraction_of_local_unique_bytes": persistent_upper_bytes
        / local_prefix_all_layers_batch,
        "ideal_persistence_plus_all_metadata_upper_fraction": (
            persistent_upper_bytes + metadata_upper_bytes
        )
        / local_prefix_all_layers_batch,
        "local_unique_hbm_time_floor_ms_at_3350_gb_s": (
            local_prefix_all_layers_batch / 3_350_000_000_000 * 1000
        ),
        "ideal_persistent_l2_time_saved_upper_ms_at_3350_gb_s": (
            persistent_upper_bytes / 3_350_000_000_000 * 1000
        ),
    }


def workload_weighted_bound(geometry, requests, l2_mib: int):
    histogram = {
        int(size): count
        for size, count in requests["release_group_size_histogram"].items()
    }
    total_unique = 0
    total_persistent_upper = 0
    total_metadata_upper = 0
    for batch_size, groups in histogram.items():
        row = batch_working_set(geometry, batch_size, l2_mib)
        total_unique += groups * row["local_prefix_hot_bytes_all_50_layers_batch"]
        total_persistent_upper += groups * row["ideal_persistent_l2_saved_bytes_upper"]
        total_metadata_upper += groups * row["all_ownership_metadata_upper_bytes"]
    return {
        "l2_mib_available": l2_mib,
        "exact_release_groups": histogram,
        "local_unique_bytes": total_unique,
        "ideal_persistent_l2_saved_bytes_upper": total_persistent_upper,
        "all_ownership_metadata_upper_bytes": total_metadata_upper,
        "ideal_persistence_fraction": total_persistent_upper / total_unique,
        "ideal_persistence_plus_all_metadata_upper_fraction": (
            total_persistent_upper + total_metadata_upper
        )
        / total_unique,
    }


def build_result():
    binding = source_binding()
    if (
        binding["packet_manifest"]["sha256"]
        != "8127631191fe1afc47e718502ff61980b1e51adb8ac43c2f28e140ff506173bd"
    ):
        raise ValueError("packet manifest identity changed")
    expected_hashes = {
        "checkpoint_config": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
        "requests": "10e7edacaa194fd0f43b3a3c38f7d91cec0ceba22df8e08e3b5897b174346135",
        "exact_semantic_rows": "630d05bd860d1dd22c3e35ba2d8f792afc5051f0c68e0a74a9deda8140a02b36",
        "gemma4_causal": "9b7fccf2f35a57aa16de0fbc3abc0ca84b5fe34431535e26eea13a27b2cfda2e",
        "hybrid_attn_backend": "9ed86790c5f00ce6b156aa7eccbe716f03fe49f6eacda805f47f3d277ea4ff04",
        "triton_backend": "c09161c77e4586064c0d70c5dda4f943378510a4facb187590ac31e17b0e6e73",
        "extend_attention_auxiliary_same_commit_snapshot": "2f4a934625b38d2e797a92c5966270c4d36ebfce9dc0093fb83bf18b140e9f28",
        "extend_attention_auxiliary_binding": "8a823687d9cd4c3726443ab1c8e4245a1eb4e9c5293094f5a9f8b49385685df1",
        "prior_contiguous_ring_terminal_mechanism_separation": "c5d6e7093dd717239471133cfa7280afd4c7bb56bc26911a7c282d7b5287b8d6",
    }
    for name, expected in expected_hashes.items():
        if binding[name]["sha256"] != expected:
            raise ValueError(f"{name} identity changed")

    extend_binding = json.loads(EXTEND_SOURCE_BINDING.read_text())
    extend_record = extend_binding["official_source_manifest"][
        "python/sglang/srt/layers/attention/triton_ops/extend_attention.py"
    ]
    if (
        extend_binding["identity"]["runtime_commit"]
        != "f63458b5beaceabbd9d749b9fc956370e1b649e6"
        or extend_record["sha256"]
        != binding["extend_attention_auxiliary_same_commit_snapshot"]["sha256"]
    ):
        raise ValueError("auxiliary extend source is not bound to v0.5.15")

    requests = request_geometry()
    geometry = model_geometry()
    accelerator = find_accelerator(
        json.loads(ACCELERATOR_INVENTORY.read_text()), "nvidia-h100-sxm"
    )
    if accelerator is None:
        raise ValueError("H100 SXM accelerator record missing")
    l2_mib = accelerator["cache"]["last_level_mb"]

    scenarios = [
        workload_weighted_bound(geometry, requests, available)
        for available in (25, 30, 40, l2_mib)
    ]
    representative_batches = [
        batch_working_set(geometry, batch_size, l2_mib)
        for batch_size in (1, requests["tail_group_size"], requests["full_group_size"])
    ]
    full_batch = representative_batches[-1]
    full_l2_upper = scenarios[-1]

    material_local_byte_gate = 0.01
    passes_material_gate = (
        full_l2_upper["ideal_persistence_plus_all_metadata_upper_fraction"]
        >= material_local_byte_gate
    )
    if passes_material_gate:
        raise AssertionError("typed-none falsifier unexpectedly passed material gate")

    return {
        "schema_version": 1,
        "result": "typed_none",
        "typed_none": {
            "type": "l2_capacity_and_native_query_tiling_defeat_material_residency",
            "scope_closed": (
                "H100 L2-resident local-KV layout/access scheduling for the exact "
                "v0.5.15 Gemma 4 NGRAM workload; contiguous-ring addressing remains "
                "a distinct already-measured coalescing/index mechanism."
            ),
            "material_gate": (
                "At least 1% reduction of non-overlapping local-KV bytes on the "
                "exact release-group distribution, before any endpoint claim."
            ),
            "material_gate_fraction": material_local_byte_gate,
            "optimistic_full_50_mib_l2_plus_all_metadata_fraction": full_l2_upper[
                "ideal_persistence_plus_all_metadata_upper_fraction"
            ],
            "gate_pass": passes_material_gate,
        },
        "evidence_labels": {
            "source_and_geometry": "derived",
            "address_examples": "synthetic",
            "hbm_and_l2_bytes": "analytical upper/lower bounds",
            "endpoint_speedup": "not measured and not claimed",
            "live_h100": "not used or mutated",
        },
        "source_binding": binding,
        "runtime_identity": {
            "sglang_commit": "f63458b5beaceabbd9d749b9fc956370e1b649e6",
            "image": (
                "docker.io/lmsysorg/sglang@sha256:"
                "ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
            ),
            "model": (
                "google/gemma-4-31B-it@"
                "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
            ),
        },
        "accelerator": {
            "id": accelerator["id"],
            "sms": accelerator["execution"]["compute_units"],
            "l2_mib": l2_mib,
            "hbm_capacity_gb": accelerator["memory"]["capacity_gb"],
            "hbm_bandwidth_gb_s": accelerator["memory"]["bandwidth_gb_s"],
        },
        "model_geometry": geometry,
        "request_geometry": requests,
        "source_reconstruction": {
            "cadence": (
                "The checkpoint layer_types are ten exact repetitions of five "
                "sliding_attention layers followed by one full_attention layer."
            ),
            "processed_head_geometry": (
                "Gemma raw base fields describe local attention (16 KV heads, "
                "head dimension 256); SGLang preserves them as swa_* and maps "
                "global_* to the full path (4 KV heads, head dimension 512)."
            ),
            "window": (
                "Gemma returns configured sliding_window - 1 = 1023 as the prefix "
                "window because its semantic 1024-token window is inclusive of the "
                "current/extend token."
            ),
            "ownership": (
                "req_pool_indices select request rows; req_to_token[row, logical "
                "position] owns page-size-one token locations. The backend gathers "
                "the last min(seq_len, 1023) locations and, for SWAKVPool, translates "
                "full locations to SWA locations before the layer buffer consumer."
            ),
            "producer": (
                "Gemma4Attention forwards layer-specific K/V with save_kv_cache; "
                "TritonAttnBackend._set_kv_buffer writes through KVWriteLoc to the "
                "layer buffer. No KV sharing is configured."
            ),
            "consumer": (
                "TritonAttnBackend.forward_decode selects window_kv_indptr/indices "
                "for local layers and full kv_indptr/indices for global layers, then "
                "passes the layer-specific K/V buffers to decode_attention_fwd. "
                "Target verification uses extend_attention_fwd."
            ),
            "native_reuse": (
                "On Hopper and local head dimension 256, extend_attention uses "
                "BLOCK_M=64 and BLOCK_N=64. The 12 NGRAM queries fit one M tile, "
                "so a CTA streams prefix K/V once for all queries. Two query heads "
                "share each KV head; their whole-batch reuse footprint is below "
                "even the 30 MiB contention scenario."
            ),
            "native_reuse_uncertainty": (
                "The fit is source-and-address-model evidence, not a measured H100 "
                "hit rate. CUDA block execution order is not a semantic guarantee; "
                "scope-matched DRAM/L2 counters that show paired-head eviction would "
                "invalidate this typed none."
            ),
        },
        "synthetic_address_model": synthetic_address_examples(
            geometry, requests["full_group_size"], requests["prompt_tokens"]
        ),
        "representative_batch_working_sets_at_full_l2": representative_batches,
        "exact_workload_l2_scenarios": scenarios,
        "physical_interpretation": {
            "compulsory_local_bytes": (
                "A local prefix is 1023 * 16 heads * 256 dimensions * K/V * "
                "one E5M2 byte = 7.9921875 MiB per request per layer. At batch "
                "32 one layer is 255.75 MiB and all 50 local layers are about "
                "12.49 GiB."
            ),
            "intra_verify_reuse": (
                "The native 64-row query tile already removes repeated prefix "
                "streams across the 12 verification queries. The remaining GQA "
                "pair reuse footprint is only about 16 MiB at batch 32 and is an "
                "ordinary transient-L2 fit, not a missing persistent layout."
            ),
            "cross_step_reuse": (
                "The same layer is revisited only after 49 other local layers, ten "
                "global layers, and intervening linear work. Distinct layer_id "
                "buffers and num_kv_shared_layers=0 forbid byte aliasing. A 50 MiB "
                "fully persistent ideal can retain only a sub-percent slice of the "
                "exact workload's local unique bytes."
            ),
            "global_separation": (
                "Global layers remain full-context, page-size-one E5M2 and are not "
                "credited as candidate savings. Their traffic and linear work only "
                "increase contention beyond the optimistic local-only bound."
            ),
        },
        "candidate_considered": {
            "name": "request_owned_local_ring_with_persisting_l2_access_window",
            "layout": (
                "[local_layer, request_generation, ring_token, kv_head, head_dim] "
                "with a 1024-token power-of-two ring; global layers unchanged."
            ),
            "source_boundaries": {
                "producer": (
                    "Gemma4Attention -> TritonAttnBackend._set_kv_buffer -> "
                    "token_to_kv_pool.set_kv_buffer"
                ),
                "allocator": (
                    "req_to_token request-row/logical-position ownership plus "
                    "SWAKVPool full-to-SWA translation"
                ),
                "consumer": (
                    "TritonAttnBackend.forward_decode/forward_extend -> "
                    "decode_attention_fwd/extend_attention_fwd"
                ),
            },
            "predicted_change": (
                "Eliminate page-one index materialization/consumption and attempt "
                "to retain selected ring lines across model steps."
            ),
            "why_not_patch": (
                "Even granting the entire 50 MiB L2 and deleting an intentionally "
                "generous 24 metadata bytes per KV token, the exact workload upper "
                "bound remains below the 1% local-byte gate. A patch cannot remove "
                "compulsory distinct-layer K/V bytes without changing semantics."
            ),
        },
        "historical_mechanism_separation": {
            "evidence": (
                "The bound H200 terminal measured a request-owned contiguous ring "
                "as a positive 3.10198225% endpoint change after exact producer "
                "binding. That result is not transferred to H100 and does not prove "
                "L2 persistence; it keeps address/coalescing work distinct from the "
                "capacity-closed residency mechanism here."
            ),
            "classification": "measured on different hardware/runtime; non-transferable",
        },
        "lifecycle_hazards": [
            {
                "hazard": "CUDA graph padding",
                "requirement": (
                    "Request slot zero and padded seq_len=1 rows must map to a sink "
                    "or -1 and no-op before K/V access; captured addresses must stay stable."
                ),
            },
            {
                "hazard": "request reuse and dynamic reorder",
                "requirement": (
                    "Ring rows need generation-tagged, collision-free ownership "
                    "independent of current batch order; release must invalidate stale tags."
                ),
            },
            {
                "hazard": "prefix sharing/restoration",
                "requirement": (
                    "req_to_token may alias shared prefix locations. A request-owned "
                    "ring must copy exact producer bytes or preserve reference-counted aliases."
                ),
            },
            {
                "hazard": "NGRAM accepted-KV settlement",
                "requirement": (
                    "The v0.5.15 scheduler remains the sole committed-length owner; "
                    "accepted-token moves and ring positions must update atomically."
                ),
            },
            {
                "hazard": "five-local/one-global transitions",
                "requirement": (
                    "Only the 50 exact local layer IDs may use the ring. The ten "
                    "global IDs retain paged full-context ownership and buffers."
                ),
            },
        ],
        "falsifier": {
            "kind": "checkpoint_free_deterministic_source_and_address_model",
            "command": "python3 analyze_l2_residency.py --check",
            "pass_condition_for_candidate": (
                "The exact release-group weighted optimistic bound, including the "
                "entire 50 MiB L2 and all ownership metadata, reaches at least 1% "
                "of local unique bytes."
            ),
            "observed": full_l2_upper[
                "ideal_persistence_plus_all_metadata_upper_fraction"
            ],
            "candidate_falsified": not passes_material_gate,
        },
        "next_distinct_measurement_if_reopened": {
            "scope": (
                "Checkpoint-free H100 exact-shape counter test only if new source "
                "introduces KV sharing, a smaller local representation, or a query "
                "tile that rereads the same prefix, or if counters contradict the "
                "paired-head transient-L2 fit."
            ),
            "required_counters": [
                "dram bytes for local extend/decode interval",
                "L2 read hit sectors",
                "candidate path identity",
            ],
            "not_authorized_now": True,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROJECT / "CAUSAL_RESULT.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    result = build_result()
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists():
            raise SystemExit(f"missing output: {args.output}")
        current = args.output.read_text()
        if current != encoded:
            raise SystemExit("CAUSAL_RESULT.json is not reproducible")
        print(
            json.dumps(
                {
                    "result": result["result"],
                    "candidate_falsified": result["falsifier"][
                        "candidate_falsified"
                    ],
                    "observed_upper_fraction": result["falsifier"]["observed"],
                    "output_sha256": hashlib.sha256(current.encode()).hexdigest(),
                },
                sort_keys=True,
            )
        )
        return

    args.output.write_text(encoded)
    print(args.output)


if __name__ == "__main__":
    main()
