"""Exact-shape source replacement for Gemma-4 local paged GQA decode.

This module deliberately targets one production contract:

* BF16 Q/K/V/O
* Q heads 32, KV heads 16, head dimension 256
* HND logical KV cache, page size 16
* one decode token per request
* window_left=1023 (1024 visible tokens)
* compact fresh K/V [batch, 16, 256]
* int64 slot mapping [batch]

The cache append is executed in the native FlashInfer batch-decode CTA before
the source-complete paged-GQA loop.  The owning (request, KV-head) CTA writes
one vector per x-thread and synchronizes before the cache is read.  Split-KV is
rejected because duplicate CTAs would make that ownership ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


URI = "gemma4_b200_bf16_hnd_d256_gqa2_window1024_fused_append_decode_v1"
NUM_QO_HEADS = 32
NUM_KV_HEADS = 16
HEAD_DIM = 256
PAGE_SIZE = 16
WINDOW_LEFT = 1023
SM_SCALE = 1.0
DECODE_PLAN_SPLIT_KV_INDEX = 9


VARIANT_DECL = r"""
#include <cooperative_groups.h>
#include <cstdint>
#include <flashinfer/attention/variant_helper.cuh>
#include <flashinfer/math.cuh>
#include <flashinfer/vec_dtypes.cuh>

namespace cg = cooperative_groups;

struct Gemma4LocalFusedAppendDecode : AttentionVariantBase {
  static constexpr bool use_softmax = true;
  static constexpr uint32_t kHeadDim = 256;
  static constexpr uint32_t kNumKvHeads = 16;
  static constexpr uint32_t kVecSize = 8;  // 16-byte BF16 transaction

  uint32_t qo_len;
  uint32_t kv_len;
  uint32_t window_left;
  float sm_scale_log2;

  template <typename Params>
  __device__ Gemma4LocalFusedAppendDecode(
      const Params& params, uint32_t batch_idx, uint8_t*) {
    using DTypeKV = typename Params::DTypeKV;

    static_assert(sizeof(DTypeKV) == 2, "candidate is BF16-only");
    static_assert(kHeadDim % kVecSize == 0, "vector must tile head");

    const int64_t slot = params.slot_mapping[batch_idx];
    if (slot >= 0 && slot < params.num_pages_in_pool * int64_t(params.paged_kv.page_size) &&
        threadIdx.y == 0 && threadIdx.z == 0) {
      const uint32_t feature = threadIdx.x * kVecSize;
      const uint32_t kv_head = blockIdx.y;
      const int64_t append_offset =
          (int64_t(batch_idx) * kNumKvHeads + kv_head) * kHeadDim + feature;
      const uint32_t physical_page = uint32_t(slot) / params.paged_kv.page_size;
      const uint32_t page_entry = uint32_t(slot) % params.paged_kv.page_size;
      const size_t cache_offset =
          params.paged_kv.get_elem_offset(physical_page, kv_head, page_entry, feature);

      vec_t<DTypeKV, kVecSize> key_vec;
      vec_t<DTypeKV, kVecSize> value_vec;
      key_vec.cast_load(params.append_key + append_offset);
      value_vec.cast_load(params.append_value + append_offset);
      key_vec.cast_store(params.paged_kv.k_data + cache_offset);
      value_vec.cast_store(params.paged_kv.v_data + cache_offset);
    }

    // Exactly one CTA owns each (request, KV-head) in the admitted no-split plan.
    // This makes the just-written token visible before native paged-GQA loads.
    cg::this_thread_block().sync();

    qo_len = 1;
    kv_len = params.get_kv_len(batch_idx);
    window_left = params.window_left >= 0 ? params.window_left : kv_len;
    sm_scale_log2 = params.sm_scale * math::log2e;
  }

  REGISTER_LOGITS_MASK(params, batch_idx, qo_idx, kv_idx, qo_head_idx, kv_head_idx, {
    return kv_idx + qo_len + window_left >= kv_len + qo_idx;
  })
};
"""


@dataclass(frozen=True)
class ExactContract:
    num_qo_heads: int = NUM_QO_HEADS
    num_kv_heads: int = NUM_KV_HEADS
    head_dim: int = HEAD_DIM
    page_size: int = PAGE_SIZE
    window_left: int = WINDOW_LEFT
    sm_scale: float = SM_SCALE


def jit_args() -> list[Any]:
    """Return FlashInfer 0.6.6 custom batch-decode JIT arguments."""
    import torch

    return [
        URI,
        torch.bfloat16,
        torch.bfloat16,
        torch.bfloat16,
        torch.int32,
        HEAD_DIM,
        HEAD_DIM,
        ["append_key", "append_value", "slot_mapping"],
        ["nv_bfloat16", "nv_bfloat16", "int64_t"],
        ["num_pages_in_pool", "sm_scale"],
        ["int64_t", "double"],
        "Gemma4LocalFusedAppendDecode",
        VARIANT_DECL,
        0,  # PosEncodingMode::kNone; Q/K are already position transformed.
        True,
        False,
    ]


def make_wrapper(float_workspace_buffer: Any) -> Any:
    """Build the source module and return the exact-shape native decode wrapper."""
    from flashinfer.decode import BatchDecodeWithPagedKVCacheWrapper

    return BatchDecodeWithPagedKVCacheWrapper(
        float_workspace_buffer,
        kv_layout="HND",
        use_cuda_graph=False,
        use_tensor_cores=False,
        backend="fa2",
        jit_args=jit_args(),
    )


def plan_exact(wrapper: Any, indptr: Any, indices: Any, last_page_len: Any) -> None:
    """Plan the admitted c32 geometry and reject unsafe split-KV ownership."""
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
    if bool(plan_info[DECODE_PLAN_SPLIT_KV_INDEX]):
        raise RuntimeError(
            "typed_rejection: split_kv_invalidates_single_cta_append_ownership"
        )


def run_exact(
    wrapper: Any,
    q: Any,
    kv_cache: Any,
    append_key: Any,
    append_value: Any,
    slot_mapping: Any,
) -> Any:
    """Run the fused append plus source-complete paged-GQA first consumer."""
    import torch

    expected_q = (q.shape[0], NUM_QO_HEADS, HEAD_DIM)
    expected_kv = (q.shape[0], NUM_KV_HEADS, HEAD_DIM)
    if tuple(q.shape) != expected_q or q.dtype != torch.bfloat16 or not q.is_contiguous():
        raise ValueError(f"q must be contiguous BF16 {expected_q}")
    for name, tensor in (("append_key", append_key), ("append_value", append_value)):
        if (
            tuple(tensor.shape) != expected_kv
            or tensor.dtype != torch.bfloat16
            or not tensor.is_contiguous()
        ):
            raise ValueError(f"{name} must be contiguous BF16 {expected_kv}")
    if (
        tuple(slot_mapping.shape) != (q.shape[0],)
        or slot_mapping.dtype != torch.int64
        or not slot_mapping.is_contiguous()
    ):
        raise ValueError("slot_mapping must be contiguous int64 [batch]")
    if kv_cache.ndim != 5 or tuple(kv_cache.shape[1:]) != (
        2,
        NUM_KV_HEADS,
        PAGE_SIZE,
        HEAD_DIM,
    ):
        raise ValueError("kv_cache must be HND [pages,2,16,16,256]")
    if kv_cache.dtype != torch.bfloat16:
        raise ValueError("kv_cache must be BF16")
    expected_strides = (131072, 65536, 256, 4096, 1)
    if tuple(kv_cache.stride()) != expected_strides:
        raise ValueError(
            f"production HND view strides must be {expected_strides}, got {kv_cache.stride()}"
        )

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
