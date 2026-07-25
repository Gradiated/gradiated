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
PACKET = PACKET_PROJECT / "packet/candidate-v0.5.15"
REQUESTS = PACKET / "inputs/requests.jsonl"
SEMANTIC_ROWS = PACKET / "inputs/exact_semantic_rows.jsonl"
PACKET_MANIFEST = PACKET_PROJECT / "PACKET_MANIFEST.json"
CONFIG = PACKET_PROJECT / "inputs/checkpoint/config.json"
L2_RESULT = PROJECTS / "gemma4_h100_local_kv_l2_residency/CAUSAL_RESULT.json"
RING_TERMINAL = (
    PROJECTS
    / "gemma4_h200_swa_contiguous_ring_cache"
    / "artifacts/RING_PRODUCER_BINDING_FINAL_TERMINAL.json"
)
ACCELERATOR_INVENTORY = REPO / "research/factory/data/accelerator_inventory.json"
CHECKOUT = REPO / ".agents/runtime/sglang-v0.5.15-full-checkout"
COMMIT = "f63458b5beaceabbd9d749b9fc956370e1b649e6"

WINDOW = 1023
RING_TOKENS = 1024
LOCAL_LAYERS = 50
QUERY_HEADS = 32
KV_HEADS = 16
HEAD_DIM = 256
KV_ELEMENT_BYTES = 1
KV_ROW_BYTES = KV_HEADS * HEAD_DIM * KV_ELEMENT_BYTES
KV_TOKEN_BYTES = 2 * KV_ROW_BYTES
INDEX_ELEMENT_BYTES = 8
SECTOR_BYTES = 32
TRANSACTION_BYTES = 128
NGRAM_DEPTH = 12

SOURCE_FILES = {
    "memory_pool": "python/sglang/srt/mem_cache/memory_pool.py",
    "token_allocator": "python/sglang/srt/mem_cache/allocator/token.py",
    "swa_allocator": "python/sglang/srt/mem_cache/allocator/swa.py",
    "allocation_call_sites": "python/sglang/srt/mem_cache/common.py",
    "swa_pool": "python/sglang/srt/mem_cache/swa_memory_pool.py",
    "triton_backend": "python/sglang/srt/layers/attention/triton_backend.py",
    "extend_consumer": (
        "python/sglang/srt/layers/attention/triton_ops/extend_attention.py"
    ),
    "decode_consumer": (
        "python/sglang/srt/layers/attention/triton_ops/decode_attention.py"
    ),
    "kv_indices_producer": (
        "python/sglang/srt/layers/attention/triton_ops/kv_indices.py"
    ),
    "gemma4_model": "python/sglang/srt/models/gemma4_causal.py",
}

EXPECTED_SOURCE_HASHES = {
    "memory_pool": "7e585c4c5870ac84a048069e61bfd9892f2c638b2d89964e927d2c554f3f951e",
    "token_allocator": "8e9c936a0e51307eae876dcf175ed91f6e505a77b2c8a3a2e3f390d0440916a9",
    "swa_allocator": "43c41e269dd3d8eefd3131c457aff5c0458c37524e1f23242b25e21ceb16429b",
    "allocation_call_sites": "2dce58dd6f323208e34801e044ae087d6d032464efd01342c604efea3de156df",
    "swa_pool": "1a43bf0ef33319d3a8094026b0457c7282c9cd650acf60d335724ee1dd6043fd",
    "triton_backend": "c09161c77e4586064c0d70c5dda4f943378510a4facb187590ac31e17b0e6e73",
    "extend_consumer": "2f4a934625b38d2e797a92c5966270c4d36ebfce9dc0093fb83bf18b140e9f28",
    "decode_consumer": "4ecf5d81f06fcc8aa36479541ff3857a1416e2d8def2c5fa818808148febaa75",
    "kv_indices_producer": "ab8bd0fc5e2aa00a86b242368e2e701d660df938b72e950226294fa5594b3c48",
    "gemma4_model": "9b7fccf2f35a57aa16de0fbc3abc0ca84b5fe34431535e26eea13a27b2cfda2e",
}

