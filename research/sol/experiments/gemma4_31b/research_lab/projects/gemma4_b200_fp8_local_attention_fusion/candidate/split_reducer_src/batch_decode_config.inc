#pragma once
#include <flashinfer/page.cuh>
#include <flashinfer/math.cuh>
#include <flashinfer/layout.cuh>
#include <flashinfer/pos_enc.cuh>
#include <flashinfer/attention/variant_helper.cuh>

#define ADDITIONAL_FUNC_PARAMS                                                    \
  , ffi::Tensor append_key, ffi::Tensor append_value, ffi::Tensor slot_mapping, \
      int64_t num_pages_in_pool, double sm_scale
#define ADDITIONAL_PARAMS_SETTER                                             \
  params.append_key = static_cast<nv_bfloat16*>(append_key.data_ptr());       \
  params.append_value = static_cast<nv_bfloat16*>(append_value.data_ptr());   \
  params.slot_mapping = static_cast<int64_t*>(slot_mapping.data_ptr());       \
  params.num_pages_in_pool = num_pages_in_pool;                               \
  params.sm_scale = sm_scale;

#undef DISPATCH_GQA_GROUP_SIZE
#define DISPATCH_GQA_GROUP_SIZE(group_size, GROUP_SIZE, ...) \
  {                                                          \
    constexpr size_t GROUP_SIZE = 2;                         \
    __VA_ARGS__                                              \
  }

#define DISPATCH_context(DTypeQ, DTypeKV, DTypeO, IdType, HEAD_DIM_QK,            \
                         HEAD_DIM_VO, POS_ENCODING_MODE, USE_SLIDING_WINDOW,       \
                         USE_LOGITS_SOFT_CAP, AttentionVariant, Params, ...) {     \
  using AttentionVariant = Gemma4LocalSplitReducerVariant;                         \
  __VA_ARGS__();                                                                   \
}

using namespace flashinfer;

using DTypeQ = nv_bfloat16;
using DTypeKV = nv_bfloat16;
using DTypeO = nv_bfloat16;
using IdType = int32_t;
constexpr int HEAD_DIM_QK = 256;
constexpr int HEAD_DIM_VO = 256;
constexpr auto USE_LOGITS_SOFT_CAP = false;
constexpr auto POS_ENCODING_MODE = PosEncodingMode::kNone;
constexpr auto USE_SLIDING_WINDOW = true;

struct Params {
  using DTypeQ = ::DTypeQ;
  using DTypeKV = ::DTypeKV;
  using DTypeO = ::DTypeO;
  using IdType = ::IdType;

  DTypeQ* q;
  paged_kv_t<DTypeKV, IdType> paged_kv;
  DTypeO* o;
  float* lse;

  DTypeKV* append_key;
  DTypeKV* append_value;
  int64_t* slot_mapping;
  int64_t num_pages_in_pool;
  double sm_scale;

  uint32_t padded_batch_size;
  uint32_t num_qo_heads;
  IdType q_stride_n;
  IdType q_stride_h;
  int32_t window_left;
  bool enable_pdl;

  IdType* request_indices;
  IdType* kv_tile_indices;
  IdType* o_indptr;
  IdType* kv_chunk_size_ptr;
  bool* block_valid_mask;
  bool partition_kv;

  __host__ __device__ __forceinline__ int32_t get_qo_len(int32_t) const {
    return 1;
  }

  __host__ __device__ __forceinline__ int32_t get_kv_len(
      int32_t batch_idx) const {
    return paged_kv.get_length(batch_idx);
  }
};

struct Gemma4LocalSplitReducerVariant : AttentionVariantBase {
  static constexpr bool use_softmax = true;

  uint32_t qo_len;
  uint32_t kv_len;
  uint32_t window_left;
  float sm_scale_log2;
  bool is_tail_partition;

  template <typename ParamsT>
  __device__ Gemma4LocalSplitReducerVariant(
      const ParamsT& params, uint32_t batch_idx, uint8_t*) {
    const uint32_t work_idx = blockIdx.x;
    const uint32_t kv_tile_idx = params.kv_tile_indices[work_idx];
    const uint32_t num_partitions =
        params.o_indptr[batch_idx + 1] - params.o_indptr[batch_idx];
    is_tail_partition =
        params.partition_kv && num_partitions > 1 &&
        kv_tile_idx + 1 == num_partitions;
    qo_len = 1;
    kv_len = params.get_kv_len(batch_idx);
    window_left = params.window_left >= 0 ? params.window_left : kv_len;
    sm_scale_log2 = float(params.sm_scale) * math::log2e;
  }

  REGISTER_LOGITS_MASK(params, batch_idx, qo_idx, kv_idx, qo_head_idx,
                       kv_head_idx, {
    const bool in_window =
        kv_idx + qo_len + window_left >= kv_len + qo_idx;
    const bool stale_fresh_row =
        is_tail_partition && kv_idx + 1 == kv_len;
    return in_window && !stale_fresh_row;
  })
};
