#include "gradiated/engine/attention.h"
#include "gradiated/engine/gemm_attention.h"
#include "gradiated/engine/prefill_attention.h"

#include <cuda_runtime.h>
#include <cuda_bf16.h>
#include <cuda_fp8.h>

#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

void check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

class Allocation {
 public:
  explicit Allocation(std::uint64_t bytes) {
    check(cudaMalloc(&pointer_, static_cast<std::size_t>(bytes)), "cudaMalloc attention buffer");
    check(cudaMemset(pointer_, 0, static_cast<std::size_t>(bytes)), "cudaMemset attention buffer");
  }
  ~Allocation() { cudaFree(pointer_); }
  void* get() { return pointer_; }

 private:
  void* pointer_{nullptr};
};

__device__ std::uint32_t mix(std::uint32_t value) {
  value ^= value >> 16U;
  value *= 0x7feb352dU;
  value ^= value >> 15U;
  value *= 0x846ca68bU;
  return value ^ (value >> 16U);
}

__global__ void initialize_bf16(__nv_bfloat16* output, std::uint64_t elements,
                                std::uint32_t seed, float magnitude) {
  const std::uint64_t index = static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= elements) return;
  const float uniform = static_cast<float>(mix(static_cast<std::uint32_t>(index) ^ seed)) /
                        static_cast<float>(0xffffffffU);
  output[index] = __float2bfloat16_rn((2.0F * uniform - 1.0F) * magnitude);
}

__global__ void quantize_fixed_e4m3(const __nv_bfloat16* input, __nv_fp8_e4m3* output,
                                    std::uint64_t elements, float multiplier) {
  const std::uint64_t index = static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < elements) {
    output[index] = __nv_fp8_e4m3(__bfloat162float(input[index]) * multiplier);
  }
}

void fp8_parity() {
  constexpr int batch = 2;
  constexpr int kv_heads = 4;
  constexpr int query_group = 8;
  constexpr int context = 8192;
  constexpr int dimension = 512;
  constexpr std::uint64_t query_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * query_group * dimension;
  constexpr std::uint64_t cache_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * context * dimension;
  Allocation query(2ULL * query_elements), key(2ULL * cache_elements),
      value(2ULL * cache_elements), fp8_query(query_elements), fp8_key(cache_elements),
      reference(2ULL * query_elements), candidate(2ULL * query_elements),
      positions(sizeof(int) * batch);
  constexpr int threads = 256;
  initialize_bf16<<<(query_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(query.get()), query_elements, 0x12345678U, 1.75F);
  initialize_bf16<<<(cache_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(key.get()), cache_elements, 0x9abcdef0U, 0.11F);
  initialize_bf16<<<(cache_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(value.get()), cache_elements, 0x31415926U, 1.75F);
  quantize_fixed_e4m3<<<(query_elements + threads - 1) / threads, threads>>>(
      static_cast<const __nv_bfloat16*>(query.get()),
      static_cast<__nv_fp8_e4m3*>(fp8_query.get()), query_elements, 64.0F);
  quantize_fixed_e4m3<<<(cache_elements + threads - 1) / threads, threads>>>(
      static_cast<const __nv_bfloat16*>(key.get()),
      static_cast<__nv_fp8_e4m3*>(fp8_key.get()), cache_elements, 1024.0F);
  const std::vector<int> host_positions(batch, context - 1);
  check(cudaMemcpy(positions.get(), host_positions.data(), sizeof(int) * batch,
                   cudaMemcpyHostToDevice), "copy FP8 parity positions");
  gradiated::engine::GemmGroupedDecodeAttention attention(
      batch, kv_heads, query_group, context);
  attention.run_ragged_contiguous(
      query.get(), key.get(), value.get(), reference.get(),
      static_cast<const int*>(positions.get()), batch, kv_heads, query_group,
      context, dimension, 0, nullptr, context);
  attention.run_ragged_contiguous_fp8_keys(
      fp8_query.get(), fp8_key.get(), value.get(), candidate.get(),
      static_cast<const int*>(positions.get()), batch, kv_heads, query_group,
      context, dimension, 0, nullptr, context);
  check(cudaDeviceSynchronize(), "synchronize FP8-key parity");
  std::vector<__nv_bfloat16> expected(query_elements), actual(query_elements);
  check(cudaMemcpy(expected.data(), reference.get(), 2ULL * query_elements,
                   cudaMemcpyDeviceToHost), "copy FP8-key reference");
  check(cudaMemcpy(actual.data(), candidate.get(), 2ULL * query_elements,
                   cudaMemcpyDeviceToHost), "copy FP8-key candidate");
  double squared_error = 0.0;
  double squared_reference = 0.0;
  double squared_candidate = 0.0;
  double dot = 0.0;
  double mean = 0.0;
  float maximum = 0.0F;
  for (std::uint64_t index = 0; index < query_elements; ++index) {
    const float expected_value = __bfloat162float(expected[index]);
    const float actual_value = __bfloat162float(actual[index]);
    const float difference = std::abs(expected_value - actual_value);
    maximum = std::max(maximum, difference);
    mean += difference;
    squared_error += static_cast<double>(difference) * difference;
    squared_reference += static_cast<double>(expected_value) * expected_value;
    squared_candidate += static_cast<double>(actual_value) * actual_value;
    dot += static_cast<double>(expected_value) * actual_value;
  }
  std::cout << "fp8_key_parity_max_abs=" << maximum << '\n'
            << "fp8_key_parity_mean_abs=" << mean / query_elements << '\n'
            << "fp8_key_parity_relative_l2=" << std::sqrt(squared_error / squared_reference) << '\n'
            << "fp8_key_parity_cosine="
            << dot / std::sqrt(squared_reference * squared_candidate) << '\n';
}