SOURCE_SYMBOLS = {
    "memory_pool": ["class ReqToTokenPool", "dtype=torch.int32"],
    "token_allocator": [
        "class TokenToKVPoolAllocator",
        "select_index = self.free_pages[:need_size]",
        "self.free_pages = torch.cat",
    ],
    "swa_allocator": [
        "class SWATokenToKVPoolAllocator",
        "full_to_swa_index_mapping",
    ],
    "allocation_call_sites": [
        "if _alloc_page_size(batch) == 1:",
        "alloc_token_slots",
    ],
    "swa_pool": [
        "class SWAKVPool",
        "translate_loc_from_full_to_swa",
        "set_kv_buffer",
    ],
    "triton_backend": [
        "def update_sliding_window_buffer",
        "dtype=torch.int64",
        "forward_extend",
        "forward_decode",
    ],
    "extend_consumer": [
        "offs_kv_loc = tl.load",
        "BLOCK_M, BLOCK_N = (64, 64)",
        "grid = (batch_size, head_num",
    ],
    "decode_consumer": [
        "kv_loc = tl.load",
        "BLOCK_H = 16",
        "decode_attention_fwd_grouped",
    ],
    "kv_indices_producer": ["create_flashinfer_kv_indices_triton"],
    "gemma4_model": [
        "def get_attention_sliding_window_size",
        "return config.sliding_window - 1",
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_jsonl(path: Path):
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def source_binding():
    head = (
        __import__("subprocess")
        .run(
            ["git", "-C", str(CHECKOUT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    if head != COMMIT:
        raise ValueError(f"checkout commit changed: {head}")

    result = {}
    for name, relative in SOURCE_FILES.items():
        path = CHECKOUT / relative
        digest = sha256(path)
        if digest != EXPECTED_SOURCE_HASHES[name]:
            raise ValueError(f"{name} hash changed: {digest}")
        text = path.read_text()
        missing = [symbol for symbol in SOURCE_SYMBOLS[name] if symbol not in text]
        if missing:
            raise ValueError(f"{name} source symbols missing: {missing}")
        result[name] = {
            "git_path": relative,
            "git_commit": COMMIT,
            "workspace_path": str(path.relative_to(REPO)),
            "sha256": digest,
            "bytes": path.stat().st_size,
            "required_symbols": SOURCE_SYMBOLS[name],
        }

    auxiliary = {
        "analysis_script": Path(__file__).resolve(),
        "test_script": Path(__file__).resolve().with_name(
            "test_analyze_transactions.py"
        ),
        "packet_manifest": PACKET_MANIFEST,
        "checkpoint_config": CONFIG,
        "requests": REQUESTS,
        "exact_semantic_rows": SEMANTIC_ROWS,
        "h100_l2_result": L2_RESULT,
        "h200_ring_terminal": RING_TERMINAL,
        "accelerator_inventory": ACCELERATOR_INVENTORY,
    }
    return {
        "runtime_sources": result,
        "auxiliary": {
            name: {
                "path": str(path.relative_to(REPO)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for name, path in auxiliary.items()
        },
    }


def source_line_numbers(binding):
    result = {}
    for name, record in binding["runtime_sources"].items():
        lines = (REPO / record["workspace_path"]).read_text().splitlines()
        result[name] = {
            symbol: next(
                index
                for index, line in enumerate(lines, start=1)
                if symbol in line
            )
            for symbol in record["required_symbols"]
        }
    return result


def request_geometry():
    requests = load_jsonl(REQUESTS)
    semantic_rows = load_jsonl(SEMANTIC_ROWS)
    if len(requests) != 1036 or len(requests) != len(semantic_rows):
        raise ValueError("the exact trace is not 1,036 paired rows")
    usage = {
        (
            row["usage"]["prompt_tokens"],
            row["usage"]["completion_tokens"],
            row["usage"]["total_tokens"],
        )
        for row in requests
    }
    if usage != {(4214, 358, 4572)}:
        raise ValueError(f"request geometry changed: {usage}")
    release_counts = Counter(row["released_s"] for row in semantic_rows)
    histogram = Counter(release_counts.values())
    if histogram != Counter({32: 32, 12: 1}):
        raise ValueError(f"release groups changed: {histogram}")
    return {
        "rows": len(requests),
        "prompt_tokens": 4214,
        "completion_tokens": 358,
        "total_tokens": 4572,
        "release_group_size_histogram": {
            str(size): count for size, count in sorted(histogram.items())
        },
        "release_group_count": len(release_counts),
        "request_sha256_unique": len(
            {row["request_sha256"] for row in requests}
        ),
        "internal_scheduler_trace_present": False,
        "missing_internal_fields": [
            "forward batch membership and request order",
            "chunked-prefill boundaries",
            "per-step accepted NGRAM depth",
            "allocator alloc/free/evict events",
            "req_to_token and full_to_swa values",
        ],
    }


def units_touched(start: int, length: int, unit: int) -> int:
    if length <= 0:
        return 0
    return (start % unit + length + unit - 1) // unit


def release_group_alignment(group_size: int):
    index_bytes = WINDOW * INDEX_ELEMENT_BYTES
    sectors = [
        units_touched(lane * index_bytes, index_bytes, SECTOR_BYTES)
        for lane in range(group_size)
    ]
    transactions = [
        units_touched(lane * index_bytes, index_bytes, TRANSACTION_BYTES)
        for lane in range(group_size)
    ]
    return {
        "group_size": group_size,
        "index_bytes_per_request": index_bytes,
        "sector_counts_by_request_lane": Counter(sectors),
        "transaction_counts_by_request_lane": Counter(transactions),
        "sectors_per_one_consumer_stream": sum(sectors),
        "transactions_per_one_consumer_stream": sum(transactions),
    }


def aggregate_alignment(requests):
    histogram = {
        int(size): count
        for size, count in requests["release_group_size_histogram"].items()
    }
    group_rows = {
        size: release_group_alignment(size) for size in sorted(histogram)
    }
    sectors = sum(
        histogram[size] * group_rows[size]["sectors_per_one_consumer_stream"]
        for size in histogram
    )
    transactions = sum(
        histogram[size]
        * group_rows[size]["transactions_per_one_consumer_stream"]
        for size in histogram
    )
    return group_rows, sectors, transactions


def phase_model(
    *,
    name: str,
    steps_per_request: int,
    index_streams_per_request_layer_step: int,
    payload_request_multiplier: int,
    requests,
    aligned_sectors_per_stream,
    aligned_transactions_per_stream,
):
    rows = requests["rows"]
    request_layer_steps = rows * steps_per_request * LOCAL_LAYERS
    consumer_streams = request_layer_steps * index_streams_per_request_layer_step
    unique_payload_bytes = request_layer_steps * WINDOW * KV_TOKEN_BYTES
    requested_payload_bytes = unique_payload_bytes * payload_request_multiplier
    payload_sectors = requested_payload_bytes // SECTOR_BYTES
    payload_transactions = requested_payload_bytes // TRANSACTION_BYTES

    group_count_scale = steps_per_request * LOCAL_LAYERS
    stock_index_sectors = (
        aligned_sectors_per_stream
        * index_streams_per_request_layer_step
        * group_count_scale
    )
    stock_index_transactions = (
        aligned_transactions_per_stream
        * index_streams_per_request_layer_step
        * group_count_scale
    )
    ideal_ring_metadata_sectors = consumer_streams
    ideal_ring_metadata_transactions = consumer_streams
    stock_total_sectors = payload_sectors + stock_index_sectors
    ring_total_sectors = payload_sectors + ideal_ring_metadata_sectors
    stock_total_transactions = payload_transactions + stock_index_transactions
    ring_total_transactions = payload_transactions + ideal_ring_metadata_transactions

    producer_lower_bytes = rows * steps_per_request * WINDOW * (4 + 8 + 8)
    producer_upper_bytes = rows * steps_per_request * WINDOW * 52
    ring_producer_metadata_bytes = rows * steps_per_request * 8

    return {
        "name": name,
        "steps_per_request": steps_per_request,
        "request_layer_steps": request_layer_steps,
        "index_streams_per_request_layer_step": index_streams_per_request_layer_step,
        "consumer_streams": consumer_streams,
        "payload_request_multiplier": payload_request_multiplier,
        "compulsory_unique_payload_bytes": unique_payload_bytes,
        "kernel_requested_payload_bytes": requested_payload_bytes,
        "producer_metadata_bytes": {
            "stock_source_minimum": producer_lower_bytes,
            "stock_eager_temporary_upper": producer_upper_bytes,
            "ideal_ring_packed_request_generation": ring_producer_metadata_bytes,
            "scope": "once per model forward, not once per layer",
        },
        "stock": {
            "payload_sectors_32b": payload_sectors,
            "payload_transactions_128b": payload_transactions,
            "index_requested_bytes": (
                consumer_streams * WINDOW * INDEX_ELEMENT_BYTES
            ),
            "index_sectors_32b": stock_index_sectors,
            "index_transactions_128b": stock_index_transactions,
            "total_sectors_32b": stock_total_sectors,
            "total_transactions_128b": stock_total_transactions,
        },
        "ideal_request_owned_ring": {
            "payload_sectors_32b": payload_sectors,
            "payload_transactions_128b": payload_transactions,
            "packed_metadata_requested_bytes": consumer_streams * 8,
            "metadata_sectors_32b": ideal_ring_metadata_sectors,
            "metadata_transactions_128b": ideal_ring_metadata_transactions,
            "total_sectors_32b": ring_total_sectors,
            "total_transactions_128b": ring_total_transactions,
        },
        "predicted_reduction": {
            "payload_bytes": 0,
            "payload_sectors_32b": 0,
            "payload_transactions_128b": 0,
            "metadata_sectors_32b": (
                stock_index_sectors - ideal_ring_metadata_sectors
            ),
            "metadata_transactions_128b": (
                stock_index_transactions - ideal_ring_metadata_transactions
            ),
            "fraction_of_stock_requested_sectors": (
                stock_total_sectors - ring_total_sectors
            )
            / stock_total_sectors,
            "fraction_of_stock_requested_transactions": (
                stock_total_transactions - ring_total_transactions
            )
            / stock_total_transactions,
        },
    }


def payload_mapping_oracle():
    stock_schedules = {
        "initial_contiguous": list(range(1, 1 + WINDOW)),
        "chunk_segments": (
            list(range(1, 513))
            + list(range(4097, 4097 + 256))
            + list(range(8193, 8193 + 255))
        ),
        "recycled_permutation": [
            1 + ((position * 509) % 4093) for position in range(WINDOW)
        ],
    }
    head_ids = (0, 1, 15)
    schedule_rows = []
    for schedule_name, slots in stock_schedules.items():
        if len(slots) != WINDOW or len(set(slots)) != WINDOW:
            raise ValueError(f"invalid oracle schedule: {schedule_name}")
        for head_id in head_ids:
            stock_offsets = [
                slot * KV_ROW_BYTES + head_id * HEAD_DIM for slot in slots
            ]
            ring_offsets = [
                position * KV_ROW_BYTES + head_id * HEAD_DIM
                for position in range(WINDOW)
            ]
            for label, offsets in (("stock", stock_offsets), ("ring", ring_offsets)):
                sectors = sum(
                    units_touched(offset, HEAD_DIM, SECTOR_BYTES)
                    for offset in offsets
                )
                transactions = sum(
                    units_touched(offset, HEAD_DIM, TRANSACTION_BYTES)
                    for offset in offsets
                )
                if sectors != WINDOW * 8 or transactions != WINDOW * 2:
                    raise AssertionError(
                        f"payload transaction invariant failed: "
                        f"{schedule_name}/{head_id}/{label}"
                    )
                schedule_rows.append(
                    {
                        "schedule": schedule_name,
                        "head": head_id,
                        "layout": label,
                        "sectors_per_k_or_v": sectors,
                        "transactions_per_k_or_v": transactions,
                    }
                )

    mapping_rows = []
    for request_row in (-1, 0, 1, 31, 32):
        for generation in (0, 1, 17):
            for absolute_position in (0, 1, 1022, 1023, 1024, 1025, 4213, 4571):
                valid = request_row > 0 and generation > 0
                mapping_rows.append(
                    {
                        "request_row": request_row,
                        "generation": generation,
                        "absolute_position": absolute_position,
                        "valid": valid,
                        "ring_position": (
                            absolute_position & (RING_TOKENS - 1)
                            if valid
                            else -1
                        ),
                    }
                )

    return {
        "classification": "CPU analytical mapping oracle",
        "command": "python3 analyze_transactions.py --check",
        "payload_invariant_scope": (
            "All valid integer stock slot permutations, because each slot stride "
            "is 4,096 bytes and each selected head slice is an aligned 256 bytes. "
            "The three schedules are discriminating witnesses, not a claimed "
            "reconstruction of live allocator values."
        ),
        "payload_rows": schedule_rows,
        "mapping_rows": mapping_rows,
        "padded_and_stale_rule": (
            "request_row<=0 or generation<=0 maps to -1 and must no-op before "
            "any K/V address calculation"
        ),
        "oracle_sha256": canonical_sha256(
            {"payload_rows": schedule_rows, "mapping_rows": mapping_rows}
        ),
    }


def build_result():
    binding = source_binding()
    expected_auxiliary = {
        "packet_manifest": "8127631191fe1afc47e718502ff61980b1e51adb8ac43c2f28e140ff506173bd",
        "checkpoint_config": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
        "requests": "10e7edacaa194fd0f43b3a3c38f7d91cec0ceba22df8e08e3b5897b174346135",
        "exact_semantic_rows": "630d05bd860d1dd22c3e35ba2d8f792afc5051f0c68e0a74a9deda8140a02b36",
        "h100_l2_result": "df3ea75c55679f6f676ba12383b7c829061141e91373bb6a0a64c560b87c2f37",
        "h200_ring_terminal": "c5d6e7093dd717239471133cfa7280afd4c7bb56bc26911a7c282d7b5287b8d6",
    }
    for name, expected in expected_auxiliary.items():
        observed = binding["auxiliary"][name]["sha256"]
        if observed != expected:
            raise ValueError(f"{name} identity changed: {observed}")

    config = json.loads(CONFIG.read_text())["text_config"]
    local_ids = [
        index
        for index, layer_type in enumerate(config["layer_types"])
        if layer_type == "sliding_attention"
    ]
    global_ids = [
        index
        for index, layer_type in enumerate(config["layer_types"])
        if layer_type == "full_attention"
    ]
    if (
        len(local_ids) != LOCAL_LAYERS
        or global_ids != list(range(5, 60, 6))
        or config["num_key_value_heads"] != KV_HEADS
        or config["head_dim"] != HEAD_DIM
        or config["sliding_window"] != RING_TOKENS
    ):
        raise ValueError("bound model geometry changed")

    requests = request_geometry()
    group_rows, sectors_per_stream, transactions_per_stream = aggregate_alignment(
        requests
    )
    phases = [
        phase_model(
            name="target_verify_ideal_depth_12_lower_step_bound",
            steps_per_request=math.ceil(
                requests["completion_tokens"] / NGRAM_DEPTH
            ),
            index_streams_per_request_layer_step=QUERY_HEADS,
            payload_request_multiplier=2,
            requests=requests,
            aligned_sectors_per_stream=sectors_per_stream,
            aligned_transactions_per_stream=transactions_per_stream,
        ),
        phase_model(
            name="target_verify_one_accepted_token_upper_step_bound",
            steps_per_request=requests["completion_tokens"],
            index_streams_per_request_layer_step=QUERY_HEADS,
            payload_request_multiplier=2,
            requests=requests,
            aligned_sectors_per_stream=sectors_per_stream,
            aligned_transactions_per_stream=transactions_per_stream,
        ),
        phase_model(
            name="stock_grouped_decode_no_spec_reference",
            steps_per_request=requests["completion_tokens"],
            index_streams_per_request_layer_step=KV_HEADS,
            payload_request_multiplier=1,
            requests=requests,
            aligned_sectors_per_stream=sectors_per_stream,
            aligned_transactions_per_stream=transactions_per_stream,
        ),
    ]
    max_sector_fraction = max(
        row["predicted_reduction"]["fraction_of_stock_requested_sectors"]
        for row in phases
    )
    max_transaction_fraction = max(
        row["predicted_reduction"]["fraction_of_stock_requested_transactions"]
        for row in phases
    )

    return {
        "schema_version": 1,
        "result": "typed_none",
        "typed_none": {
            "type": (
                "payload_transactions_are_permutation_invariant_and_only_"
                "metadata_reduction_remains"
            ),
            "decision": (
                "Do not nominate a v0.5.15 H100 ring implementation from this "
                "evidence. Stock allocator fragmentation cannot add a K/V payload "
                "sector or 128-byte transaction at the bound 256-byte head slice; "
                "the ideal ring only deletes index/mapping metadata."
            ),
            "independent_reasons": [
                (
                    "The stock and ring payload sector/transaction counts are "
                    "identical for every valid realized allocator permutation."
                ),
                (
                    "The remaining ideal reduction is metadata-only, at most "
                    f"{max_sector_fraction:.6%} of local consumer requested sectors "
                    "before cache hits and before unrelated endpoint work."
                ),
                (
                    "The 1,036-row trace has client/release timing and token totals "
                    "but no internal batching, chunk, acceptance, allocator, or "
                    "req_to_token events, so one exact live slot sequence cannot be "
                    "reconstructed without new instrumentation."
                ),
                (
                    "Prefix aliasing and accepted-KV settlement therefore cannot "
                    "be proven source-complete for a request-owned ring from this "
                    "trace alone."
                ),
            ],
            "candidate": None,
        },
        "evidence_labels": {
            "runtime_source_and_geometry": "source-backed/derived",
            "request_counts_and_release_groups": "measured trace",
            "payload_sector_invariance": "analytical and CPU-oracle checked",
            "index_sector_counts": (
                "analytical issued-request model; not cache-level or DRAM counters"
            ),
            "endpoint_speedup": "not measured and not claimed",
            "live_h100": "not claimed, inspected, signaled, or mutated",
        },
        "runtime_identity": {
            "sglang_commit": COMMIT,
            "image": (
                "docker.io/lmsysorg/sglang@sha256:"
                "ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
            ),
            "model": (
                "google/gemma-4-31B-it@"
                "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
            ),
            "accelerator": "nvidia-h100-sxm",
            "gpu_used": False,
        },
        "source_binding": binding,
        "source_line_numbers": source_line_numbers(binding),
        "request_geometry": requests,
        "model_geometry": {
            "local_layer_ids": local_ids,
            "global_layer_ids": global_ids,
            "local_layers": LOCAL_LAYERS,
            "query_heads": QUERY_HEADS,
            "kv_heads": KV_HEADS,
            "head_dim": HEAD_DIM,
            "kv_dtype": "fp8_e5m2",
            "kv_element_bytes": KV_ELEMENT_BYTES,
            "kv_row_bytes_one_tensor": KV_ROW_BYTES,
            "kv_bytes_per_token_k_plus_v": KV_TOKEN_BYTES,
            "page_size": 1,
            "semantic_window_tokens": RING_TOKENS,
            "runtime_prefix_window_tokens": WINDOW,
            "ngram_depth": NGRAM_DEPTH,
        },
        "source_reconstruction": {
            "producer": (
                "Gemma4Attention sends canonical K/V through "
                "TritonAttnBackend._set_kv_buffer. SWAKVPool selects the local "
                "layer buffer and MHATokenToKVPool stores E5M2 at "
                "[swa_slot, kv_head, head_dim]."
            ),
            "ownership": (
                "ReqToTokenPool is int32 [request_row, logical_position]. At "
                "page size one, common.alloc_for_extend/decode calls the token "
                "allocator, which slices the head of free_pages; frees append or "
                "enter release_pages depending on need_sort. SWA allocation pairs "
                "a full slot with a separately allocated SWA slot in an int64 "
                "full_to_swa mapping."
            ),
            "address_schedule": (
                "Initial allocation order and free policy are source-complete, "
                "but the exact realized sequence is a function of scheduler batch "
                "membership, DCP chunks, radix eviction, accepted draft depth, and "
                "free timing. Those events are absent from the bound trace. The "
                "physical conclusion does not assume a replacement synthetic "
                "schedule: it quantifies all integer slot permutations."
            ),
            "metadata_producer": (
                "update_sliding_window_buffer gathers the last min(seq_len,1023) "
                "int32 req_to_token entries into an int64 window_kv_indices "
                "buffer and translates them through the int64 full_to_swa map."
            ),
            "extend_consumer": (
                "Hopper head_dim 256 selects BLOCK_M=64, BLOCK_N=64, eight warps. "
                "The grid has one CTA per request, query head, and M tile. A "
                "12-query NGRAM target-verification block fits one M tile, so each "
                "of 32 query-head CTAs loads one int64 index stream; paired query "
                "heads request the same KV-head payload."
            ),
            "decode_consumer": (
                "GQA decode selects the grouped kernel. BLOCK_H=16 groups the two "
                "query heads per KV head; with 16 KV heads and eight configured "
                "splits, the split CTAs collectively consume each request's index "
                "stream 16 times and request each KV-head payload once."
            ),
            "alignment": (
                "Each K or V slot row is 16*256=4096 E5M2 bytes. Selecting any "
                "head adds a 256-byte-aligned offset. Every 256-byte head slice "
                "therefore occupies exactly eight 32-byte sectors and two "
                "128-byte transactions regardless of the slot integer."
            ),
        },
        "release_group_index_alignment": {
            str(size): {
                **row,
                "sector_counts_by_request_lane": {
                    str(key): value
                    for key, value in sorted(
                        row["sector_counts_by_request_lane"].items()
                    )
                },
                "transaction_counts_by_request_lane": {
                    str(key): value
                    for key, value in sorted(
                        row["transaction_counts_by_request_lane"].items()
                    )
                },
            }
            for size, row in group_rows.items()
        },
        "transaction_model": {
            "counting_boundary": (
                "Global-load request sectors and 128-byte address regions before "
                "cache-hit suppression. Payload counts include kernel-requested "
                "GQA duplication separately from compulsory unique payload."
            ),
            "common_traffic_excluded": (
                "Q/O, softmax intermediates, kv_indptr, sequence lengths, masks, "
                "global layers, linears, scheduler, and HTTP work are unchanged."
            ),
            "ideal_ring_metadata": (
                "An intentionally optimistic packed 64-bit "
                "(request-generation,row/start) scalar per consumer stream; no "
                "per-token index array."
            ),
            "phases": phases,
        },
        "cpu_mapping_oracle": payload_mapping_oracle(),
        "whole_request_relevance": {
            "strict_endpoint_lower_fraction": 0.0,
            "why_lower_is_zero": (
                "The model has no H100 cache counters or endpoint critical-path "
                "share; all deleted index sectors may hit on chip and endpoint work "
                "outside the local consumer is positive."
            ),
            "local_consumer_requested_sector_upper_fraction": max_sector_fraction,
            "local_consumer_requested_transaction_upper_fraction": (
                max_transaction_fraction
            ),
            "upper_scope": (
                "Exact 1,036 rows and exact release-group alignment, completion "
                "steady-window bounds only. Prefill is omitted because the trace "
                "does not contain its internal DCP chunks; adding prefill and "
                "unchanged endpoint work can only dilute this metadata fraction."
            ),
            "classification": "analytical upper bound, not endpoint speedup",
        },
        "lifecycle_requirements_if_reopened": [
            {
                "hazard": "CUDA graph padding",
                "requirement": (
                    "row zero and generation zero map to -1 and no-op before "
                    "producer or consumer address calculation; captured ring "
                    "addresses remain stable."
                ),
            },
            {
                "hazard": "request reuse and reorder",
                "requirement": (
                    "Use a generation-tagged request-row lease, not batch lane; "
                    "free atomically invalidates the old generation."
                ),
            },
            {
                "hazard": "prefix sharing and restoration",
                "requirement": (
                    "Preserve reference-counted aliasing or copy canonical producer "
                    "bytes into each owner before access; the trace has a 528-token "
                    "cacheable common prefix inside release groups."
                ),
            },
            {
                "hazard": "NGRAM accepted-KV settlement",
                "requirement": (
                    "Only scheduler-committed accepted tokens advance the ring; "
                    "rejected draft positions cannot overwrite committed entries."
                ),
            },
            {
                "hazard": "five-local/one-global cadence",
                "requirement": (
                    "Only the 50 listed local layers use a ring. Ten global layers "
                    "retain full paged ownership and canonical buffers."
                ),
            },
        ],
        "smallest_future_h100_falsifier": {
            "authorized_now": False,
            "checkpoint_free": True,
            "shape": {
                "batch": 32,
                "query_tokens_per_request": 12,
                "prefix_tokens": 1023,
                "query_heads": 32,
                "kv_heads": 16,
                "head_dim": 256,
                "kv_dtype": "fp8_e5m2",
                "local_layers": 1,
                "page_size": 1,
            },
            "consumer": (
                "Pinned v0.5.15 extend_attention_fwd in a fresh process, stock "
                "window_kv_indices versus one direct packed-row ring variant; "
                "consume full output against the stock CPU/high-precision oracle."
            ),
            "profiler_off_first": (
                "Warm both paths, then report CUDA-event median and p95 with exact "
                "output equality or bounded error and candidate-path identity."
            ),
            "minimum_counters": [
                "l1tex__t_sectors_pipe_lsu_mem_global_op_ld.sum",
                "lts__t_sectors_op_read.sum",
                "dram__sectors_read.sum",
            ],
            "falsifies_typed_none_if": (
                "The direct ring reduces payload-attributed L2/DRAM sectors, not "
                "only index metadata, or produces a stable consumer latency gain "
                "larger than the 1.55% local requested-sector ceiling with exact "
                "outputs and no hidden representation change."
            ),
        },
        "historical_separation": {
            "h100_l2": (
                "The bound H100 L2 result closes persistent capacity residency; "
                "this result independently closes payload coalescing and leaves "
                "only metadata."
            ),
            "h200_v0513": (
                "The measured 3.10198225% H200 v0.5.13 ring endpoint is a "
                "non-transferable prior. It does not override the H100/v0.5.15 "
                "payload-sector invariant or supply missing scheduler events."
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=PROJECT / "TRANSACTION_RESULT.json"
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build_result()
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists():
            raise SystemExit(f"missing output: {args.output}")
        current = args.output.read_text()
        if current != encoded:
            raise SystemExit("TRANSACTION_RESULT.json is not reproducible")
        print(
            json.dumps(
                {
                    "result": result["result"],
                    "type": result["typed_none"]["type"],
                    "max_local_sector_fraction": result[
                        "whole_request_relevance"
                    ]["local_consumer_requested_sector_upper_fraction"],
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
