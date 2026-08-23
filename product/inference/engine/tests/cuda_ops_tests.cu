#include "gradiated/engine/cuda_ops.h"
#include "gradiated/engine/attention.h"
#include "gradiated/engine/linear.h"
#include "gradiated/engine/gemm_attention.h"
#include "gradiated/engine/prefill_gemm_attention.h"
#include "gradiated/engine/qkv.h"

#include <cuda_bf16.h>
#include <cuda_runtime.h>

#include <array>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void cuda_check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

void near(float actual, float expected, float tolerance, const char* operation) {
  if (std::abs(actual - expected) > tolerance) {
    throw std::runtime_error(std::string(operation) + ": expected " + std::to_string(expected) +
                             ", got " + std::to_string(actual));
  }
}

template <std::size_t Size>
std::array<__nv_bfloat16, Size> bf16(const std::array<float, Size>& values) {
  std::array<__nv_bfloat16, Size> result{};
  for (std::size_t index = 0; index < Size; ++index) result[index] = __float2bfloat16(values[index]);
  return result;
}

template <typename T>
class DeviceAllocation {
 public:
  explicit DeviceAllocation(std::size_t elements) {
    cuda_check(cudaMalloc(&pointer_, elements * sizeof(T)), "cudaMalloc");
  }
  ~DeviceAllocation() { cudaFree(pointer_); }
  T* get() { return static_cast<T*>(pointer_); }
  const T* get() const { return static_cast<const T*>(pointer_); }

 private:
  void* pointer_{nullptr};
};

void test_norm_add_and_scale() {
  constexpr std::size_t width = 8;
  const auto input = bf16<width>({1, 2, 3, 4, 5, 6, 7, 8});
  const auto weight = bf16<width>({1, 1, 1, 1, 1, 1, 1, 1});
  const auto residual = bf16<width>({0.5F, 0.5F, 0.5F, 0.5F, 0.5F, 0.5F, 0.5F, 0.5F});
  const auto scalar = bf16<1>({0.5F});
  DeviceAllocation<__nv_bfloat16> device_input(width), device_weight(width), device_residual(width),
      device_output(width), device_fused_output(width), device_first_residual(width),
      device_fused_first_residual(width), device_normalized(width),
      device_fused_normalized(width), device_scalar(1);
  cuda_check(cudaMemcpy(device_input.get(), input.data(), sizeof(input), cudaMemcpyHostToDevice), "copy input");
  cuda_check(cudaMemcpy(device_weight.get(), weight.data(), sizeof(weight), cudaMemcpyHostToDevice), "copy weight");
  cuda_check(cudaMemcpy(device_residual.get(), residual.data(), sizeof(residual), cudaMemcpyHostToDevice),
             "copy residual");
  cuda_check(cudaMemcpy(device_scalar.get(), scalar.data(), sizeof(scalar), cudaMemcpyHostToDevice), "copy scalar");
  gradiated::engine::rms_norm_add_bf16(device_input.get(), device_weight.get(), device_residual.get(),
                                       device_output.get(), 1, width, 1e-6F, nullptr);
  gradiated::engine::scale_bf16(device_output.get(), device_scalar.get(), width, nullptr);
  gradiated::engine::rms_norm_add_scale_bf16(
      device_input.get(), device_weight.get(), device_residual.get(), device_scalar.get(),
      device_fused_output.get(), 1, width, 1e-6F, nullptr);
  gradiated::engine::rms_norm_add_bf16(
      device_input.get(), device_weight.get(), device_residual.get(), device_first_residual.get(),
      1, width, 1e-6F, nullptr);
  gradiated::engine::rms_norm_bf16(device_first_residual.get(), device_weight.get(),
                                   device_normalized.get(), 1, width, 1e-6F, nullptr);
  gradiated::engine::rms_norm_add_and_norm_bf16(
      device_input.get(), device_weight.get(), device_residual.get(), device_weight.get(),
      device_fused_first_residual.get(), device_fused_normalized.get(), 1, width, 1e-6F, nullptr);
  cuda_check(cudaDeviceSynchronize(), "norm synchronization");
  std::array<__nv_bfloat16, width> output{};
  std::array<__nv_bfloat16, width> fused_output{}, first_residual{}, fused_first_residual{},
      normalized{}, fused_normalized{};
  cuda_check(cudaMemcpy(output.data(), device_output.get(), sizeof(output), cudaMemcpyDeviceToHost), "copy output");
  cuda_check(cudaMemcpy(fused_output.data(), device_fused_output.get(), sizeof(fused_output),
                        cudaMemcpyDeviceToHost), "copy fused output");
  cuda_check(cudaMemcpy(first_residual.data(), device_first_residual.get(), sizeof(first_residual),
                        cudaMemcpyDeviceToHost), "copy first residual");
  cuda_check(cudaMemcpy(fused_first_residual.data(), device_fused_first_residual.get(),
                        sizeof(fused_first_residual), cudaMemcpyDeviceToHost),
             "copy fused first residual");
  cuda_check(cudaMemcpy(normalized.data(), device_normalized.get(), sizeof(normalized),
                        cudaMemcpyDeviceToHost), "copy normalized");
  cuda_check(cudaMemcpy(fused_normalized.data(), device_fused_normalized.get(),
                        sizeof(fused_normalized), cudaMemcpyDeviceToHost), "copy fused normalized");
  float mean_square = 0.0F;
  for (const auto value : input) {
    const float converted = __bfloat162float(value);
    mean_square += converted * converted;
  }
  mean_square /= static_cast<float>(width);
  for (std::size_t index = 0; index < width; ++index) {
    const float expected = (__bfloat162float(input[index]) / std::sqrt(mean_square + 1e-6F) + 0.5F) * 0.5F;
    near(__bfloat162float(output[index]), expected, 0.012F, "rms_norm_add/scale");
  }
  if (std::memcmp(output.data(), fused_output.data(), sizeof(output)) != 0 ||
      std::memcmp(first_residual.data(), fused_first_residual.data(), sizeof(first_residual)) != 0 ||
      std::memcmp(normalized.data(), fused_normalized.data(), sizeof(normalized)) != 0) {
    throw std::runtime_error("fused normalization changed BF16 rounding");
  }
}