void wgmma_qk_parity() {
  constexpr int batch = 2;
  constexpr int kv_heads = 4;
  constexpr int query_group = 8;
  constexpr int context = 128;
  constexpr int dimension = 512;
  constexpr std::uint64_t query_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * query_group * dimension;
  constexpr std::uint64_t key_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * context * dimension;
  constexpr std::uint64_t score_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * query_group * context;
  Allocation query(2ULL * query_elements), key(2ULL * key_elements),
      reference(2ULL * score_elements), candidate(2ULL * score_elements);
  constexpr int threads = 256;
  initialize_bf16<<<(query_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(query.get()), query_elements, 0x88776655U, 0.12F);
  initialize_bf16<<<(key_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(key.get()), key_elements, 0x10293847U, 0.08F);
  gradiated::engine::GemmGroupedDecodeAttention attention(
      batch, kv_heads, query_group, context);
  attention.run_qk(query.get(), key.get(), reference.get(), batch, kv_heads,
                   query_group, context, dimension, nullptr);
  gradiated::engine::grouped_global_qk_wgmma_bf16(
      query.get(), key.get(), candidate.get(), batch, kv_heads, query_group,
      context, dimension, nullptr);
  check(cudaDeviceSynchronize(), "synchronize WGMMA QK parity");
  std::vector<__nv_bfloat16> expected(score_elements), actual(score_elements);
  check(cudaMemcpy(expected.data(), reference.get(), 2ULL * score_elements,
                   cudaMemcpyDeviceToHost), "copy WGMMA QK reference");
  check(cudaMemcpy(actual.data(), candidate.get(), 2ULL * score_elements,
                   cudaMemcpyDeviceToHost), "copy WGMMA QK candidate");
  float maximum = 0.0F;
  double mean = 0.0;
  for (std::uint64_t index = 0; index < score_elements; ++index) {
    const float difference = std::abs(__bfloat162float(expected[index]) -
                                      __bfloat162float(actual[index]));
    maximum = std::max(maximum, difference);
    mean += difference;
  }
  std::cout << "wgmma_qk_parity_max_abs=" << maximum << '\n'
            << "wgmma_qk_parity_mean_abs=" << mean / score_elements << '\n';
  if (maximum > 0.02F) throw std::runtime_error("WGMMA QK parity exceeded tolerance");
}

