#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAGuard.h>
#include <c10/cuda/CUDAException.h>
#include <cooperative_groups.h>
#include <cuda_bf16.h>
#include <cuda_fp8.h>
#include <cuda_runtime.h>
#include <torch/extension.h>

#include <cstdint>
#include <limits>

namespace cg = cooperative_groups;

namespace {

constexpr int kBatch = 32;
constexpr int kRows = 12;
constexpr int kHeads = 32;
constexpr int kTileN = 64;
constexpr int kValueSlice = 256;
constexpr int kThreads = 256;
constexpr int kOriginalPrefix = 4214;

template <int HeadDim, int KvHeads, int Prefix, int ClusterSize, bool Local>
__global__ void packed_m384_streaming_cluster_kernel(
    const __nv_bfloat16* q,
    const __nv_bfloat16* k_extend,
    const __nv_bfloat16* v_extend,
    __nv_bfloat16* output,
    const __nv_fp8_e4m3* k_cache,
    const __nv_fp8_e4m3* v_cache,
    const int32_t* qo_indptr,
    const int32_t* kv_indptr,
    const int32_t* kv_indices,
    const bool* custom_mask,
    const int32_t* mask_indptr,
    float k_scale,
    float v_scale,
    float sm_scale) {
  cg::cluster_group cluster = cg::this_cluster();
  const int cluster_rank = static_cast<int>(cluster.block_rank());
  const int cluster_index = static_cast<int>(blockIdx.x) / ClusterSize;
  const int sequence = cluster_index / kHeads;
  const int query_head = cluster_index % kHeads;
  const int kv_group = kHeads / KvHeads;
  const int kv_head = query_head / kv_group;
  const int query_start = qo_indptr[sequence];
  const int prefix_start = kv_indptr[sequence];
  const int value_base = cluster_rank * kValueSlice;

  extern __shared__ __align__(16) unsigned char storage[];
  auto* k_stage = storage;
  auto* v_stage = k_stage + kTileN * HeadDim;
  auto* q_stage = reinterpret_cast<__nv_bfloat16*>(
      v_stage + kTileN * kValueSlice);
  auto* score_stage = reinterpret_cast<float*>(
      reinterpret_cast<unsigned char*>(q_stage) +
      kRows * HeadDim * sizeof(__nv_bfloat16));
  auto* old_scale_stage = score_stage + kRows * kTileN;
  auto* running_max_stage = old_scale_stage + kRows;
  auto* running_sum_stage = running_max_stage + kRows;

  float* producer_scores = cluster.map_shared_rank(score_stage, 0);
  float* producer_old_scale = cluster.map_shared_rank(old_scale_stage, 0);
  float* producer_running_sum = cluster.map_shared_rank(running_sum_stage, 0);

  float accumulator[kRows];
#pragma unroll
  for (int row = 0; row < kRows; ++row) {
    accumulator[row] = 0.0F;
  }
  if (cluster_rank == 0) {
    for (int index = threadIdx.x; index < kRows * HeadDim;
         index += blockDim.x) {
      const int row = index / HeadDim;
      const int dimension = index - row * HeadDim;
      const int64_t q_offset =
          (static_cast<int64_t>(query_start + row) * kHeads + query_head) *
              HeadDim +
          dimension;
      q_stage[index] = q[q_offset];
    }
  }
  if (cluster_rank == 0 && threadIdx.x < kRows) {
    running_max_stage[threadIdx.x] = -CUDART_INF_F;
    running_sum_stage[threadIdx.x] = 0.0F;
    old_scale_stage[threadIdx.x] = 0.0F;
  }
  __syncthreads();
  cluster.sync();

  for (int tile_start = 0; tile_start < Prefix; tile_start += kTileN) {
    if (cluster_rank == 0) {
      for (int index = threadIdx.x; index < kTileN * HeadDim;
           index += blockDim.x) {
        const int column = index / HeadDim;
        const int dimension = index - column * HeadDim;
        const int logical_column = tile_start + column;
        unsigned char value = 0;
        if (logical_column < Prefix) {
          const int physical_slot =
              kv_indices[prefix_start + logical_column];
          const int64_t offset =
              (static_cast<int64_t>(physical_slot) * KvHeads + kv_head) *
                  HeadDim +
              dimension;
          value = reinterpret_cast<const unsigned char*>(k_cache)[offset];
        }
        k_stage[index] = value;
      }
    }
    for (int index = threadIdx.x; index < kTileN * kValueSlice;
         index += blockDim.x) {
      const int column = index / kValueSlice;
      const int dimension = index - column * kValueSlice;
      const int logical_column = tile_start + column;
      unsigned char value = 0;
      if (logical_column < Prefix) {
        const int physical_slot = kv_indices[prefix_start + logical_column];
        const int64_t offset =
            (static_cast<int64_t>(physical_slot) * KvHeads + kv_head) *
                HeadDim +
            value_base + dimension;
        value = reinterpret_cast<const unsigned char*>(v_cache)[offset];
      }
      v_stage[index] = value;
    }
    __syncthreads();

    if (cluster_rank == 0) {
      for (int score_index = threadIdx.x;
           score_index < kRows * kTileN;
           score_index += blockDim.x) {
        const int row = score_index / kTileN;
        const int column = score_index - row * kTileN;
        const int logical_column = tile_start + column;
        bool valid = logical_column < Prefix;
        if constexpr (Local) {
          valid = valid && logical_column >= row;
        }
        float score = -CUDART_INF_F;
        if (valid) {
          float dot = 0.0F;
          const int q_base = row * HeadDim;
          const int k_base = column * HeadDim;
          for (int dimension = 0; dimension < HeadDim; ++dimension) {
            const float q_value =
                __bfloat162float(q_stage[q_base + dimension]);
            const auto k_value = reinterpret_cast<const __nv_fp8_e4m3*>(
                k_stage)[k_base + dimension];
            dot = fmaf(q_value, static_cast<float>(k_value), dot);
          }
          score = dot * (sm_scale * k_scale);
        }
        score_stage[score_index] = score;
      }
      __syncthreads();
      if (threadIdx.x < kRows) {
        const int row = threadIdx.x;
        float tile_max = -CUDART_INF_F;
#pragma unroll
        for (int column = 0; column < kTileN; ++column) {
          tile_max = fmaxf(tile_max, score_stage[row * kTileN + column]);
        }
        const float previous_max = running_max_stage[row];
        const float new_max = fmaxf(previous_max, tile_max);
        const float old_scale =
            isinf(previous_max) ? 0.0F : __expf(previous_max - new_max);
        float tile_sum = 0.0F;
#pragma unroll
        for (int column = 0; column < kTileN; ++column) {
          const float score = score_stage[row * kTileN + column];
          const float probability =
              isinf(score) ? 0.0F : __expf(score - new_max);
          score_stage[row * kTileN + column] = probability;
          tile_sum += probability;
        }
        running_max_stage[row] = new_max;
        running_sum_stage[row] =
            running_sum_stage[row] * old_scale + tile_sum;
        old_scale_stage[row] = old_scale;
      }
      __syncthreads();
    }
    cluster.sync();

    if (threadIdx.x < kValueSlice) {
#pragma unroll
      for (int row = 0; row < kRows; ++row) {
        accumulator[row] *= producer_old_scale[row];
      }
#pragma unroll
      for (int column = 0; column < kTileN; ++column) {
        const auto v_value = reinterpret_cast<const __nv_fp8_e4m3*>(
            v_stage)[column * kValueSlice + threadIdx.x];
        const float scaled_value = static_cast<float>(v_value) * v_scale;
#pragma unroll
        for (int row = 0; row < kRows; ++row) {
          accumulator[row] = fmaf(
              producer_scores[row * kTileN + column],
              scaled_value,
              accumulator[row]);
        }
      }
    }
    cluster.sync();
  }

  if (cluster_rank == 0) {
    for (int score_index = threadIdx.x;
         score_index < kRows * kTileN;
         score_index += blockDim.x) {
      const int row = score_index / kTileN;
      const int column = score_index - row * kTileN;
      bool valid = column < kRows && row >= column;
      if (valid && custom_mask != nullptr) {
        const int mask_start = mask_indptr[sequence];
        valid = custom_mask[
            mask_start + row * (kOriginalPrefix + kRows) +
            kOriginalPrefix + column];
      }
      float score = -CUDART_INF_F;
      if (valid) {
        float dot = 0.0F;
        const int q_base = row * HeadDim;
        const int64_t k_base =
            (static_cast<int64_t>(query_start + column) * KvHeads + kv_head) *
            HeadDim;
        for (int dimension = 0; dimension < HeadDim; ++dimension) {
          dot = fmaf(
              __bfloat162float(q_stage[q_base + dimension]),
              __bfloat162float(k_extend[k_base + dimension]),
              dot);
        }
        score = dot * sm_scale;
      }
      score_stage[score_index] = score;
    }
    __syncthreads();
    if (threadIdx.x < kRows) {
      const int row = threadIdx.x;
      float tile_max = -CUDART_INF_F;
#pragma unroll
      for (int column = 0; column < kTileN; ++column) {
        tile_max = fmaxf(tile_max, score_stage[row * kTileN + column]);
      }
      const float previous_max = running_max_stage[row];
      const float new_max = fmaxf(previous_max, tile_max);
      const float old_scale =
          isinf(previous_max) ? 0.0F : __expf(previous_max - new_max);
      float tile_sum = 0.0F;
#pragma unroll
      for (int column = 0; column < kTileN; ++column) {
        const float score = score_stage[row * kTileN + column];
        const float probability =
            isinf(score) ? 0.0F : __expf(score - new_max);
        score_stage[row * kTileN + column] = probability;
        tile_sum += probability;
      }
      running_max_stage[row] = new_max;
      running_sum_stage[row] =
          running_sum_stage[row] * old_scale + tile_sum;
      old_scale_stage[row] = old_scale;
    }
    __syncthreads();
  }
  cluster.sync();

  if (threadIdx.x < kValueSlice) {
#pragma unroll
    for (int row = 0; row < kRows; ++row) {
      accumulator[row] *= producer_old_scale[row];
    }
#pragma unroll
    for (int column = 0; column < kRows; ++column) {
      const int64_t v_base =
          (static_cast<int64_t>(query_start + column) * KvHeads + kv_head) *
              HeadDim +
          value_base + threadIdx.x;
      const float value = __bfloat162float(v_extend[v_base]);
#pragma unroll
      for (int row = 0; row < kRows; ++row) {
        accumulator[row] = fmaf(
            producer_scores[row * kTileN + column],
            value,
            accumulator[row]);
      }
    }
  }
  cluster.sync();

  if (threadIdx.x < kValueSlice) {
#pragma unroll
    for (int row = 0; row < kRows; ++row) {
      const int64_t output_offset =
          (static_cast<int64_t>(query_start + row) * kHeads + query_head) *
              HeadDim +
          value_base + threadIdx.x;
      output[output_offset] = __float2bfloat16_rn(
          accumulator[row] / producer_running_sum[row]);
    }
  }
}

template <int HeadDim, int KvHeads, int Prefix, int ClusterSize, bool Local>
void launch_exact(
    const torch::Tensor& q,
    const torch::Tensor& k_extend,
    const torch::Tensor& v_extend,
    torch::Tensor& output,
    const torch::Tensor& k_cache,
    const torch::Tensor& v_cache,
    const torch::Tensor& qo_indptr,
    const torch::Tensor& kv_indptr,
    const torch::Tensor& kv_indices,
    const c10::optional<torch::Tensor>& custom_mask,
    const c10::optional<torch::Tensor>& mask_indptr,
    float k_scale,
    float v_scale,
    float sm_scale) {
  constexpr int shared_bytes =
      kTileN * HeadDim + kTileN * kValueSlice +
      kRows * HeadDim * sizeof(__nv_bfloat16) +
      (kRows * kTileN + 3 * kRows) * sizeof(float);
  auto kernel =
      packed_m384_streaming_cluster_kernel<
          HeadDim,
          KvHeads,
          Prefix,
          ClusterSize,
          Local>;
  TORCH_CHECK(
      cudaFuncSetAttribute(
          kernel,
          cudaFuncAttributeMaxDynamicSharedMemorySize,
          shared_bytes) == cudaSuccess,
      "packed_m384_streaming_shared_memory_attribute_failed");

  cudaLaunchConfig_t config{};
  config.gridDim = dim3(kBatch * kHeads * ClusterSize, 1, 1);
  config.blockDim = dim3(kThreads, 1, 1);
  config.dynamicSmemBytes = shared_bytes;
  config.stream = at::cuda::getCurrentCUDAStream();
  cudaLaunchAttribute attribute{};
  attribute.id = cudaLaunchAttributeClusterDimension;
  attribute.val.clusterDim = dim3(ClusterSize, 1, 1);
  config.attrs = &attribute;
  config.numAttrs = 1;

  const bool* mask_pointer =
      custom_mask.has_value() ? custom_mask->data_ptr<bool>() : nullptr;
  const int32_t* mask_indptr_pointer =
      mask_indptr.has_value() ? mask_indptr->data_ptr<int32_t>() : nullptr;
  TORCH_CHECK(
      cudaLaunchKernelEx(
          &config,
          kernel,
          reinterpret_cast<const __nv_bfloat16*>(
              q.data_ptr<at::BFloat16>()),
          reinterpret_cast<const __nv_bfloat16*>(
              k_extend.data_ptr<at::BFloat16>()),
          reinterpret_cast<const __nv_bfloat16*>(
              v_extend.data_ptr<at::BFloat16>()),
          reinterpret_cast<__nv_bfloat16*>(
              output.data_ptr<at::BFloat16>()),
          reinterpret_cast<const __nv_fp8_e4m3*>(k_cache.data_ptr()),
          reinterpret_cast<const __nv_fp8_e4m3*>(v_cache.data_ptr()),
          qo_indptr.data_ptr<int32_t>(),
          kv_indptr.data_ptr<int32_t>(),
          kv_indices.data_ptr<int32_t>(),
          mask_pointer,
          mask_indptr_pointer,
          k_scale,
          v_scale,
          sm_scale) == cudaSuccess,
      "packed_m384_streaming_cluster_launch_failed");
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}

void validate_common(
    const torch::Tensor& q,
    const torch::Tensor& k_extend,
    const torch::Tensor& v_extend,
    const torch::Tensor& output,
    const torch::Tensor& k_cache,
    const torch::Tensor& v_cache,
    const torch::Tensor& qo_indptr,
    const torch::Tensor& kv_indptr,
    const torch::Tensor& kv_indices) {
  TORCH_CHECK(q.is_cuda(), "packed_m384_streaming_cuda_required");
  TORCH_CHECK(
      q.scalar_type() == at::kBFloat16 &&
          k_extend.scalar_type() == at::kBFloat16 &&
          v_extend.scalar_type() == at::kBFloat16 &&
          output.scalar_type() == at::kBFloat16,
      "packed_m384_streaming_bfloat16_extend_required");
  TORCH_CHECK(
      k_cache.scalar_type() == at::kFloat8_e4m3fn &&
          v_cache.scalar_type() == at::kFloat8_e4m3fn,
      "packed_m384_streaming_e4m3_cache_required");
  TORCH_CHECK(
      q.is_contiguous() && k_extend.is_contiguous() &&
          v_extend.is_contiguous() && output.is_contiguous() &&
          k_cache.is_contiguous() && v_cache.is_contiguous(),
      "packed_m384_streaming_contiguous_required");
  TORCH_CHECK(
      q.sizes()[0] == kBatch * kRows && q.sizes()[1] == kHeads,
      "packed_m384_streaming_m384_h32_required");
  TORCH_CHECK(
      qo_indptr.numel() == kBatch + 1 &&
          kv_indptr.numel() == kBatch + 1,
      "packed_m384_streaming_indptr_shape_required");
  TORCH_CHECK(
      kv_indices.scalar_type() == at::kInt,
      "packed_m384_streaming_int32_indices_required");
}

}  // namespace