void test_gelu_gate() {
  const auto gate = bf16<4>({-1.0F, 0.0F, 1.0F, 2.0F});
  const auto up = bf16<4>({2.0F, 2.0F, 2.0F, 2.0F});
  DeviceAllocation<__nv_bfloat16> device_gate(4), device_up(4), device_output(4);
  cuda_check(cudaMemcpy(device_gate.get(), gate.data(), sizeof(gate), cudaMemcpyHostToDevice), "copy gate");
  cuda_check(cudaMemcpy(device_up.get(), up.data(), sizeof(up), cudaMemcpyHostToDevice), "copy up");
  gradiated::engine::gelu_tanh_gate_bf16(device_gate.get(), device_up.get(), device_output.get(), 4, nullptr);
  cuda_check(cudaDeviceSynchronize(), "gelu synchronization");
  std::array<__nv_bfloat16, 4> output{};
  cuda_check(cudaMemcpy(output.data(), device_output.get(), sizeof(output), cudaMemcpyDeviceToHost), "copy gelu");
  for (std::size_t index = 0; index < output.size(); ++index) {
    const float value = __bfloat162float(gate[index]);
    const float expected = value * (1.0F + std::tanh(0.7978845608028654F *
        (value + 0.044715F * value * value * value)));
    near(__bfloat162float(output[index]), expected, 0.02F, "gelu gate");
  }
}

void test_linear() {
  const auto input = bf16<6>({1, 2, 3, 4, 5, 6});
  const auto weight = bf16<12>({1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1});
  DeviceAllocation<__nv_bfloat16> device_input(6), device_weight(12), device_output(8);
  cuda_check(cudaMemcpy(device_input.get(), input.data(), sizeof(input), cudaMemcpyHostToDevice), "copy linear input");
  cuda_check(cudaMemcpy(device_weight.get(), weight.data(), sizeof(weight), cudaMemcpyHostToDevice),
             "copy linear weight");
  gradiated::engine::Bf16Linear linear;
  linear.run(device_input.get(), device_weight.get(), device_output.get(), 2, 3, 4, nullptr);
  cuda_check(cudaDeviceSynchronize(), "linear synchronization");
  std::array<__nv_bfloat16, 8> output{};
  cuda_check(cudaMemcpy(output.data(), device_output.get(), sizeof(output), cudaMemcpyDeviceToHost),
             "copy linear output");
  const std::array<float, 8> expected{1, 2, 3, 6, 4, 5, 6, 15};
  for (std::size_t index = 0; index < output.size(); ++index) {
    near(__bfloat162float(output[index]), expected[index], 0.01F, "linear");
  }
}