void wgmma_attention_tile_parity() {
  constexpr int batch = 2;
  constexpr int kv_heads = 4;
  constexpr int query_group = 8;
  constexpr int context = 64;
  constexpr int dimension = 512;
  constexpr std::uint64_t query_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * query_group * dimension;
  constexpr std::uint64_t cache_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * context * dimension;
  Allocation query(2ULL * query_elements), key(2ULL * cache_elements),
      value(2ULL * cache_elements), reference(2ULL * query_elements),
      candidate(2ULL * query_elements);
  constexpr int threads = 256;
  initialize_bf16<<<(query_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(query.get()), query_elements, 0xa1b2c3d4U, 0.12F);
  initialize_bf16<<<(cache_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(key.get()), cache_elements, 0x55667788U, 0.08F);
  initialize_bf16<<<(cache_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(value.get()), cache_elements, 0xabcdef01U, 1.1F);
  gradiated::engine::GemmGroupedDecodeAttention attention(
      batch, kv_heads, query_group, context);
  attention.run(query.get(), key.get(), value.get(), reference.get(), batch, kv_heads,
                query_group, context, dimension, nullptr);
  gradiated::engine::grouped_global_attention_wgmma_tile_bf16(
      query.get(), key.get(), value.get(), candidate.get(), batch, kv_heads,
      query_group, context, dimension, nullptr);
  check(cudaDeviceSynchronize(), "synchronize WGMMA attention tile parity");
  std::vector<__nv_bfloat16> expected(query_elements), actual(query_elements);
  check(cudaMemcpy(expected.data(), reference.get(), 2ULL * query_elements,
                   cudaMemcpyDeviceToHost), "copy WGMMA attention tile reference");
  check(cudaMemcpy(actual.data(), candidate.get(), 2ULL * query_elements,
                   cudaMemcpyDeviceToHost), "copy WGMMA attention tile candidate");
  float maximum = 0.0F;
  double mean = 0.0;
  for (std::uint64_t index = 0; index < query_elements; ++index) {
    const float difference = std::abs(__bfloat162float(expected[index]) -
                                      __bfloat162float(actual[index]));
    maximum = std::max(maximum, difference);
    mean += difference;
  }
  std::cout << "wgmma_attention_tile_parity_max_abs=" << maximum << '\n'
            << "wgmma_attention_tile_parity_mean_abs=" << mean / query_elements << '\n';
  if (maximum > 0.02F) {
    throw std::runtime_error("WGMMA attention tile parity exceeded tolerance");
  }
}

