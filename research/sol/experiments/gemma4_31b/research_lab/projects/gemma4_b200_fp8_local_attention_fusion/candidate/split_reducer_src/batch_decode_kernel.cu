#include <flashinfer/attention/decode.cuh>
#include "batch_decode_config.inc"

using namespace flashinfer;

namespace flashinfer {

constexpr uint32_t kGemmaHeadDim = 256;
constexpr uint32_t kGemmaVecSize = 8;
constexpr uint32_t kGemmaThreadsX = 32;

template <typename ParamsT>
__global__ void Gemma4VariableLengthMergeFreshKernel(
    typename ParamsT::DTypeO* __restrict__ partial_v,
    float* __restrict__ partial_lse,
    typename ParamsT::IdType* __restrict__ indptr,
    typename ParamsT::DTypeO* __restrict__ output,
    float* __restrict__ output_lse,
    uint32_t batch_size,
    ParamsT params) {
  using DTypeKV = typename ParamsT::DTypeKV;
  using DTypeO = typename ParamsT::DTypeO;

  const uint32_t tx = threadIdx.x;
  const uint32_t flat_head = blockIdx.x;
  const uint32_t batch_idx = flat_head / params.num_qo_heads;
  const uint32_t qo_head_idx = flat_head % params.num_qo_heads;
  if (batch_idx >= batch_size) return;

  const uint32_t group_size =
      params.num_qo_heads / params.paged_kv.num_heads;
  const uint32_t kv_head_idx = qo_head_idx / group_size;
  const int64_t slot = params.slot_mapping[batch_idx];
  const bool valid_fresh =
      slot >= 0 &&
      slot < params.num_pages_in_pool *
                 int64_t(params.paged_kv.page_size);

  state_t<kGemmaVecSize> state;
  const uint32_t begin = indptr[batch_idx];
  const uint32_t end = indptr[batch_idx + 1];
  for (uint32_t partition = begin; partition < end; ++partition) {
    vec_t<float, kGemmaVecSize> value;
    value.cast_load(
        partial_v +
        (int64_t(partition) * params.num_qo_heads + qo_head_idx) *
            kGemmaHeadDim +
        tx * kGemmaVecSize);
    const float lse =
        partial_lse[partition * params.num_qo_heads + qo_head_idx];
    state.merge(value, lse, 1.f);
  }

  if (valid_fresh) {
    const int64_t q_offset =
        int64_t(batch_idx) * params.q_stride_n +
        int64_t(qo_head_idx) * params.q_stride_h +
        tx * kGemmaVecSize;
    const int64_t kv_offset =
        (int64_t(batch_idx) * params.paged_kv.num_heads + kv_head_idx) *
            kGemmaHeadDim +
        tx * kGemmaVecSize;
    vec_t<float, kGemmaVecSize> query;
    vec_t<float, kGemmaVecSize> key;
    vec_t<float, kGemmaVecSize> value;
    query.cast_load(params.q + q_offset);
    key.cast_load(params.append_key + kv_offset);
    value.cast_load(params.append_value + kv_offset);

    float fresh_lse = 0.f;
#pragma unroll
    for (uint32_t i = 0; i < kGemmaVecSize; ++i) {
      fresh_lse += query[i] * key[i];
    }
#pragma unroll
    for (uint32_t offset = 16; offset > 0; offset /= 2) {
      fresh_lse += math::shfl_xor_sync(fresh_lse, offset);
    }
    fresh_lse *= float(params.sm_scale) * math::log2e;
    state.merge(value, fresh_lse, 1.f);

    // The reducer has one work item per Q head.  In GQA2 exactly the first
    // Q head mapped to each KV head owns the cache persistence side effect.
    if (qo_head_idx % group_size == 0) {
      const uint32_t physical_page =
          uint32_t(slot) / params.paged_kv.page_size;
      const uint32_t page_entry =
          uint32_t(slot) % params.paged_kv.page_size;
      const size_t cache_offset = params.paged_kv.get_elem_offset(
          physical_page, kv_head_idx, page_entry, tx * kGemmaVecSize);
      vec_t<DTypeKV, kGemmaVecSize> key_store;
      vec_t<DTypeKV, kGemmaVecSize> value_store;
      key_store.cast_load(params.append_key + kv_offset);
      value_store.cast_load(params.append_value + kv_offset);
      key_store.cast_store(params.paged_kv.k_data + cache_offset);
      value_store.cast_store(params.paged_kv.v_data + cache_offset);
    }
  }

  state.normalize();
  state.o.cast_store(
      output +
      (int64_t(batch_idx) * params.num_qo_heads + qo_head_idx) *
          kGemmaHeadDim +
      tx * kGemmaVecSize);
  if (output_lse != nullptr && tx == 0) {
    output_lse[batch_idx * params.num_qo_heads + qo_head_idx] =
        state.get_lse();
  }
}

template <>
cudaError_t BatchDecodeWithPagedKVCacheDispatched<
    HEAD_DIM_QK, POS_ENCODING_MODE, Gemma4LocalSplitReducerVariant, Params>(
    Params params, DTypeO* tmp_v, float* tmp_s, bool enable_pdl,
    cudaStream_t stream) {
  if (tmp_v == nullptr || tmp_s == nullptr || enable_pdl) {
    return cudaErrorInvalidValue;
  }

  constexpr uint32_t vec_size = kGemmaVecSize;
  constexpr uint32_t bdx = kGemmaThreadsX;
  constexpr uint32_t bdy = 2;
  constexpr uint32_t num_threads = 128;
  constexpr uint32_t bdz = num_threads / (bdx * bdy);
  constexpr uint32_t tile_size_per_bdx = 1;
  const uint32_t num_kv_heads = params.paged_kv.num_heads;
  const uint32_t padded_batch_size = params.padded_batch_size;
  auto compute_capacity = GetCudaComputeCapability();

  DISPATCH_COMPUTE_CAP_DECODE_NUM_STAGES_SMEM(
      compute_capacity, NUM_STAGES_SMEM, {
        const uint32_t smem_size =
            2 * NUM_STAGES_SMEM * tile_size_per_bdx * bdy * bdz *
                HEAD_DIM_QK * sizeof(DTypeKV) +
            std::max(tile_size_per_bdx * num_threads * sizeof(DTypeKV*),
                     2 * bdy * bdz * sizeof(float));
        auto decode_kernel = BatchDecodeWithPagedKVCacheKernel<
            POS_ENCODING_MODE, NUM_STAGES_SMEM, tile_size_per_bdx,
            vec_size, bdx, bdy, bdz,
            Gemma4LocalSplitReducerVariant, Params>;
        FLASHINFER_CUDA_CALL(cudaFuncSetAttribute(
            decode_kernel, cudaFuncAttributeMaxDynamicSharedMemorySize,
            smem_size));

        auto output = params.o;
        auto output_lse = params.lse;
        params.partition_kv = true;
        params.o = tmp_v;
        params.lse = tmp_s;
        dim3 decode_grid(padded_batch_size, num_kv_heads);
        dim3 decode_block(bdx, bdy, bdz);
        void* decode_args[] = {(void*)&params};
        FLASHINFER_CUDA_CALL(cudaLaunchKernel(
            (void*)decode_kernel, decode_grid, decode_block, decode_args,
            smem_size, stream));

        const uint32_t reducer_blocks =
            params.paged_kv.batch_size * params.num_qo_heads;
        Gemma4VariableLengthMergeFreshKernel<Params>
            <<<reducer_blocks, kGemmaThreadsX, 0, stream>>>(
                tmp_v, tmp_s, params.o_indptr, output, output_lse,
                params.paged_kv.batch_size, params);
        FLASHINFER_CUDA_CALL(cudaGetLastError());
      });
  return cudaSuccess;
}

}  // namespace flashinfer