void test_grouped_attention() {
  constexpr int context = 3;
  constexpr int dimension = 256;
  constexpr int group = 2;
  std::array<float, group * dimension> query_values{};
  std::array<float, context * dimension> key_values{};
  std::array<float, context * dimension> value_values{};
  for (int token = 0; token < context; ++token) {
    for (int index = 0; index < dimension; ++index) {
      value_values[token * dimension + index] = static_cast<float>(token + 1) +
                                                 static_cast<float>(index % 7) / 16.0F;
    }
  }
  const auto query = bf16<group * dimension>(query_values);
  const auto key = bf16<context * dimension>(key_values);
  const auto value = bf16<context * dimension>(value_values);
  DeviceAllocation<__nv_bfloat16> device_query(query.size()), device_key(key.size()),
      device_value(value.size()), device_output(query.size());
  cuda_check(cudaMemcpy(device_query.get(), query.data(), sizeof(query), cudaMemcpyHostToDevice),
             "copy attention query");
  cuda_check(cudaMemcpy(device_key.get(), key.data(), sizeof(key), cudaMemcpyHostToDevice),
             "copy attention key");
  cuda_check(cudaMemcpy(device_value.get(), value.data(), sizeof(value), cudaMemcpyHostToDevice),
             "copy attention value");
  gradiated::engine::grouped_decode_attention_bf16(device_query.get(), device_key.get(),
      device_value.get(), device_output.get(), 1, 1, group, context, dimension, nullptr);
  cuda_check(cudaDeviceSynchronize(), "attention synchronization");
  std::array<__nv_bfloat16, group * dimension> output{};
  cuda_check(cudaMemcpy(output.data(), device_output.get(), sizeof(output), cudaMemcpyDeviceToHost),
             "copy attention output");
  for (int query_index = 0; query_index < group; ++query_index) {
    for (int index = 0; index < dimension; ++index) {
      const float expected = 2.0F + static_cast<float>(index % 7) / 16.0F;
      near(__bfloat162float(output[query_index * dimension + index]), expected, 0.02F,
           "grouped attention");
    }
  }
  gradiated::engine::GemmGroupedDecodeAttention gemm_attention(1, 1, group, context);
  gemm_attention.run(device_query.get(), device_key.get(), device_value.get(), device_output.get(),
                     1, 1, group, context, dimension, nullptr);
  cuda_check(cudaDeviceSynchronize(), "GEMM attention synchronization");
  cuda_check(cudaMemcpy(output.data(), device_output.get(), sizeof(output), cudaMemcpyDeviceToHost),
             "copy GEMM attention output");
  for (int query_index = 0; query_index < group; ++query_index) {
    for (int index = 0; index < dimension; ++index) {
      const float expected = 2.0F + static_cast<float>(index % 7) / 16.0F;
      near(__bfloat162float(output[query_index * dimension + index]), expected, 0.02F,
           "GEMM grouped attention");
    }
  }
}

