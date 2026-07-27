"""Exact current-SGLang component seam for the fixed global mixed-tier cache."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np
import torch
from torch.utils.cpp_extension import load


HEAD_DIM = 512
KV_HEADS = 4
QUERY_HEADS = 32
RECENT_TOKENS = 1024
OLD_VECTOR_BYTES = 296
CONCURRENCY = 32
CHUNKED_PREFILL_TOKENS = 2048
RECENT_CAPACITY = CONCURRENCY * RECENT_TOKENS + CHUNKED_PREFILL_TOKENS
PHYSICAL_CAPACITY = 129_688
PEAK_PHYSICAL_ROWS = 129_687
OLD_CAPACITY = PEAK_PHYSICAL_ROWS - CONCURRENCY * RECENT_TOKENS
_EXTENSION = None


def load_extension():
    global _EXTENSION
    if _EXTENSION is None:
        root = Path(__file__).resolve().parent
        _EXTENSION = load(
            name="sglang_global_tiered_kv4_outlier_sm89",
            sources=[
                str(root / "global_tiered_kv4_bindings.cpp"),
                str(root / "global_tiered_kv4_cuda.cu"),
            ],
            extra_cflags=["-O3"],
            extra_cuda_cflags=[
                "-O3",
                "--use_fast_math",
                "--ptxas-options=-v",
                "-gencode=arch=compute_89,code=sm_89",
            ],
            verbose=True,
        )
    return _EXTENSION


@dataclass(frozen=True)
class LockedC32Layout:
    kv_indptr: np.ndarray
    kv_indices: np.ndarray
    old_locations: np.ndarray
    recent_locations: np.ndarray
    old_physical: np.ndarray
    recent_physical: np.ndarray
    retiring_physical: np.ndarray
    new_physical: np.ndarray
    sequence_length: int


def build_locked_c32_layout(sequence_length: int) -> LockedC32Layout:
    if sequence_length < RECENT_TOKENS:
        raise ValueError("the production component requires a full old tier")
    shared_prefix = 535
    unique_length = sequence_length - shared_prefix
    physical_rows = shared_prefix + CONCURRENCY * unique_length
    if physical_rows > PEAK_PHYSICAL_ROWS:
        raise ValueError("sequence exceeds the frozen physical-row peak")
    shared = np.arange(shared_prefix, dtype=np.int64)
    request_tables = []
    cursor = shared_prefix
    for _ in range(CONCURRENCY):
        unique = np.arange(cursor, cursor + unique_length, dtype=np.int64)
        request_tables.append(np.concatenate([shared, unique]))
        cursor += unique_length
    kv_indptr = np.arange(
        0, CONCURRENCY * sequence_length + 1, sequence_length, dtype=np.int32
    )
    kv_indices = np.concatenate(request_tables)

    recent_set: set[int] = set()
    for table in request_tables:
        recent_set.update(int(slot) for slot in table[-RECENT_TOKENS:])
    recent_physical = np.asarray(sorted(recent_set), np.int64)
    old_physical = np.asarray(
        sorted(set(range(physical_rows)).difference(recent_set)), np.int64
    )
    if old_physical.size > OLD_CAPACITY or recent_physical.size > RECENT_CAPACITY:
        raise RuntimeError("locked c32 tier capacity exceeded")
    old_locations = np.full(PHYSICAL_CAPACITY, -1, np.int32)
    recent_locations = np.full(PHYSICAL_CAPACITY, -1, np.int32)
    old_locations[old_physical] = np.arange(old_physical.size, dtype=np.int32)
    recent_locations[recent_physical] = np.arange(recent_physical.size, dtype=np.int32)
    retiring_physical = np.asarray(
        [table[-RECENT_TOKENS - 1] for table in request_tables], np.int64
    )
    new_physical = np.asarray([table[-1] for table in request_tables], np.int64)
    recent_locations[retiring_physical] = np.arange(
        recent_physical.size,
        recent_physical.size + CONCURRENCY,
        dtype=np.int32,
    )
    return LockedC32Layout(
        kv_indptr=kv_indptr,
        kv_indices=kv_indices,
        old_locations=old_locations,
        recent_locations=recent_locations,
        old_physical=old_physical,
        recent_physical=recent_physical,
        retiring_physical=retiring_physical,
        new_physical=new_physical,
        sequence_length=sequence_length,
    )


def allocate_candidate(device: torch.device):
    return {
        "recent_k": torch.empty(
            (RECENT_CAPACITY, KV_HEADS, HEAD_DIM), dtype=torch.uint8, device=device
        ),
        "recent_v": torch.empty(
            (RECENT_CAPACITY, KV_HEADS, HEAD_DIM), dtype=torch.uint8, device=device
        ),
        "old_k": torch.empty(
            (OLD_CAPACITY, KV_HEADS, OLD_VECTOR_BYTES),
            dtype=torch.uint8,
            device=device,
        ),
        "old_v": torch.empty(
            (OLD_CAPACITY, KV_HEADS, OLD_VECTOR_BYTES),
            dtype=torch.uint8,
            device=device,
        ),
    }


def materialize_candidate(keys, values, *, layout: LockedC32Layout, candidate):
    extension = load_extension()
    device = keys.device
    old_locations = torch.as_tensor(layout.old_locations, device=device)
    recent_locations = torch.as_tensor(layout.recent_locations, device=device)
    old_physical = torch.as_tensor(layout.old_physical, device=device)
    recent_physical = torch.as_tensor(layout.recent_physical, device=device)
    extension.pack_old(
        keys.index_select(0, old_physical),
        old_physical,
        old_locations,
        candidate["old_k"],
    )
    extension.pack_old(
        values.index_select(0, old_physical),
        old_physical,
        old_locations,
        candidate["old_v"],
    )
    extension.store_recent(
        keys.index_select(0, recent_physical),
        recent_physical,
        recent_locations,
        candidate["recent_k"],
    )
    extension.store_recent(
        values.index_select(0, recent_physical),
        recent_physical,
        recent_locations,
        candidate["recent_v"],
    )
    retiring_physical = torch.as_tensor(layout.retiring_physical, device=device)
    extension.store_recent(
        keys.index_select(0, retiring_physical),
        retiring_physical,
        recent_locations,
        candidate["recent_k"],
    )
    extension.store_recent(
        values.index_select(0, retiring_physical),
        retiring_physical,
        recent_locations,
        candidate["recent_v"],
    )


def consume_candidate(query, *, layout: LockedC32Layout, candidate):
    extension = load_extension()
    device = query.device
    old_locations = torch.as_tensor(layout.old_locations, device=device)
    recent_locations = torch.as_tensor(layout.recent_locations, device=device)
    qo_indptr = torch.arange(CONCURRENCY + 1, dtype=torch.int32, device=device)
    kv_indptr = torch.as_tensor(layout.kv_indptr, device=device)
    kv_indices = torch.as_tensor(layout.kv_indices, device=device)
    return extension.paged_attention(
        query,
        candidate["recent_k"],
        candidate["recent_v"],
        candidate["old_k"],
        candidate["old_v"],
        recent_locations,
        old_locations,
        qo_indptr,
        kv_indptr,
        kv_indices,
        1,
        1.0 / math.sqrt(HEAD_DIM),
    )


def candidate_decode_step(
    query,
    keys,
    values,
    *,
    layout: LockedC32Layout,
    candidate,
):
    extension = load_extension()
    device = query.device
    old_locations = torch.as_tensor(layout.old_locations, device=device)
    recent_locations = torch.as_tensor(layout.recent_locations, device=device)
    new_physical = torch.as_tensor(layout.new_physical, device=device)
    retiring_physical = torch.as_tensor(layout.retiring_physical, device=device)
    extension.store_recent(
        keys.index_select(0, new_physical),
        new_physical,
        recent_locations,
        candidate["recent_k"],
    )
    extension.store_recent(
        values.index_select(0, new_physical),
        new_physical,
        recent_locations,
        candidate["recent_v"],
    )
    extension.retire_recent(
        retiring_physical,
        old_locations,
        recent_locations,
        candidate["recent_k"],
        candidate["old_k"],
    )
    extension.retire_recent(
        retiring_physical,
        old_locations,
        recent_locations,
        candidate["recent_v"],
        candidate["old_v"],
    )
    return consume_candidate(query, layout=layout, candidate=candidate)