void packed_m384_streaming_forward(
    torch::Tensor q,
    torch::Tensor k_extend,
    torch::Tensor v_extend,
    torch::Tensor output,
    torch::Tensor k_cache,
    torch::Tensor v_cache,
    torch::Tensor qo_indptr,
    torch::Tensor kv_indptr,
    torch::Tensor kv_indices,
    c10::optional<torch::Tensor> custom_mask,
    c10::optional<torch::Tensor> mask_indptr,
    bool local,
    double k_scale,
    double v_scale,
    double sm_scale) {
  validate_common(
      q,
      k_extend,
      v_extend,
      output,
      k_cache,
      v_cache,
      qo_indptr,
      kv_indptr,
      kv_indices);
  c10::cuda::CUDAGuard device_guard(q.device());
  int device = -1;
  cudaDeviceProp properties{};
  C10_CUDA_CHECK(cudaGetDevice(&device));
  C10_CUDA_CHECK(cudaGetDeviceProperties(&properties, device));
  TORCH_CHECK(
      properties.major == 9 && properties.minor == 0,
      "packed_m384_streaming_sm90_required");
  if (local) {
    TORCH_CHECK(
        q.sizes()[2] == 256 && k_extend.sizes()[1] == 16 &&
            kv_indices.numel() == kBatch * 1024,
        "packed_m384_streaming_local_geometry_required");
    launch_exact<256, 16, 1024, 1, true>(
        q,
        k_extend,
        v_extend,
        output,
        k_cache,
        v_cache,
        qo_indptr,
        kv_indptr,
        kv_indices,
        custom_mask,
        mask_indptr,
        static_cast<float>(k_scale),
        static_cast<float>(v_scale),
        static_cast<float>(sm_scale));
  } else {
    TORCH_CHECK(
        q.sizes()[2] == 512 && k_extend.sizes()[1] == 4 &&
            kv_indices.numel() == kBatch * 4214,
        "packed_m384_streaming_global_geometry_required");
    launch_exact<512, 4, 4214, 2, false>(
        q,
        k_extend,
        v_extend,
        output,
        k_cache,
        v_cache,
        qo_indptr,
        kv_indptr,
        kv_indices,
        custom_mask,
        mask_indptr,
        static_cast<float>(k_scale),
        static_cast<float>(v_scale),
        static_cast<float>(sm_scale));
  }
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def(
      "forward",
      &packed_m384_streaming_forward,
      "Packed M384 streaming cluster attention");
}