void wgmma_split_attention_parity() {
  constexpr int batch = 2;
  constexpr int kv_heads = 4;
  constexpr int query_group = 8;
  constexpr int context = 128;
  constexpr int dimension = 512;
  constexpr int tiles_per_segment = 1;
  constexpr int segments_per_head = context / 64 / tiles_per_segment;
  constexpr int heads = batch * kv_heads;
  constexpr std::uint64_t query_elements =
      static_cast<std::uint64_t>(heads) * query_group * dimension;
  constexpr std::uint64_t cache_elements =
      static_cast<std::uint64_t>(heads) * context * dimension;
  constexpr std::uint64_t partial_elements =
      static_cast<std::uint64_t>(heads) * segments_per_head * query_group * dimension;
  constexpr std::uint64_t statistic_elements =
      static_cast<std::uint64_t>(heads) * segments_per_head * query_group;
  Allocation query(2ULL * query_elements), key(2ULL * cache_elements),
      value(2ULL * cache_elements), reference(2ULL * query_elements),
      candidate(2ULL * query_elements), partial(sizeof(float) * partial_elements),
      maxima(sizeof(float) * statistic_elements), sums(sizeof(float) * statistic_elements);
  constexpr int threads = 256;
  initialize_bf16<<<(query_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(query.get()), query_elements, 0x10203040U, 0.12F);
  initialize_bf16<<<(cache_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(key.get()), cache_elements, 0x50607080U, 0.08F);
  initialize_bf16<<<(cache_elements + threads - 1) / threads, threads>>>(
      static_cast<__nv_bfloat16*>(value.get()), cache_elements, 0x90abcdefU, 1.1F);
  gradiated::engine::GemmGroupedDecodeAttention attention(
      batch, kv_heads, query_group, context);
  attention.run(query.get(), key.get(), value.get(), reference.get(), batch, kv_heads,
                query_group, context, dimension, nullptr);
  gradiated::engine::grouped_global_attention_wgmma_split_bf16(
      query.get(), key.get(), value.get(), candidate.get(),
      static_cast<float*>(partial.get()), static_cast<float*>(maxima.get()),
      static_cast<float*>(sums.get()), batch, kv_heads, query_group, context, dimension,
      tiles_per_segment, nullptr);
  check(cudaDeviceSynchronize(), "synchronize split WGMMA attention parity");
  std::vector<__nv_bfloat16> expected(query_elements), actual(query_elements);
  check(cudaMemcpy(expected.data(), reference.get(), 2ULL * query_elements,
                   cudaMemcpyDeviceToHost), "copy split WGMMA reference");
  check(cudaMemcpy(actual.data(), candidate.get(), 2ULL * query_elements,
                   cudaMemcpyDeviceToHost), "copy split WGMMA candidate");
  float maximum = 0.0F;
  double mean = 0.0;
  for (std::uint64_t index = 0; index < query_elements; ++index) {
    const float difference = std::abs(__bfloat162float(expected[index]) -
                                      __bfloat162float(actual[index]));
    maximum = std::max(maximum, difference);
    mean += difference;
  }
  std::cout << "wgmma_split_attention_parity_max_abs=" << maximum << '\n'
            << "wgmma_split_attention_parity_mean_abs=" << mean / query_elements << '\n';
  if (maximum > 0.03F) {
    throw std::runtime_error("split WGMMA attention parity exceeded tolerance");
  }
}

float benchmark_split_attention(int batch, int context, int tiles_per_segment) {
  constexpr int kv_heads = 4;
  constexpr int query_group = 8;
  constexpr int dimension = 512;
  const int heads = batch * kv_heads;
  const int segments_per_head = context / 64 / tiles_per_segment;
  const std::uint64_t query_elements =
      static_cast<std::uint64_t>(heads) * query_group * dimension;
  const std::uint64_t cache_elements =
      static_cast<std::uint64_t>(heads) * context * dimension;
  const std::uint64_t partial_elements =
      static_cast<std::uint64_t>(heads) * segments_per_head * query_group * dimension;
  const std::uint64_t statistic_elements =
      static_cast<std::uint64_t>(heads) * segments_per_head * query_group;
  Allocation query(2ULL * query_elements), key(2ULL * cache_elements),
      value(2ULL * cache_elements), output(2ULL * query_elements),
      partial(sizeof(float) * partial_elements), maxima(sizeof(float) * statistic_elements),
      sums(sizeof(float) * statistic_elements);
  const auto run = [&] {
    gradiated::engine::grouped_global_attention_wgmma_split_bf16(
        query.get(), key.get(), value.get(), output.get(), static_cast<float*>(partial.get()),
        static_cast<float*>(maxima.get()), static_cast<float*>(sums.get()), batch, kv_heads,
        query_group, context, dimension, tiles_per_segment, nullptr);
  };
  for (int iteration = 0; iteration < 2; ++iteration) run();
  check(cudaDeviceSynchronize(), "split WGMMA attention warmup");
  cudaEvent_t begin{}, end{};
  check(cudaEventCreate(&begin), "create split WGMMA begin event");
  check(cudaEventCreate(&end), "create split WGMMA end event");
  constexpr int iterations = 5;
  check(cudaEventRecord(begin), "record split WGMMA begin event");
  for (int iteration = 0; iteration < iterations; ++iteration) run();
  check(cudaEventRecord(end), "record split WGMMA end event");
  check(cudaEventSynchronize(end), "synchronize split WGMMA benchmark");
  float milliseconds = 0.0F;
  check(cudaEventElapsedTime(&milliseconds, begin, end), "measure split WGMMA benchmark");
  cudaEventDestroy(end);
  cudaEventDestroy(begin);
  return milliseconds / iterations;
}

