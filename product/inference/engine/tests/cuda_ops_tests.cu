#include "gradiated/engine/cuda_ops.h"
#include "gradiated/engine/attention.h"
#include "gradiated/engine/linear.h"
#include "gradiated/engine/gemm_attention.h"

#include <cuda_bf16.h>
#include <cuda_runtime.h>

#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

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
      device_output(width), device_scalar(1);
  cuda_check(cudaMemcpy(device_input.get(), input.data(), sizeof(input), cudaMemcpyHostToDevice), "copy input");
  cuda_check(cudaMemcpy(device_weight.get(), weight.data(), sizeof(weight), cudaMemcpyHostToDevice), "copy weight");
  cuda_check(cudaMemcpy(device_residual.get(), residual.data(), sizeof(residual), cudaMemcpyHostToDevice),
             "copy residual");
  cuda_check(cudaMemcpy(device_scalar.get(), scalar.data(), sizeof(scalar), cudaMemcpyHostToDevice), "copy scalar");
  gradiated::engine::rms_norm_add_bf16(device_input.get(), device_weight.get(), device_residual.get(),
                                       device_output.get(), 1, width, 1e-6F, nullptr);
  gradiated::engine::scale_bf16(device_output.get(), device_scalar.get(), width, nullptr);
  cuda_check(cudaDeviceSynchronize(), "norm synchronization");
  std::array<__nv_bfloat16, width> output{};
  cuda_check(cudaMemcpy(output.data(), device_output.get(), sizeof(output), cudaMemcpyDeviceToHost), "copy output");
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

}  // namespace

int main() {
  try {
    test_norm_add_and_scale();
    test_gelu_gate();
    test_linear();
    test_grouped_attention();
    std::cout << "all CUDA operation tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "CUDA operation test failed: " << error.what() << '\n';
    return 1;
  }
}
