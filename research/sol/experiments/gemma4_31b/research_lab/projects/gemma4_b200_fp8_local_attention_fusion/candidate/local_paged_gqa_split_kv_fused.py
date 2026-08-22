"""Split-KV-safe exact-shape Gemma-4 local paged GQA decode.

This module deliberately targets one production contract:

* BF16 Q/K/V/O
* Q heads 32, KV heads 16, head dimension 256
* HND logical KV cache, page size 16
* one decode token per request
* window_left=1023 (1024 visible tokens)
* compact fresh K/V [batch, 16, 256]
* int64 slot mapping [batch]

Only the final KV-partition CTA for each (request, KV-head) persists the fresh
cache row.  That CTA masks the stale cache row out of its native partial and
merges fresh K/V directly into the partial online-softmax state.  Other split
CTAs read settled prefix state only, so no grid-wide cache visibility is
required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


URI = "gemma4_b200_bf16_hnd_d256_gqa2_window1024_split_kv_tail_owner_v1"
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

struct Gemma4LocalSplitKvTailOwner : AttentionVariantBase {
  static constexpr bool use_softmax = true;
  static constexpr uint32_t kHeadDim = 256;
  static constexpr uint32_t kNumKvHeads = 16;
  static constexpr uint32_t kVecSize = 8;  // 16-byte BF16 transaction

  uint32_t qo_len;
  uint32_t kv_len;
  uint32_t window_left;
  float sm_scale_log2;
  bool is_tail_partition;
  uint32_t output_component;

  template <typename Params>
  __device__ Gemma4LocalSplitKvTailOwner(
      const Params& params, uint32_t batch_idx, uint8_t*) {
    using DTypeKV = typename Params::DTypeKV;

    static_assert(sizeof(DTypeKV) == 2, "candidate is BF16-only");
    static_assert(kHeadDim % kVecSize == 0, "vector must tile head");

    const uint32_t work_idx = blockIdx.x;
    const uint32_t kv_tile_idx = params.kv_tile_indices[work_idx];
    const uint32_t num_partitions =
        params.o_indptr[batch_idx + 1] - params.o_indptr[batch_idx];
    is_tail_partition =
        params.partition_kv && num_partitions > 1 && kv_tile_idx + 1 == num_partitions;
    output_component = 0;

    const int64_t slot = params.slot_mapping[batch_idx];
    if (is_tail_partition && slot >= 0 &&
        slot < params.num_pages_in_pool * int64_t(params.paged_kv.page_size) &&
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

    // Only this CTA consumes fresh K/V, and it does so from append_key/value
    // below.  The barrier protects its cache-persistence side effect only.
    cg::this_thread_block().sync();

    qo_len = 1;
    kv_len = params.get_kv_len(batch_idx);
    window_left = params.window_left >= 0 ? params.window_left : kv_len;
    sm_scale_log2 = params.sm_scale * math::log2e;
  }

  REGISTER_LOGITS_MASK(params, batch_idx, qo_idx, kv_idx, qo_head_idx, kv_head_idx, {
    const bool in_window = kv_idx + qo_len + window_left >= kv_len + qo_idx;
    const bool stale_fresh_row =
        is_tail_partition && kv_idx + 1 == kv_len;
    return in_window && !stale_fresh_row;
  })

  REGISTER_OUTPUT_TRANSFORM(params, output, batch_idx, qo_idx, qo_head_idx, m, d, scale, {
    if (!is_tail_partition) {
      return output * ((m != -math::inf) ? math::ptx_rcp(d) : 0.f);
    }
    using DTypeQ = typename Params::DTypeQ;
    using DTypeKV = typename Params::DTypeKV;
    const uint32_t feature = threadIdx.x * kVecSize;
    const uint32_t kv_head_idx = qo_head_idx / (params.num_qo_heads / kNumKvHeads);
    const int64_t q_offset =
        int64_t(batch_idx) * params.q_stride_n +
        int64_t(qo_head_idx) * params.q_stride_h + feature;
    const int64_t kv_offset =
        (int64_t(batch_idx) * kNumKvHeads + kv_head_idx) * kHeadDim + feature;
    vec_t<float, kVecSize> q_vec;
    vec_t<float, kVecSize> k_vec;
    vec_t<float, kVecSize> v_vec;
    q_vec.cast_load(params.q + q_offset);
    k_vec.cast_load(params.append_key + kv_offset);
    v_vec.cast_load(params.append_value + kv_offset);
    float fresh_score = 0.f;
#pragma unroll
    for (uint32_t i = 0; i < kVecSize; ++i) fresh_score += q_vec[i] * k_vec[i];
#pragma unroll
    for (uint32_t offset = 16; offset > 0; offset /= 2) {
      fresh_score += math::shfl_xor_sync(fresh_score, offset);
    }
    fresh_score *= sm_scale_log2;
    const float merged_m = max(float(m), fresh_score);
    const float prefix_scale = math::ptx_exp2(float(m) - merged_m);
    const float fresh_scale = math::ptx_exp2(fresh_score - merged_m);
    const float merged_d = d * prefix_scale + fresh_scale;
    const uint32_t lane_component = output_component++;
    return (output * prefix_scale + v_vec[lane_component] * fresh_scale) *
           math::ptx_rcp(merged_d);
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
        "Gemma4LocalSplitKvTailOwner",
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


def plan_exact(wrapper: Any, indptr: Any, indices: Any, last_page_len: Any) -> dict[str, Any]:
    """Plan the admitted geometry and prove that split-KV is active."""
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
        raise RuntimeError(
            "typed_rejection: exact planner did not select required split_kv"
        )
    return {
        "split_kv": True,
        "padded_batch_size": int(plan_info[0]),
        "request_indices_offset": int(plan_info[3]),
        "kv_tile_indices_offset": int(plan_info[4]),
        "o_indptr_offset": int(plan_info[5]),
        "kv_chunk_size_ptr_offset": int(plan_info[7]),
        "unique_tail_rule": "kv_tile_idx + 1 == o_indptr[request+1]-o_indptr[request]",
    }


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