float benchmark_qk(int batch, int context, bool wgmma, int tiles_per_block = 1) {
  constexpr int kv_heads = 4;
  constexpr int query_group = 8;
  constexpr int dimension = 512;
  const std::uint64_t query_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * query_group * dimension;
  const std::uint64_t key_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * context * dimension;
  const std::uint64_t score_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * query_group * context;
  Allocation query(2ULL * query_elements), key(2ULL * key_elements),
      scores(2ULL * score_elements);
  gradiated::engine::GemmGroupedDecodeAttention attention(
      batch, kv_heads, query_group, context);
  const auto run = [&] {
    if (wgmma) {
      gradiated::engine::grouped_global_qk_wgmma_bf16(
          query.get(), key.get(), scores.get(), batch, kv_heads, query_group,
          context, dimension, nullptr, tiles_per_block);
    } else {
      attention.run_qk(query.get(), key.get(), scores.get(), batch, kv_heads,
                       query_group, context, dimension, nullptr);
    }
  };
  for (int iteration = 0; iteration < 4; ++iteration) run();
  check(cudaDeviceSynchronize(), "WGMMA QK warmup");
  cudaEvent_t begin{}, end{};
  check(cudaEventCreate(&begin), "create WGMMA QK begin event");
  check(cudaEventCreate(&end), "create WGMMA QK end event");
  constexpr int iterations = 20;
  check(cudaEventRecord(begin), "record WGMMA QK begin event");
  for (int iteration = 0; iteration < iterations; ++iteration) run();
  check(cudaEventRecord(end), "record WGMMA QK end event");
  check(cudaEventSynchronize(end), "synchronize WGMMA QK benchmark");
  float milliseconds = 0.0F;
  check(cudaEventElapsedTime(&milliseconds, begin, end), "measure WGMMA QK benchmark");
  cudaEventDestroy(end);
  cudaEventDestroy(begin);
  return milliseconds / iterations;
}

