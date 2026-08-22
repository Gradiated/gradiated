"""Source-complete split-reducer append+decode candidate for Gemma 4.

The native split decode writes untouched normalized partial outputs and base-2
LSE values.  A distinct final reducer merges those partial states, inserts the
fresh QK/V state once per Q head, and assigns cache persistence to exactly one
Q head in each GQA2 pair.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


URI = "gemma4_b200_bf16_hnd_d256_gqa2_window1024_split_reducer_v1_repair1"
NUM_QO_HEADS = 32
NUM_KV_HEADS = 16
HEAD_DIM = 256
PAGE_SIZE = 16
WINDOW_LEFT = 1023
SM_SCALE = 1.0
DECODE_PLAN_SPLIT_KV_INDEX = 9
PINNED_SOURCE_MANIFEST_SHA256 = (
    "e3bf5e617be297529619788171fdba55822d0d859a3ec0cbbf9c5efd14b24067"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_paths(project_root: Path) -> dict[str, Path]:
    pinned = (
        project_root
        / "inputs/pinned/flashinfer-0.6.6/split-reducer-source"
    )
    candidate = project_root / "candidate/split_reducer_src"
    manifest = pinned / "MANIFEST.sha256"
    if sha256_file(manifest) != PINNED_SOURCE_MANIFEST_SHA256:
        raise RuntimeError("split-reducer pinned source manifest mismatch")
    return {
        "pinned": pinned,
        "include": pinned / "include",
        "csrc": pinned / "csrc",
        "candidate": candidate,
        "manifest": manifest,
    }


def make_wrapper(project_root: Path, float_workspace_buffer: Any) -> Any:
    """Build only the exact SM100 split-reducer module and return its wrapper."""
    from flashinfer.decode import (
        BatchDecodeWithPagedKVCacheWrapper,
        get_batch_decode_jit_module,
    )
    from flashinfer.jit.core import gen_jit_spec, sm100a_nvcc_flags

    paths = source_paths(project_root)
    spec = gen_jit_spec(
        URI,
        [
            paths["candidate"] / "batch_decode_kernel.cu",
            paths["csrc"] / "batch_decode.cu",
            paths["csrc"] / "batch_decode_jit_binding.cu",
        ],
        extra_cuda_cflags=sm100a_nvcc_flags,
        extra_include_paths=[
            paths["candidate"],
            paths["include"],
            paths["csrc"],
        ],
    )
    raw_module = spec.build_and_load()
    wrapper = BatchDecodeWithPagedKVCacheWrapper(
        float_workspace_buffer,
        kv_layout="HND",
        use_cuda_graph=False,
        use_tensor_cores=False,
        backend="fa2",
    )
    wrapper._jit_module = get_batch_decode_jit_module(URI, raw_module)
    return wrapper


def plan_exact(
    wrapper: Any, indptr: Any, indices: Any, last_page_len: Any
) -> dict[str, Any]:
    import torch

    wrapper.plan(
        indptr,
        indices,
        last_page_len,
        NUM_QO_HEADS,
        NUM_KV_HEADS,
        HEAD_DIM,
        PAGE_SIZE,
        pos_encoding_mode="NONE",
        window_left=WINDOW_LEFT,
        logits_soft_cap=0.0,
        q_data_type=torch.bfloat16,
        kv_data_type=torch.bfloat16,
        o_data_type=torch.bfloat16,
        sm_scale=SM_SCALE,
    )
    plan_info = wrapper._plan_info
    if plan_info is None or len(plan_info) != 10:
        raise RuntimeError("unexpected FlashInfer DecodePlanInfo encoding")
    if not bool(plan_info[DECODE_PLAN_SPLIT_KV_INDEX]):
        raise RuntimeError("exact planner did not select required split-KV")
    return {
        "split_kv": True,
        "padded_batch_size": int(plan_info[0]),
        "request_indices_offset": int(plan_info[3]),
        "kv_tile_indices_offset": int(plan_info[4]),
        "o_indptr_offset": int(plan_info[5]),
        "kv_chunk_size_ptr_offset": int(plan_info[7]),
        "cache_owner": "qo_head_idx % 2 == 0; kv_head_idx = qo_head_idx / 2",
        "fresh_merge_count": "one reducer merge per (request, qo_head)",
    }


def run_exact(
    wrapper: Any,
    q: Any,
    kv_cache: Any,
    append_key: Any,
    append_value: Any,
    slot_mapping: Any,
) -> Any:
    import torch

    if tuple(q.shape[1:]) != (NUM_QO_HEADS, HEAD_DIM):
        raise ValueError("q shape mismatch")
    if q.dtype != torch.bfloat16 or not q.is_contiguous():
        raise ValueError("q must be contiguous BF16")
    expected_kv = (q.shape[0], NUM_KV_HEADS, HEAD_DIM)
    for name, tensor in (("append_key", append_key), ("append_value", append_value)):
        if tuple(tensor.shape) != expected_kv:
            raise ValueError(f"{name} shape mismatch")
        if tensor.dtype != torch.bfloat16 or not tensor.is_contiguous():
            raise ValueError(f"{name} must be contiguous BF16")
    if tuple(slot_mapping.shape) != (q.shape[0],):
        raise ValueError("slot_mapping shape mismatch")
    if slot_mapping.dtype != torch.int64 or not slot_mapping.is_contiguous():
        raise ValueError("slot_mapping must be contiguous int64")
    if kv_cache.ndim != 5 or tuple(kv_cache.shape[1:]) != (
        2,
        NUM_KV_HEADS,
        PAGE_SIZE,
        HEAD_DIM,
    ):
        raise ValueError("kv_cache must be HND [pages,2,16,16,256]")
    if kv_cache.dtype != torch.bfloat16:
        raise ValueError("kv_cache must be BF16")
    if tuple(kv_cache.stride()) != (131072, 65536, 256, 4096, 1):
        raise ValueError("production HND cache stride mismatch")

    return wrapper.run(
        q,
        kv_cache,
        append_key,
        append_value,
        slot_mapping,
        kv_cache.shape[0],
        SM_SCALE,
        window_left=WINDOW_LEFT,
        enable_pdl=False,
    )