void test_shared_global_kv_roundtrip() {
  constexpr int tokens = 7;
  constexpr int query_heads = 32;
  constexpr int kv_heads = 4;
  constexpr int dimension = 512;
  constexpr int query_width = query_heads * dimension;
  constexpr int packed_width = query_width + kv_heads * dimension;
  constexpr int capacity = 64;
  constexpr int maximum_slots = 4;
  constexpr std::size_t packed_elements = static_cast<std::size_t>(tokens) * packed_width;
  constexpr std::size_t positioned_cache_elements =
      static_cast<std::size_t>(kv_heads) * capacity * dimension;
  constexpr std::size_t ragged_cache_elements =
      static_cast<std::size_t>(maximum_slots) * kv_heads * capacity * dimension;
  constexpr std::size_t query_elements =
      static_cast<std::size_t>(tokens) * query_heads * dimension;
  std::vector<__nv_bfloat16> packed(packed_elements);
  std::vector<__nv_bfloat16> norm_weight(dimension);
  for (std::size_t index = 0; index < packed.size(); ++index) {
    packed[index] = __float2bfloat16_rn(
        0.75F * std::sin(static_cast<float>(index) * 0.00137F) +
        0.2F * std::cos(static_cast<float>(index) * 0.00311F));
  }
  for (int index = 0; index < dimension; ++index) {
    norm_weight[static_cast<std::size_t>(index)] = __float2bfloat16_rn(
        0.055F + 0.01F * std::sin(static_cast<float>(index) * 0.017F));
  }
  DeviceAllocation<__nv_bfloat16> device_packed(packed_elements),
      device_norm(dimension), baseline_queries(query_elements), candidate_queries(query_elements),
      baseline_keys(ragged_cache_elements), baseline_values(ragged_cache_elements),
      candidate_keys(ragged_cache_elements), candidate_values(ragged_cache_elements);
  DeviceAllocation<int> device_positions(tokens), device_slots(tokens);
  cuda_check(cudaMemcpy(device_packed.get(), packed.data(), packed.size() * sizeof(packed[0]),
                        cudaMemcpyHostToDevice), "copy shared global packed input");
  cuda_check(cudaMemcpy(device_norm.get(), norm_weight.data(),
                        norm_weight.size() * sizeof(norm_weight[0]), cudaMemcpyHostToDevice),
             "copy shared global norm weight");
  unsetenv("GRADIATED_SHARED_GLOBAL_KV_ROUNDTRIP");
  gradiated::engine::Gemma4QkvPostprocessor baseline(capacity);
  setenv("GRADIATED_SHARED_GLOBAL_KV_ROUNDTRIP", "1", 1);
  gradiated::engine::Gemma4QkvPostprocessor candidate(capacity);
  unsetenv("GRADIATED_SHARED_GLOBAL_KV_ROUNDTRIP");

  auto zero_outputs = [&] {
    cuda_check(cudaMemset(baseline_keys.get(), 0,
                          ragged_cache_elements * sizeof(__nv_bfloat16)),
               "zero baseline shared global keys");
    cuda_check(cudaMemset(baseline_values.get(), 0,
                          ragged_cache_elements * sizeof(__nv_bfloat16)),
               "zero baseline shared global values");
    cuda_check(cudaMemset(candidate_keys.get(), 0,
                          ragged_cache_elements * sizeof(__nv_bfloat16)),
               "zero candidate shared global keys");
    cuda_check(cudaMemset(candidate_values.get(), 0,
                          ragged_cache_elements * sizeof(__nv_bfloat16)),
               "zero candidate shared global values");
  };
  auto require_identical = [&](std::size_t cache_elements, std::size_t compared_queries,
                               const char* operation) {
    cuda_check(cudaDeviceSynchronize(), "synchronize shared global KV roundtrip");
    std::vector<__nv_bfloat16> expected_keys(cache_elements), actual_keys(cache_elements),
        expected_values(cache_elements), actual_values(cache_elements),
        expected_queries(compared_queries), actual_queries(compared_queries);
    cuda_check(cudaMemcpy(expected_keys.data(), baseline_keys.get(),
                          cache_elements * sizeof(__nv_bfloat16), cudaMemcpyDeviceToHost),
               "copy baseline shared global keys");
    cuda_check(cudaMemcpy(actual_keys.data(), candidate_keys.get(),
                          cache_elements * sizeof(__nv_bfloat16), cudaMemcpyDeviceToHost),
               "copy candidate shared global keys");
    cuda_check(cudaMemcpy(expected_values.data(), baseline_values.get(),
                          cache_elements * sizeof(__nv_bfloat16), cudaMemcpyDeviceToHost),
               "copy baseline shared global values");
    cuda_check(cudaMemcpy(actual_values.data(), candidate_values.get(),
                          cache_elements * sizeof(__nv_bfloat16), cudaMemcpyDeviceToHost),
               "copy candidate shared global values");
    cuda_check(cudaMemcpy(expected_queries.data(), baseline_queries.get(),
                          compared_queries * sizeof(__nv_bfloat16), cudaMemcpyDeviceToHost),
               "copy baseline shared global queries");
    cuda_check(cudaMemcpy(actual_queries.data(), candidate_queries.get(),
                          compared_queries * sizeof(__nv_bfloat16), cudaMemcpyDeviceToHost),
               "copy candidate shared global queries");
    if (std::memcmp(expected_keys.data(), actual_keys.data(),
                    cache_elements * sizeof(__nv_bfloat16)) != 0 ||
        std::memcmp(expected_values.data(), actual_values.data(),
                    cache_elements * sizeof(__nv_bfloat16)) != 0 ||
        std::memcmp(expected_queries.data(), actual_queries.data(),
                    compared_queries * sizeof(__nv_bfloat16)) != 0) {
      throw std::runtime_error(std::string(operation) + " changed BF16 output bits");
    }
  };

  zero_outputs();
  baseline.run_positioned(
      device_packed.get(), device_norm.get(), device_norm.get(), baseline_queries.get(),
      baseline_keys.get(), baseline_values.get(), tokens, query_heads, kv_heads, dimension,
      true, 9, 9, capacity, 1e-6F, nullptr);
  candidate.run_positioned(
      device_packed.get(), device_norm.get(), device_norm.get(), candidate_queries.get(),
      candidate_keys.get(), candidate_values.get(), tokens, query_heads, kv_heads, dimension,
      true, 9, 9, capacity, 1e-6F, nullptr);
  require_identical(positioned_cache_elements, query_elements,
                    "positioned shared global KV roundtrip");

  const std::array<int, maximum_slots> positions{3, 17, 31, 47};
  const std::array<int, maximum_slots> slots{3, 0, 2, 1};
  cuda_check(cudaMemcpy(device_positions.get(), positions.data(), sizeof(positions),
                        cudaMemcpyHostToDevice), "copy shared global positions");
  cuda_check(cudaMemcpy(device_slots.get(), slots.data(), sizeof(slots),
                        cudaMemcpyHostToDevice), "copy shared global slots");
  zero_outputs();
  baseline.run_decode_ragged(
      device_packed.get(), device_norm.get(), device_norm.get(), baseline_queries.get(),
      baseline_keys.get(), baseline_values.get(), device_positions.get(), device_slots.get(),
      maximum_slots, maximum_slots, query_heads, kv_heads, dimension, true, capacity, 1e-6F,
      nullptr);
  candidate.run_decode_ragged(
      device_packed.get(), device_norm.get(), device_norm.get(), candidate_queries.get(),
      candidate_keys.get(), candidate_values.get(), device_positions.get(), device_slots.get(),
      maximum_slots, maximum_slots, query_heads, kv_heads, dimension, true, capacity, 1e-6F,
      nullptr);
  require_identical(ragged_cache_elements,
                    static_cast<std::size_t>(maximum_slots) * query_heads * dimension,
                    "ragged shared global KV roundtrip");
}