void parity() {
  constexpr int context = 127;
  constexpr int dimension = 512;
  constexpr int group = 8;
  std::vector<__nv_bfloat16> query(static_cast<std::size_t>(group * dimension));
  std::vector<__nv_bfloat16> key(static_cast<std::size_t>(context * dimension));
  std::vector<__nv_bfloat16> value(static_cast<std::size_t>(context * dimension));
  for (std::size_t index = 0; index < query.size(); ++index) {
    query[index] = __float2bfloat16_rn(0.05F * std::sin(static_cast<float>(index) * 0.013F));
  }
  for (std::size_t index = 0; index < key.size(); ++index) {
    key[index] = __float2bfloat16_rn(0.04F * std::cos(static_cast<float>(index) * 0.007F));
    value[index] = __float2bfloat16_rn(0.1F * std::sin(static_cast<float>(index) * 0.011F));
  }
  Allocation device_query(2ULL * query.size()), device_key(2ULL * key.size()),
      device_value(2ULL * value.size()), reference(2ULL * query.size()),
      candidate(2ULL * query.size());
  check(cudaMemcpy(device_query.get(), query.data(), 2ULL * query.size(), cudaMemcpyHostToDevice),
        "copy parity query");
  check(cudaMemcpy(device_key.get(), key.data(), 2ULL * key.size(), cudaMemcpyHostToDevice),
        "copy parity key");
  check(cudaMemcpy(device_value.get(), value.data(), 2ULL * value.size(), cudaMemcpyHostToDevice),
        "copy parity value");
  gradiated::engine::GemmGroupedDecodeAttention baseline(1, 1, group, context);
  baseline.run(device_query.get(), device_key.get(), device_value.get(), reference.get(),
               1, 1, group, context, dimension, nullptr);
  gradiated::engine::grouped_decode_attention_wmma_bf16(
      device_query.get(), device_key.get(), device_value.get(), candidate.get(),
      1, 1, group, context, dimension, nullptr);
  check(cudaDeviceSynchronize(), "synchronize WMMA parity");
  std::vector<__nv_bfloat16> expected(query.size()), actual(query.size());
  check(cudaMemcpy(expected.data(), reference.get(), 2ULL * expected.size(), cudaMemcpyDeviceToHost),
        "copy parity reference");
  check(cudaMemcpy(actual.data(), candidate.get(), 2ULL * actual.size(), cudaMemcpyDeviceToHost),
        "copy parity candidate");
  float maximum = 0.0F;
  double mean = 0.0;
  for (std::size_t index = 0; index < expected.size(); ++index) {
    const float difference = std::abs(__bfloat162float(expected[index]) -
                                      __bfloat162float(actual[index]));
    maximum = std::max(maximum, difference);
    mean += difference;
  }
  mean /= static_cast<double>(expected.size());
  std::cout << "wmma_parity_max_abs=" << maximum << '\n'
            << "wmma_parity_mean_abs=" << mean << '\n';
}

float benchmark(int batch, int kv_heads, int query_group, int context, int dimension,
                int implementation) {
  const std::uint64_t query_bytes = 2ULL * batch * kv_heads * query_group * dimension;
  const std::uint64_t cache_bytes = 2ULL * batch * kv_heads * context * dimension;
  const std::uint64_t query_elements = query_bytes / 2ULL;
  const std::uint64_t cache_elements = cache_bytes / 2ULL;
  Allocation query(query_bytes), key(cache_bytes), value(cache_bytes), output(query_bytes),
      fp8_query(query_elements), fp8_key(cache_elements), positions(sizeof(int) * batch);
  const std::vector<int> host_positions(batch, context - 1);
  check(cudaMemcpy(positions.get(), host_positions.data(), sizeof(int) * batch,
                   cudaMemcpyHostToDevice), "copy benchmark positions");
  gradiated::engine::GemmGroupedDecodeAttention attention(batch, kv_heads, query_group, context);
  gradiated::engine::CudnnPrefillAttention cudnn_attention;
  const auto run = [&] {
    if (implementation == 1) {
      gradiated::engine::grouped_decode_attention_bf16(
          query.get(), key.get(), value.get(), output.get(), batch, kv_heads,
          query_group, context, dimension, nullptr);
    } else if (implementation == 2) {
      gradiated::engine::grouped_decode_attention_wmma_bf16(
          query.get(), key.get(), value.get(), output.get(), batch, kv_heads,
          query_group, context, dimension, nullptr);
    } else if (implementation == 3) {
      attention.run_ragged_contiguous_fp8_keys(
          fp8_query.get(), fp8_key.get(), value.get(), output.get(),
          static_cast<const int*>(positions.get()), batch, kv_heads, query_group,
          context, dimension, 0, nullptr, context);
    } else if (implementation == 4) {
      cudnn_attention.run(
          query.get(), key.get(), value.get(), output.get(), batch,
          kv_heads * query_group, kv_heads, 1, context, context, dimension, 0, nullptr);
    } else if (implementation == 5) {
      attention.run_ragged_contiguous(
          query.get(), key.get(), value.get(), output.get(),
          static_cast<const int*>(positions.get()), batch, kv_heads, query_group,
          context, dimension, 0, nullptr, context);
    } else if (implementation == 6) {
      gradiated::engine::grouped_global_attention_wgmma_tile_bf16(
          query.get(), key.get(), value.get(), output.get(), batch, kv_heads,
          query_group, context, dimension, nullptr);
    } else {
      attention.run(query.get(), key.get(), value.get(), output.get(), batch, kv_heads,
                    query_group, context, dimension, nullptr);
    }
  };
  for (int iteration = 0; iteration < 2; ++iteration) {
    run();
  }
  check(cudaDeviceSynchronize(), "attention warmup");
  cudaEvent_t begin{}, end{};
  check(cudaEventCreate(&begin), "create begin event");
  check(cudaEventCreate(&end), "create end event");
  constexpr int iterations = 5;
  check(cudaEventRecord(begin), "record begin event");
  for (int iteration = 0; iteration < iterations; ++iteration) {
    run();
  }
  check(cudaEventRecord(end), "record end event");
  check(cudaEventSynchronize(end), "attention benchmark synchronization");
  float milliseconds = 0;
  check(cudaEventElapsedTime(&milliseconds, begin, end), "attention elapsed time");
  cudaEventDestroy(end);
  cudaEventDestroy(begin);
  return milliseconds / iterations;
}

}  // namespace

