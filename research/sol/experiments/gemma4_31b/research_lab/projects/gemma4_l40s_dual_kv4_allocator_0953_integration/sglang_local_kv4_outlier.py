"""Narrow adapter from the selected SGLang KV-recipe seam to the SM89 kernels."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
from torch.utils.cpp_extension import load

from sglang.srt.layers.quantization.fp4_kv_cache_quant_method import (
    KVCacheQuantMethodBase,
)
from sglang.srt.mem_cache.memory_pool import KVWriteLoc, MHATokenToKVPool
from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool
from sglang.srt.mem_cache.utils import maybe_init_custom_mem_pool


HEAD_DIM = 256
VECTOR_BYTES = 144
WINDOW = 1024
_EXTENSION = None
GB = 1024 * 1024 * 1024


def load_extension():
    global _EXTENSION
    if _EXTENSION is None:
        root = Path(__file__).resolve().parent
        _EXTENSION = load(
            name="sglang_local_kv4_outlier_sm89",
            sources=[
                str(root / "local_kv4_outlier_bindings.cpp"),
                str(root / "local_kv4_outlier_cuda.cu"),
            ],
            extra_cflags=["-O3"],
            extra_cuda_cflags=["-O3", "--use_fast_math"],
            verbose=True,
        )
    return _EXTENSION


class LocalKV4OutlierKVCacheMethod(KVCacheQuantMethodBase):
    name = "local_kv4_outlier_d256_g64_o4"
    SCALE_BLOCK_SIZE = 64

    def create_buffers(self, size, head_num, head_dim, layer_num, device) -> dict:
        if head_dim != HEAD_DIM:
            raise ValueError(f"local KV4 is frozen to D{HEAD_DIM}, got D{head_dim}")
        shape = (size, head_num, VECTOR_BYTES)
        return {
            "k_buffer": [
                torch.empty(shape, dtype=torch.uint8, device=device)
                for _ in range(layer_num)
            ],
            "v_buffer": [
                torch.empty(shape, dtype=torch.uint8, device=device)
                for _ in range(layer_num)
            ],
            "store_dtype": torch.uint8,
        }

    def quantize_and_store(
        self,
        k_buffer,
        v_buffer,
        k_scale_buffer,
        v_scale_buffer,
        loc,
        cache_k,
        cache_v,
        k_scale=None,
        v_scale=None,
    ) -> None:
        if k_scale_buffer is not None or v_scale_buffer is not None:
            raise RuntimeError("the 144-byte rows own their embedded BF16 scales")
        extension = load_extension()
        extension.pack(cache_k.contiguous(), loc.contiguous(), k_buffer)
        extension.pack(cache_v.contiguous(), loc.contiguous(), v_buffer)

    def dequantize_prev_kv(self, *args, **kwargs):
        raise RuntimeError("full-cache dequantization is forbidden for local KV4")

    def compute_cell_size(
        self, head_num: int, head_dim: int, num_layers: int, kv_size: int
    ) -> int:
        if head_dim != HEAD_DIM:
            raise ValueError(f"local KV4 is frozen to D{HEAD_DIM}, got D{head_dim}")
        return head_num * VECTOR_BYTES * num_layers * 2 * kv_size


class LocalKV4OutlierSWAKVPool(SWAKVPool):
    def __init__(
        self,
        size: int,
        size_swa: int,
        page_size: int,
        dtype: torch.dtype,
        head_num: int,
        head_dim: int,
        swa_attention_layer_ids: List[int],
        full_attention_layer_ids: List[int],
        device: str,
        token_to_kv_pool_class=MHATokenToKVPool,
        **kwargs,
    ):
        if page_size != 1 or head_dim != HEAD_DIM:
            raise ValueError("local KV4 requires page-size one and local D256")
        self.size = size
        self.size_swa = size_swa
        self.dtype = dtype
        self.head_num = head_num
        self.head_dim = head_dim
        self.device = device
        self.swa_layer_nums = len(swa_attention_layer_ids)
        self.full_layer_nums = len(full_attention_layer_ids)
        self.layer_num = self.full_layer_nums + self.swa_layer_nums
        self.start_layer = 0
        self.page_size = page_size
        self.layer_transfer_counter = None
        kwargs["page_size"] = page_size
        kwargs["enable_memory_saver"] = False
        kwargs["head_num"] = head_num
        kwargs["head_dim"] = head_dim
        kwargs["device"] = device
        self.enable_custom_mem_pool, self.custom_mem_pool, _ = (
            maybe_init_custom_mem_pool(device=self.device)
        )

        local_kwargs = dict(kwargs)
        local_kwargs["post_capture_active"] = False
        local_kwargs["quant_method"] = LocalKV4OutlierKVCacheMethod()
        self.swa_kv_pool = token_to_kv_pool_class(
            size=size_swa,
            dtype=dtype,
            layer_num=self.swa_layer_nums,
            **local_kwargs,
        )
        for key in ("swa_head_num", "swa_head_dim", "swa_v_head_dim"):
            kwargs.pop(key, None)
        self.full_kv_pool = token_to_kv_pool_class(
            size=size,
            dtype=dtype,
            layer_num=self.full_layer_nums,
            **kwargs,
        )
        self.layers_mapping: Dict[int, Tuple[int, bool]] = {}
        for local_id, global_id in enumerate(full_attention_layer_ids):
            self.layers_mapping[global_id] = (local_id, False)
        for local_id, global_id in enumerate(swa_attention_layer_ids):
            self.layers_mapping[global_id] = (local_id, True)
        self.full_to_swa_index_mapping: Optional[torch.Tensor] = None
        k_size, v_size = self.get_kv_size_bytes()
        self.mem_usage = (k_size + v_size) / GB


def is_local_kv4_layer(pool, layer_id: int) -> bool:
    mapping = getattr(pool, "layers_mapping", {})
    if layer_id not in mapping:
        return False
    _, is_swa = mapping[layer_id]
    method = getattr(getattr(pool, "swa_kv_pool", None), "quant_method", None)
    return bool(is_swa and getattr(method, "name", None) == LocalKV4OutlierKVCacheMethod.name)


def raw_local_buffers(pool, layer_id: int):
    local_layer, is_swa = pool.layers_mapping[layer_id]
    if not is_swa:
        raise ValueError("global E5M2 layers must not enter the local KV4 consumer")
    local_pool = pool.swa_kv_pool
    if getattr(local_pool.quant_method, "name", None) != LocalKV4OutlierKVCacheMethod.name:
        raise ValueError("the SWA pool does not own the frozen local KV4 recipe")
    return local_pool.k_buffer[local_layer], local_pool.v_buffer[local_layer]


def fused_local_attention(
    q,
    *,
    pool,
    layer_id: int,
    qo_indptr,
    window_kv_indptr,
    window_kv_indices,
    max_query_len: int,
    corrected: bool = True,
):
    if q.shape[-1] != HEAD_DIM:
        raise ValueError("the fused consumer is frozen to local D256")
    if WINDOW != 1024:
        raise AssertionError("representation contract changed")
    k_buffer, v_buffer = raw_local_buffers(pool, layer_id)
    return load_extension().paged_attention(
        q.contiguous(),
        k_buffer,
        v_buffer,
        qo_indptr.contiguous(),
        window_kv_indptr.contiguous(),
        window_kv_indices.contiguous(),
        WINDOW,
        int(max_query_len),
        1.0 / math.sqrt(HEAD_DIM),
        corrected,
    )


def _store_local(backend, q, k, v, layer, forward_batch):
    if k is None or v is None:
        raise ValueError("local KV4 requires the actual current K and V producer")
    loc = KVWriteLoc(
        forward_batch.out_cache_loc,
        backend.forward_metadata.swa_out_cache_loc,
        full_loc=backend.forward_metadata.out_cache_loc_full_physical,
    )
    backend._set_kv_buffer(forward_batch, layer, loc, k, v)
    return q.view(-1, layer.tp_q_head_num, layer.qk_head_dim)


def _local_decode(backend, q, k, v, layer, forward_batch):
    q = _store_local(backend, q, k, v, layer, forward_batch)
    return fused_local_attention(
        q,
        pool=backend.token_to_kv_pool,
        layer_id=layer.layer_id,
        qo_indptr=backend.forward_metadata.qo_indptr,
        window_kv_indptr=backend.forward_metadata.window_kv_indptr,
        window_kv_indices=backend.forward_metadata.window_kv_indices,
        max_query_len=1,
    ).reshape(-1, layer.tp_q_head_num * layer.v_head_dim)


def _local_extend(backend, q, k, v, layer, forward_batch):
    q = _store_local(backend, q, k, v, layer, forward_batch)
    bs = forward_batch.batch_size
    prefix_indptr = backend.forward_metadata.window_kv_indptr
    prefix_indices = backend.forward_metadata.window_kv_indices
    extend_indices = backend.token_to_kv_pool.translate_loc_from_full_to_swa(
        forward_batch.out_cache_loc
    )
    extend_lens = forward_batch.extend_seq_lens
    if extend_lens is None:
        raise RuntimeError("local KV4 extend requires explicit ragged extend lengths")
    if forward_batch.extend_start_loc is None:
        extend_start = torch.cat(
            [
                torch.zeros(1, dtype=torch.int32, device=q.device),
                torch.cumsum(extend_lens[:-1], dim=0),
            ]
        )
    else:
        extend_start = forward_batch.extend_start_loc
    unified_indptr, unified_indices, _ = backend.build_unified_kv_indices(
        prefix_indptr,
        prefix_indices,
        extend_start,
        extend_lens,
        extend_indices,
        bs,
    )
    return fused_local_attention(
        q,
        pool=backend.token_to_kv_pool,
        layer_id=layer.layer_id,
        qo_indptr=backend.forward_metadata.qo_indptr,
        window_kv_indptr=unified_indptr,
        window_kv_indices=unified_indices,
        max_query_len=backend.forward_metadata.max_extend_len,
    ).reshape(-1, layer.tp_q_head_num * layer.v_head_dim)


def install_current_runtime() -> None:
    from sglang.srt.layers.attention import triton_backend
    from sglang.srt.mem_cache import kv_cache_configurator

    backend_class = triton_backend.TritonAttnBackend
    if getattr(backend_class, "_local_kv4_outlier_installed", False):
        return
    original_extend = backend_class.forward_extend
    original_decode = backend_class.forward_decode

    def forward_extend(self, q, k, v, layer, forward_batch, **kwargs):
        if is_local_kv4_layer(self.token_to_kv_pool, layer.layer_id):
            if kwargs.get("sinks") is not None or kwargs.get("score_mod") is not None:
                raise NotImplementedError("local KV4 admits no sinks or score modifier")
            return _local_extend(self, q, k, v, layer, forward_batch)
        return original_extend(self, q, k, v, layer, forward_batch, **kwargs)

    def forward_decode(self, q, k, v, layer, forward_batch, **kwargs):
        if is_local_kv4_layer(self.token_to_kv_pool, layer.layer_id):
            if kwargs.get("sinks") is not None or kwargs.get("score_mod") is not None:
                raise NotImplementedError("local KV4 admits no sinks or score modifier")
            return _local_decode(self, q, k, v, layer, forward_batch)
        return original_decode(self, q, k, v, layer, forward_batch, **kwargs)

    backend_class.forward_extend = forward_extend
    backend_class.forward_decode = forward_decode
    backend_class._local_kv4_outlier_installed = True
    kv_cache_configurator.SWAKVPool = LocalKV4OutlierSWAKVPool