void test_prefill_layouts() {
  constexpr int tokens = 5;
  constexpr int heads = 2;
  constexpr int dimension = 2;
  std::array<float, tokens * heads * dimension> values{};
  for (std::size_t index = 0; index < values.size(); ++index) values[index] = static_cast<float>(index);
  const auto input = bf16<values.size()>(values);
  DeviceAllocation<__nv_bfloat16> device_input(input.size()), device_head_major(input.size()),
      device_round_trip(input.size());
  cuda_check(cudaMemcpy(device_input.get(), input.data(), sizeof(input), cudaMemcpyHostToDevice),
             "copy transpose input");
  gradiated::engine::token_to_head_bf16(device_input.get(), device_head_major.get(), tokens,
                                         heads, dimension, nullptr);
  gradiated::engine::head_to_token_bf16(device_head_major.get(), device_round_trip.get(), tokens,
                                         heads, dimension, nullptr);
  std::array<__nv_bfloat16, input.size()> round_trip{};
  cuda_check(cudaMemcpy(round_trip.data(), device_round_trip.get(), sizeof(round_trip),
                        cudaMemcpyDeviceToHost), "copy transpose round trip");
  for (std::size_t index = 0; index < input.size(); ++index) {
    near(__bfloat162float(round_trip[index]), values[index], 0.01F, "prefill transpose");
  }

  constexpr int capacity = 3;
  DeviceAllocation<__nv_bfloat16> device_cache(heads * capacity * dimension);
  cuda_check(cudaMemset(device_cache.get(), 0, heads * capacity * dimension * sizeof(__nv_bfloat16)),
             "clear ring cache");
  gradiated::engine::copy_kv_to_cache_bf16(device_head_major.get(), device_cache.get(), heads,
                                            tokens, dimension, capacity, 0, nullptr);
  std::array<__nv_bfloat16, heads * capacity * dimension> cache{};
  cuda_check(cudaMemcpy(cache.data(), device_cache.get(), sizeof(cache), cudaMemcpyDeviceToHost),
             "copy ring cache");
  for (int head = 0; head < heads; ++head) {
    for (int source_token = tokens - capacity; source_token < tokens; ++source_token) {
      const int slot = source_token % capacity;
      for (int component = 0; component < dimension; ++component) {
        const int source_index = (source_token * heads + head) * dimension + component;
        const int cache_index = (head * capacity + slot) * dimension + component;
        near(__bfloat162float(cache[cache_index]), values[source_index], 0.01F,
             "prefill KV ring copy");
      }
    }
  }
}

void test_batched_argmax() {
  constexpr int rows = 3;
  constexpr int elements = 513;
  std::vector<__nv_bfloat16> values(static_cast<std::size_t>(rows * elements),
                                    __float2bfloat16(-2.0F));
  const std::array<int, rows> expected{17, 0, 512};
  values[17] = __float2bfloat16(9.0F);
  values[elements + 0] = __float2bfloat16(4.0F);
  values[elements + 401] = __float2bfloat16(4.0F);  // Equal values select the lower index.
  values[2 * elements + 512] = __float2bfloat16(7.0F);
  DeviceAllocation<__nv_bfloat16> device_values(values.size());
  DeviceAllocation<int> device_output(rows);
  const std::size_t workspace_bytes =
      rows * gradiated::engine::argmax_bf16_workspace_bytes(elements);
  DeviceAllocation<unsigned char> workspace(workspace_bytes);
  cuda_check(cudaMemcpy(device_values.get(), values.data(), values.size() * sizeof(values[0]),
                        cudaMemcpyHostToDevice), "copy batched argmax values");
  gradiated::engine::argmax_bf16_rows(
      device_values.get(), rows, elements, device_output.get(), workspace.get(), nullptr);
  std::array<int, rows> output{};
  cuda_check(cudaMemcpy(output.data(), device_output.get(), sizeof(output), cudaMemcpyDeviceToHost),
             "copy batched argmax output");
  for (int row = 0; row < rows; ++row) {
    if (output[static_cast<std::size_t>(row)] != expected[static_cast<std::size_t>(row)]) {
      throw std::runtime_error("batched argmax mismatch at row " + std::to_string(row));
    }
  }
}