int main() {
  try {
    parity();
    fp8_parity();
    wgmma_qk_parity();
    wgmma_attention_tile_parity();
    wgmma_split_attention_parity();
    std::cout << "kind,batch,context,milliseconds,physical_kv_gb_s,naive_avoided_gb\n";
    for (const int batch : std::vector<int>{1, 2, 4, 8, 10, 16}) {
      const float sliding_ms = benchmark(batch, 16, 2, 1024, 256, 0);
      const float sliding_fused_ms = benchmark(batch, 16, 2, 1024, 256, 1);
      const double sliding_bytes = 4.0 * batch * 16 * 1024 * 256;
      std::cout << "sliding," << batch << ",1024," << std::fixed << std::setprecision(4)
                << sliding_ms << ',' << std::setprecision(2) << sliding_bytes / (sliding_ms / 1000.0) / 1e9
                << ',' << sliding_bytes / 1e9 << '\n';
      std::cout << "sliding_fused," << batch << ",1024," << std::fixed
                << std::setprecision(4) << sliding_fused_ms << ',' << std::setprecision(2)
                << sliding_bytes / (sliding_fused_ms / 1000.0) / 1e9 << ','
                << sliding_bytes / 1e9 << '\n';
      const float global_ms = benchmark(batch, 4, 8, 8192, 512, 0);
      const float global_fused_ms = benchmark(batch, 4, 8, 8192, 512, 1);
      const float global_wmma_ms = benchmark(batch, 4, 8, 8192, 512, 2);
      const float global_fp8_key_ms = benchmark(batch, 4, 8, 8192, 512, 3);
      const float global_cudnn_ms = benchmark(batch, 4, 8, 8192, 512, 4);
      const float global_ragged_ms = benchmark(batch, 4, 8, 8192, 512, 5);
      const float global_tile_baseline_ms = benchmark(batch, 4, 8, 64, 512, 0);
      const float global_tile_wgmma_ms = benchmark(batch, 4, 8, 64, 512, 6);
      std::vector<std::pair<int, float>> global_split_wgmma;
      for (const int tiles_per_segment : std::vector<int>{4, 8, 16, 32}) {
        global_split_wgmma.emplace_back(
            tiles_per_segment, benchmark_split_attention(batch, 8192, tiles_per_segment));
      }
      const float global_qk_ms = benchmark_qk(batch, 8192, false);
      std::vector<std::pair<int, float>> global_qk_wgmma;
      for (const int tiles_per_block : std::vector<int>{1, 2, 4, 8, 16, 32}) {
        global_qk_wgmma.emplace_back(
            tiles_per_block, benchmark_qk(batch, 8192, true, tiles_per_block));
      }
      const double global_bytes = 4.0 * batch * 4 * 8192 * 512;
      std::cout << "global," << batch << ",8192," << std::fixed << std::setprecision(4)
                << global_ms << ',' << std::setprecision(2) << global_bytes / (global_ms / 1000.0) / 1e9
                << ',' << 7.0 * global_bytes / 1e9 << '\n';
      std::cout << "global_fused," << batch << ",8192," << std::fixed
                << std::setprecision(4) << global_fused_ms << ',' << std::setprecision(2)
                << global_bytes / (global_fused_ms / 1000.0) / 1e9 << ','
                << 7.0 * global_bytes / 1e9 << '\n';
      std::cout << "global_wmma," << batch << ",8192," << std::fixed
                << std::setprecision(4) << global_wmma_ms << ',' << std::setprecision(2)
                << global_bytes / (global_wmma_ms / 1000.0) / 1e9 << ','
                << 7.0 * global_bytes / 1e9 << '\n';
      std::cout << "global_fp8_key," << batch << ",8192," << std::fixed
                << std::setprecision(4) << global_fp8_key_ms << ',' << std::setprecision(2)
                << (global_bytes * 0.75) / (global_fp8_key_ms / 1000.0) / 1e9 << ','
                << 7.0 * global_bytes / 1e9 << '\n';
      std::cout << "global_cudnn," << batch << ",8192," << std::fixed
                << std::setprecision(4) << global_cudnn_ms << ',' << std::setprecision(2)
                << global_bytes / (global_cudnn_ms / 1000.0) / 1e9 << ','
                << 7.0 * global_bytes / 1e9 << '\n';
      std::cout << "global_ragged," << batch << ",8192," << std::fixed
                << std::setprecision(4) << global_ragged_ms << ',' << std::setprecision(2)
                << global_bytes / (global_ragged_ms / 1000.0) / 1e9 << ','
                << 7.0 * global_bytes / 1e9 << '\n';
      std::cout << "global_tile_baseline," << batch << ",64," << std::fixed
                << std::setprecision(4) << global_tile_baseline_ms << ",0,0\n";
      std::cout << "global_tile_wgmma," << batch << ",64," << std::fixed
                << std::setprecision(4) << global_tile_wgmma_ms << ",0,0\n";
      for (const auto& [tiles_per_segment, milliseconds] : global_split_wgmma) {
        std::cout << "global_split_wgmma_t" << tiles_per_segment << ',' << batch
                  << ",8192," << std::fixed << std::setprecision(4) << milliseconds
                  << ",0,0\n";
      }
      const double global_key_bytes = global_bytes * 0.5;
      std::cout << "global_qk," << batch << ",8192," << std::fixed
                << std::setprecision(4) << global_qk_ms << ',' << std::setprecision(2)
                << global_key_bytes / (global_qk_ms / 1000.0) / 1e9 << ",0\n";
      for (const auto& [tiles_per_block, milliseconds] : global_qk_wgmma) {
        std::cout << "global_qk_wgmma_t" << tiles_per_block << ',' << batch
                  << ",8192," << std::fixed << std::setprecision(4) << milliseconds << ','
                  << std::setprecision(2)
                  << global_key_bytes / (milliseconds / 1000.0) / 1e9 << ",0\n";
      }
      const double total_ms = 50.0 * sliding_ms + 10.0 * global_ms;
      const double fused_total_ms = 50.0 * sliding_fused_ms + 10.0 * global_fused_ms;
      std::cout << "all_layers," << batch << ",8192," << std::fixed << std::setprecision(4)
                << total_ms << ",0,0\n";
      std::cout << "all_layers_fused," << batch << ",8192," << std::fixed
                << std::setprecision(4) << fused_total_ms << ",0,0\n";
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "attention benchmark failed: " << error.what() << '\n';
    return 1;
  }
}