void test_int8_kv_quality_oracle() {
  constexpr int slots = 2;
  constexpr int heads = 2;
  constexpr int capacity = 5;
  constexpr int dimension = 512;
  constexpr int elements = slots * heads * capacity * dimension;
  std::vector<__nv_bfloat16> keys(elements), values(elements);
  for (int index = 0; index < elements; ++index) {
    keys[static_cast<std::size_t>(index)] = __float2bfloat16(
        static_cast<float>((index * 37) % 257 - 128) / 311.0F);
    values[static_cast<std::size_t>(index)] = __float2bfloat16(
        static_cast<float>((index * 53) % 509 - 254) / 73.0F);
  }
  const auto original_keys = keys;
  const auto original_values = values;
  DeviceAllocation<__nv_bfloat16> device_keys(elements), device_values(elements);
  cuda_check(cudaMemcpy(device_keys.get(), keys.data(), keys.size() * sizeof(keys[0]),
                        cudaMemcpyHostToDevice), "copy INT8 oracle keys");
  cuda_check(cudaMemcpy(device_values.get(), values.data(), values.size() * sizeof(values[0]),
                        cudaMemcpyHostToDevice), "copy INT8 oracle values");

  gradiated::engine::roundtrip_global_kv_int8_per_token_bf16(
      device_keys.get(), device_values.get(), heads, 2, dimension, capacity, 1, nullptr);
  const std::array<int, slots> positions{4, 0};
  const std::array<int, slots> slot_order{1, 0};
  DeviceAllocation<int> device_positions(slots), device_slots(slots);
  cuda_check(cudaMemcpy(device_positions.get(), positions.data(), sizeof(positions),
                        cudaMemcpyHostToDevice), "copy INT8 oracle positions");
  cuda_check(cudaMemcpy(device_slots.get(), slot_order.data(), sizeof(slot_order),
                        cudaMemcpyHostToDevice), "copy INT8 oracle slots");
  gradiated::engine::roundtrip_global_decode_kv_int8_per_token_bf16(
      device_keys.get(), device_values.get(), device_positions.get(), device_slots.get(),
      slots, slots, heads, dimension, capacity, nullptr);
  cuda_check(cudaDeviceSynchronize(), "synchronize INT8 KV oracle");
  cuda_check(cudaMemcpy(keys.data(), device_keys.get(), keys.size() * sizeof(keys[0]),
                        cudaMemcpyDeviceToHost), "copy INT8 oracle result keys");
  cuda_check(cudaMemcpy(values.data(), device_values.get(), values.size() * sizeof(values[0]),
                        cudaMemcpyDeviceToHost), "copy INT8 oracle result values");

  const auto verify_cache = [&](const std::vector<__nv_bfloat16>& original,
                                const std::vector<__nv_bfloat16>& actual,
                                const char* operation) {
    for (int slot = 0; slot < slots; ++slot) {
      for (int head = 0; head < heads; ++head) {
        for (int token = 0; token < capacity; ++token) {
          const bool selected = (slot == 0 && (token == 0 || token == 1 || token == 2)) ||
                                (slot == 1 && token == 4);
          const std::size_t row =
              (static_cast<std::size_t>(slot) * heads + head) * capacity + token;
          float maximum = 0.0F;
          if (selected) {
            for (int component = 0; component < dimension; ++component) {
              maximum = std::max(maximum, std::abs(__bfloat162float(
                  original[row * dimension + static_cast<std::size_t>(component)])));
            }
          }
          for (int component = 0; component < dimension; ++component) {
            const std::size_t index = row * dimension + static_cast<std::size_t>(component);
            float expected = __bfloat162float(original[index]);
            if (selected && maximum != 0.0F) {
              const int quantized = std::clamp(
                  static_cast<int>(std::nearbyint(expected * (127.0F / maximum))), -127, 127);
              expected = __bfloat162float(__float2bfloat16(
                  static_cast<float>(quantized) * (maximum / 127.0F)));
            }
            if (__bfloat162float(actual[index]) != expected) {
              throw std::runtime_error(std::string(operation) + " mismatch at row " +
                                       std::to_string(row) + ", component " +
                                       std::to_string(component));
            }
          }
        }
      }
    }
  };
  verify_cache(original_keys, keys, "INT8 key oracle");
  verify_cache(original_values, values, "INT8 value oracle");

  // Exercise the block-scaled and keys-only mapping independently. Slot 1 is a guard region.
  cuda_check(cudaMemcpy(device_keys.get(), original_keys.data(),
                        original_keys.size() * sizeof(original_keys[0]), cudaMemcpyHostToDevice),
             "reset block INT8 oracle keys");
  cuda_check(cudaMemcpy(device_values.get(), original_values.data(),
                        original_values.size() * sizeof(original_values[0]),
                        cudaMemcpyHostToDevice), "reset block INT8 oracle values");
  gradiated::engine::roundtrip_global_kv_int8_per_token_bf16(
      device_keys.get(), device_values.get(), heads, capacity, dimension, capacity, 0,
      nullptr, true, false, 128);
  cuda_check(cudaMemcpy(keys.data(), device_keys.get(), keys.size() * sizeof(keys[0]),
                        cudaMemcpyDeviceToHost), "copy block INT8 oracle keys");
  for (int slot = 0; slot < slots; ++slot) {
    for (int head = 0; head < heads; ++head) {
      for (int token = 0; token < capacity; ++token) {
        const std::size_t row =
            (static_cast<std::size_t>(slot) * heads + head) * capacity + token;
        for (int component_block = 0; component_block < dimension; component_block += 128) {
          float maximum = 0.0F;
          for (int component = component_block; component < component_block + 128; ++component) {
            maximum = std::max(maximum, std::abs(__bfloat162float(
                original_keys[row * dimension + static_cast<std::size_t>(component)])));
          }
          for (int component = component_block; component < component_block + 128; ++component) {
            const std::size_t index = row * dimension + static_cast<std::size_t>(component);
            float expected = __bfloat162float(original_keys[index]);
            if (slot == 0 && maximum != 0.0F) {
              const int quantized = std::clamp(static_cast<int>(std::nearbyint(
                  expected * (127.0F / maximum))), -127, 127);
              expected = __bfloat162float(__float2bfloat16(
                  static_cast<float>(quantized) * (maximum / 127.0F)));
            }
            if (__bfloat162float(keys[index]) != expected) {
              throw std::runtime_error("block INT8 key oracle mismatch");
            }
          }
        }
      }
    }
  }

  constexpr int materialized_rows = 3;
  DeviceAllocation<std::int8_t> materialized(materialized_rows * dimension);
  DeviceAllocation<float> materialized_scales(materialized_rows);
  gradiated::engine::quantize_bf16_rows_symmetric_int8(
      device_keys.get(), materialized.get(), materialized_scales.get(),
      materialized_rows, dimension, nullptr);
  std::array<float, materialized_rows> host_scales{};
  std::vector<std::int8_t> host_materialized(materialized_rows * dimension);
  cuda_check(cudaMemcpy(host_scales.data(), materialized_scales.get(), sizeof(host_scales),
                        cudaMemcpyDeviceToHost), "copy materialized INT8 scales");
  cuda_check(cudaMemcpy(host_materialized.data(), materialized.get(), host_materialized.size(),
                        cudaMemcpyDeviceToHost), "copy materialized INT8 values");
  for (int row = 0; row < materialized_rows; ++row) {
    float maximum = 0.0F;
    for (int column = 0; column < dimension; ++column) {
      maximum = std::max(maximum, std::abs(__bfloat162float(
          keys[static_cast<std::size_t>(row * dimension + column)])));
    }
    const float expected_scale = maximum == 0.0F ? 1.0F : maximum / 127.0F;
    if (host_scales[static_cast<std::size_t>(row)] != expected_scale) {
      throw std::runtime_error("materialized INT8 scale mismatch");
    }
    for (int column = 0; column < dimension; ++column) {
      const float value = __bfloat162float(
          keys[static_cast<std::size_t>(row * dimension + column)]);
      const int expected = std::clamp(
          static_cast<int>(std::nearbyint(value * (1.0F / expected_scale))), -127, 127);
      if (host_materialized[static_cast<std::size_t>(row * dimension + column)] != expected) {
        throw std::runtime_error("materialized INT8 value mismatch");
      }
    }
  }
}

template <int query_tokens>
void test_uniform_ring_attention() {
  constexpr int requests = 2;
  constexpr int query_heads = 2;
  constexpr int kv_heads = 1;
  constexpr int capacity = 16;
  constexpr int dimension = 16;
  constexpr int query_elements = requests * query_heads * query_tokens * dimension;
  constexpr int cache_elements = requests * kv_heads * capacity * dimension;
  constexpr int backup_elements = requests * kv_heads * query_tokens * dimension;
  std::vector<float> query_values(query_elements);
  std::vector<float> key_values(cache_elements);
  std::vector<float> value_values(cache_elements);
  std::vector<float> backup_key_values(backup_elements);
  std::vector<float> backup_value_values(backup_elements);
  const std::array<int, requests> positions{11, 13};
  for (int index = 0; index < query_elements; ++index) {
    query_values[static_cast<std::size_t>(index)] =
        static_cast<float>((index * 7) % 19 - 9) / 32.0F;
  }
  for (int index = 0; index < cache_elements; ++index) {
    key_values[static_cast<std::size_t>(index)] =
        static_cast<float>((index * 5) % 23 - 11) / 48.0F;
    value_values[static_cast<std::size_t>(index)] =
        static_cast<float>((index * 11) % 29 - 14) / 24.0F;
  }
  for (int index = 0; index < backup_elements; ++index) {
    backup_key_values[static_cast<std::size_t>(index)] =
        static_cast<float>((index * 13) % 17 - 8) / 40.0F;
    backup_value_values[static_cast<std::size_t>(index)] =
        static_cast<float>((index * 3) % 31 - 15) / 20.0F;
  }
  const auto to_bf16 = [](const std::vector<float>& values) {
    std::vector<__nv_bfloat16> result(values.size());
    for (std::size_t index = 0; index < values.size(); ++index) {
      result[index] = __float2bfloat16(values[index]);
    }
    return result;
  };
  const auto query = to_bf16(query_values);
  const auto keys = to_bf16(key_values);
  const auto values = to_bf16(value_values);
  const auto backup_keys = to_bf16(backup_key_values);
  const auto backup_values = to_bf16(backup_value_values);
  DeviceAllocation<__nv_bfloat16> device_query(query_elements), device_keys(cache_elements),
      device_values(cache_elements), device_backup_keys(backup_elements),
      device_backup_values(backup_elements), device_output(query_elements);
  DeviceAllocation<int> device_positions(requests);
  DeviceAllocation<void*> device_pointers(2 * requests);
  cuda_check(cudaMemcpy(device_query.get(), query.data(), query.size() * sizeof(query[0]),
                        cudaMemcpyHostToDevice), "copy ring queries");
  cuda_check(cudaMemcpy(device_keys.get(), keys.data(), keys.size() * sizeof(keys[0]),
                        cudaMemcpyHostToDevice), "copy ring keys");
  cuda_check(cudaMemcpy(device_values.get(), values.data(), values.size() * sizeof(values[0]),
                        cudaMemcpyHostToDevice), "copy ring values");
  cuda_check(cudaMemcpy(device_backup_keys.get(), backup_keys.data(),
                        backup_keys.size() * sizeof(backup_keys[0]), cudaMemcpyHostToDevice),
             "copy ring backup keys");
  cuda_check(cudaMemcpy(device_backup_values.get(), backup_values.data(),
                        backup_values.size() * sizeof(backup_values[0]), cudaMemcpyHostToDevice),
             "copy ring backup values");
  cuda_check(cudaMemcpy(device_positions.get(), positions.data(), sizeof(positions),
                        cudaMemcpyHostToDevice), "copy ring positions");
  std::array<void*, 2 * requests> pointers{};
  for (int request = 0; request < requests; ++request) {
    pointers[static_cast<std::size_t>(request)] =
        device_keys.get() + request * kv_heads * capacity * dimension;
    pointers[static_cast<std::size_t>(requests + request)] =
        device_values.get() + request * kv_heads * capacity * dimension;
  }
  cuda_check(cudaMemcpy(device_pointers.get(), pointers.data(), sizeof(pointers),
                        cudaMemcpyHostToDevice), "copy ring pointers");
  gradiated::engine::GemmCausalPrefillAttention attention(
      requests * capacity, query_heads, requests);
  attention.run_uniform_ring_batch(
      device_query.get(), reinterpret_cast<const void* const*>(device_pointers.get()),
      reinterpret_cast<const void* const*>(device_pointers.get() + requests),
      device_backup_keys.get(), device_backup_values.get(), device_output.get(),
      device_positions.get(), requests, query_heads, kv_heads, query_tokens,
      capacity, dimension, nullptr);
  cuda_check(cudaDeviceSynchronize(), "ring attention synchronization");
  std::vector<__nv_bfloat16> output(query_elements);
  cuda_check(cudaMemcpy(output.data(), device_output.get(), output.size() * sizeof(output[0]),
                        cudaMemcpyDeviceToHost), "copy ring attention output");

  for (int request = 0; request < requests; ++request) {
    for (int head = 0; head < query_heads; ++head) {
      for (int query_token = 0; query_token < query_tokens; ++query_token) {
        std::array<float, capacity> scores{};
        float maximum = -INFINITY;
        for (int physical = 0; physical < capacity; ++physical) {
          int backup_token = -1;
          for (int proposal = query_token + 1; proposal < query_tokens; ++proposal) {
            if ((positions[static_cast<std::size_t>(request)] + proposal) % capacity == physical) {
              backup_token = proposal;
            }
          }
          float score = 0.0F;
          for (int component = 0; component < dimension; ++component) {
            const int query_index =
                ((request * query_heads + head) * query_tokens + query_token) * dimension +
                component;
            const int key_index = backup_token >= 0
                ? ((request * kv_heads) * query_tokens + backup_token) * dimension + component
                : ((request * kv_heads) * capacity + physical) * dimension + component;
            score += __bfloat162float(query[static_cast<std::size_t>(query_index)]) *
                     __bfloat162float((backup_token >= 0 ? backup_keys : keys)
                                         [static_cast<std::size_t>(key_index)]);
          }
          scores[static_cast<std::size_t>(physical)] = score;
          maximum = std::max(maximum, score);
        }
        float denominator = 0.0F;
        for (float& score : scores) {
          score = std::exp(score - maximum);
          denominator += score;
        }
        for (int component = 0; component < dimension; ++component) {
          float expected = 0.0F;
          for (int physical = 0; physical < capacity; ++physical) {
            int backup_token = -1;
            for (int proposal = query_token + 1; proposal < query_tokens; ++proposal) {
              if ((positions[static_cast<std::size_t>(request)] + proposal) % capacity == physical) {
                backup_token = proposal;
              }
            }
            const int value_index = backup_token >= 0
                ? ((request * kv_heads) * query_tokens + backup_token) * dimension + component
                : ((request * kv_heads) * capacity + physical) * dimension + component;
            expected += scores[static_cast<std::size_t>(physical)] / denominator *
                        __bfloat162float((backup_token >= 0 ? backup_values : values)
                                            [static_cast<std::size_t>(value_index)]);
          }
          const int output_index =
              ((request * query_heads + head) * query_tokens + query_token) * dimension +
              component;
          near(__bfloat162float(output[static_cast<std::size_t>(output_index)]), expected,
               0.015F, "uniform ring attention");
        }
      }
    }
  }
}

}  // namespace

int main() {
  try {
    test_norm_add_and_scale();
    test_gelu_gate();
    test_linear();
    test_grouped_attention();
    test_shared_global_kv_roundtrip();
    test_prefill_layouts();
    test_int8_kv_quality_oracle();
    test_batched_argmax();
    test_uniform_ring_attention<4>();
    test_uniform_ring_attention<8>();
    std::cout << "all CUDA operation tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "CUDA operation test failed: " << error.what() << '\n';
    return 1;
  }
}
