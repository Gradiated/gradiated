#include "gradiated/engine/linear.h"

#include <cuda_bf16.h>
#include <cuda_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Shape {
  const char* name;
  int input_width;
  int output_width;
  int multiplicity;
};

struct Measurements {
  float gemm_milliseconds;
  float quantize_and_gemm_milliseconds;
};

void check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

class Allocation {
 public:
  explicit Allocation(std::uint64_t bytes) {
    check(cudaMalloc(&pointer_, static_cast<std::size_t>(bytes)), "allocate FP8 benchmark buffer");
    check(cudaMemset(pointer_, 0, static_cast<std::size_t>(bytes)), "clear FP8 benchmark buffer");
  }
  ~Allocation() { cudaFree(pointer_); }
  void* get() { return pointer_; }

 private:
  void* pointer_{nullptr};
};

template <typename Callable>
float measure(Callable&& callable) {
  for (int iteration = 0; iteration < 3; ++iteration) callable();
  check(cudaDeviceSynchronize(), "synchronize FP8 warmup");
  cudaEvent_t begin{}, end{};
  check(cudaEventCreate(&begin), "create FP8 begin event");
  check(cudaEventCreate(&end), "create FP8 end event");
  constexpr int iterations = 8;
  check(cudaEventRecord(begin), "record FP8 begin event");
  for (int iteration = 0; iteration < iterations; ++iteration) callable();
  check(cudaEventRecord(end), "record FP8 end event");
  check(cudaEventSynchronize(end), "synchronize FP8 benchmark");
  float milliseconds = 0.0F;
  check(cudaEventElapsedTime(&milliseconds, begin, end), "measure FP8 benchmark");
  cudaEventDestroy(end);
  cudaEventDestroy(begin);
  return milliseconds / iterations;
}

Measurements benchmark(gradiated::engine::Fp8Linear& linear, const Shape& shape, int rows) {
  const std::size_t input_elements = static_cast<std::size_t>(rows) * shape.input_width;
  const std::size_t weight_elements =
      static_cast<std::size_t>(shape.input_width) * shape.output_width;
  Allocation bf16_input(2ULL * input_elements);
  Allocation fp8_input(input_elements);
  Allocation bf16_weight(2ULL * weight_elements);
  Allocation fp8_weight(weight_elements);
  Allocation output(2ULL * static_cast<std::size_t>(rows) * shape.output_width);
  Allocation input_scale(sizeof(float));
  Allocation weight_scale(sizeof(float));
  gradiated::engine::quantize_bf16_to_fp8_e4m3(
      bf16_weight.get(), fp8_weight.get(), static_cast<float*>(weight_scale.get()),
      weight_elements, nullptr);
  gradiated::engine::quantize_bf16_to_fp8_e4m3(
      bf16_input.get(), fp8_input.get(), static_cast<float*>(input_scale.get()),
      input_elements, nullptr);
  check(cudaDeviceSynchronize(), "prepare FP8 benchmark operands");

  const auto gemm = [&] {
    linear.run(fp8_input.get(), static_cast<float*>(input_scale.get()), fp8_weight.get(),
               static_cast<float*>(weight_scale.get()), output.get(), rows, shape.input_width,
               shape.output_width, nullptr);
  };
  const float gemm_milliseconds = measure(gemm);
  const float combined_milliseconds = measure([&] {
    gradiated::engine::quantize_bf16_to_fp8_e4m3(
        bf16_input.get(), fp8_input.get(), static_cast<float*>(input_scale.get()),
        input_elements, nullptr);
    gemm();
  });
  return {gemm_milliseconds, combined_milliseconds};
}

void correctness_smoke_test() {
  constexpr int rows = 4;
  constexpr int input_width = 128;
  constexpr int output_width = 128;
  std::vector<__nv_bfloat16> input(rows * input_width);
  std::vector<__nv_bfloat16> weight(output_width * input_width);
  for (std::size_t index = 0; index < input.size(); ++index) {
    input[index] = __float2bfloat16(static_cast<float>(static_cast<int>(index % 11) - 5) / 8.0F);
  }
  for (std::size_t index = 0; index < weight.size(); ++index) {
    weight[index] = __float2bfloat16(static_cast<float>(static_cast<int>(index % 17) - 8) / 16.0F);
  }
  Allocation bf16_input(2ULL * input.size()), fp8_input(input.size());
  Allocation bf16_weight(2ULL * weight.size()), fp8_weight(weight.size());
  Allocation bf16_output(2ULL * rows * output_width), fp8_output(2ULL * rows * output_width);
  Allocation input_scale(sizeof(float)), weight_scale(sizeof(float));
  check(cudaMemcpy(bf16_input.get(), input.data(), 2ULL * input.size(), cudaMemcpyHostToDevice),
        "copy correctness input");
  check(cudaMemcpy(bf16_weight.get(), weight.data(), 2ULL * weight.size(), cudaMemcpyHostToDevice),
        "copy correctness weight");
  gradiated::engine::quantize_bf16_to_fp8_e4m3(
      bf16_input.get(), fp8_input.get(), static_cast<float*>(input_scale.get()), input.size(), nullptr);
  gradiated::engine::quantize_bf16_to_fp8_e4m3(
      bf16_weight.get(), fp8_weight.get(), static_cast<float*>(weight_scale.get()), weight.size(), nullptr);
  gradiated::engine::Bf16Linear bf16_linear;
  gradiated::engine::Fp8Linear fp8_linear;
  bf16_linear.run(bf16_input.get(), bf16_weight.get(), bf16_output.get(), rows, input_width,
                  output_width, nullptr);
  fp8_linear.run(fp8_input.get(), static_cast<float*>(input_scale.get()), fp8_weight.get(),
                 static_cast<float*>(weight_scale.get()), fp8_output.get(), rows, input_width,
                 output_width, nullptr);
  std::vector<__nv_bfloat16> reference(rows * output_width), candidate(rows * output_width);
  check(cudaMemcpy(reference.data(), bf16_output.get(), 2ULL * reference.size(), cudaMemcpyDeviceToHost),
        "copy BF16 correctness output");
  check(cudaMemcpy(candidate.data(), fp8_output.get(), 2ULL * candidate.size(), cudaMemcpyDeviceToHost),
        "copy FP8 correctness output");
  double squared_error = 0.0;
  double squared_reference = 0.0;
  double maximum_absolute_error = 0.0;
  for (std::size_t index = 0; index < reference.size(); ++index) {
    const double expected = __bfloat162float(reference[index]);
    const double actual = __bfloat162float(candidate[index]);
    const double error = actual - expected;
    squared_error += error * error;
    squared_reference += expected * expected;
    maximum_absolute_error = std::max(maximum_absolute_error, std::abs(error));
  }
  const double relative_l2 = std::sqrt(squared_error / squared_reference);
  if (!std::isfinite(relative_l2) || relative_l2 > 0.1) {
    throw std::runtime_error("FP8 linear correctness smoke test exceeded error bound");
  }
  std::cout << "correctness_relative_l2=" << relative_l2 << '\n'
            << "correctness_max_absolute_error=" << maximum_absolute_error << '\n';

  Allocation channel_fp8_input(input.size()), channel_fp8_weight(weight.size());
  Allocation channel_output(2ULL * rows * output_width);
  Allocation channel_input_scales(sizeof(float) * rows);
  Allocation channel_weight_scales(sizeof(float) * output_width);
  gradiated::engine::quantize_bf16_rows_to_fp8_e4m3(
      bf16_input.get(), channel_fp8_input.get(), static_cast<float*>(channel_input_scales.get()),
      rows, input_width, nullptr);
  gradiated::engine::quantize_bf16_rows_to_fp8_e4m3(
      bf16_weight.get(), channel_fp8_weight.get(), static_cast<float*>(channel_weight_scales.get()),
      output_width, input_width, nullptr);
  gradiated::engine::Fp8Linear channel_linear(gradiated::engine::Fp8Scaling::channel);
  channel_linear.run(channel_fp8_input.get(), static_cast<float*>(channel_input_scales.get()),
                     channel_fp8_weight.get(), static_cast<float*>(channel_weight_scales.get()),
                     channel_output.get(), rows, input_width, output_width, nullptr);
  check(cudaMemcpy(candidate.data(), channel_output.get(), 2ULL * candidate.size(),
                   cudaMemcpyDeviceToHost), "copy channel FP8 correctness output");
  squared_error = 0.0;
  maximum_absolute_error = 0.0;
  for (std::size_t index = 0; index < reference.size(); ++index) {
    const double expected = __bfloat162float(reference[index]);
    const double actual = __bfloat162float(candidate[index]);
    const double error = actual - expected;
    squared_error += error * error;
    maximum_absolute_error = std::max(maximum_absolute_error, std::abs(error));
  }
  const double channel_relative_l2 = std::sqrt(squared_error / squared_reference);
  if (!std::isfinite(channel_relative_l2) || channel_relative_l2 > 0.1) {
    throw std::runtime_error("channel FP8 linear correctness smoke test exceeded error bound");
  }
  std::cout << "channel_correctness_relative_l2=" << channel_relative_l2 << '\n'
            << "channel_correctness_max_absolute_error=" << maximum_absolute_error << '\n';

  Allocation block_fp8_input(input.size()), block_fp8_weight(weight.size());
  Allocation block_output(2ULL * rows * output_width);
  Allocation block_input_scales(sizeof(float) *
      gradiated::engine::fp8_activation_block_scale_elements(rows, input_width));
  Allocation block_weight_scales(sizeof(float) *
      gradiated::engine::fp8_weight_block_scale_elements(output_width, input_width));
  gradiated::engine::quantize_bf16_activation_to_fp8_block_128(
      bf16_input.get(), block_fp8_input.get(), static_cast<float*>(block_input_scales.get()),
      rows, input_width, nullptr);
  gradiated::engine::quantize_bf16_weight_to_fp8_block_128(
      bf16_weight.get(), block_fp8_weight.get(), static_cast<float*>(block_weight_scales.get()),
      output_width, input_width, nullptr);
  gradiated::engine::Fp8Linear block_linear(gradiated::engine::Fp8Scaling::block_128);
  block_linear.run(block_fp8_input.get(), static_cast<float*>(block_input_scales.get()),
                   block_fp8_weight.get(), static_cast<float*>(block_weight_scales.get()),
                   block_output.get(), rows, input_width, output_width, nullptr);
  check(cudaMemcpy(candidate.data(), block_output.get(), 2ULL * candidate.size(),
                   cudaMemcpyDeviceToHost), "copy block FP8 correctness output");
  squared_error = 0.0;
  maximum_absolute_error = 0.0;
  for (std::size_t index = 0; index < reference.size(); ++index) {
    const double expected = __bfloat162float(reference[index]);
    const double actual = __bfloat162float(candidate[index]);
    const double error = actual - expected;
    squared_error += error * error;
    maximum_absolute_error = std::max(maximum_absolute_error, std::abs(error));
  }
  const double block_relative_l2 = std::sqrt(squared_error / squared_reference);
  if (!std::isfinite(block_relative_l2) || block_relative_l2 > 0.1) {
    throw std::runtime_error("block FP8 linear correctness smoke test exceeded error bound");
  }
  std::cout << "block_correctness_relative_l2=" << block_relative_l2 << '\n'
            << "block_correctness_max_absolute_error=" << maximum_absolute_error << '\n';
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc > 2) {
      std::cerr << "usage: gradiated-engine-fp8-linear-benchmark [ROWS]\n";
      return 64;
    }
    correctness_smoke_test();
    const std::vector<Shape> shapes{
        {"sliding_qkv", 5376, 16384, 50},
        {"sliding_o", 8192, 5376, 50},
        {"global_qk", 5376, 18432, 10},
        {"global_o", 16384, 5376, 10},
        {"gate_up", 5376, 43008, 60},
        {"down", 21504, 5376, 60},
        {"lm_head", 5376, 262144, 1},
    };
    const std::vector<int> row_counts = argc == 2
        ? std::vector<int>{std::stoi(argv[1])}
        : std::vector<int>{1, 4, 8, 16, 32};
    gradiated::engine::Fp8Linear linear(gradiated::engine::Fp8Scaling::tensor);
    std::map<int, double> gemm_iteration_milliseconds;
    std::map<int, double> combined_iteration_milliseconds;
    std::cout << "component,rows,fp8_gemm_ms,quantize_and_gemm_ms,effective_weight_gb_s\n";
    for (const auto& shape : shapes) {
      for (const int rows : row_counts) {
        const Measurements measured = benchmark(linear, shape, rows);
        const double seconds = measured.gemm_milliseconds / 1000.0;
        const double weight_bytes = static_cast<double>(shape.input_width) * shape.output_width;
        gemm_iteration_milliseconds[rows] += measured.gemm_milliseconds * shape.multiplicity;
        combined_iteration_milliseconds[rows] +=
            measured.quantize_and_gemm_milliseconds * shape.multiplicity;
        std::cout << shape.name << ',' << rows << ',' << std::fixed << std::setprecision(4)
                  << measured.gemm_milliseconds << ',' << measured.quantize_and_gemm_milliseconds
                  << ',' << std::setprecision(2) << weight_bytes / seconds / 1e9 << '\n';
      }
    }
    std::cout << "summary_rows,fp8_linear_iteration_ms,quantized_linear_iteration_ms,"
                 "fp8_aggregate_tokens_s,quantized_aggregate_tokens_s\n";
    for (const int rows : row_counts) {
      const double gemm_ms = gemm_iteration_milliseconds.at(rows);
      const double combined_ms = combined_iteration_milliseconds.at(rows);
      std::cout << rows << ',' << std::fixed << std::setprecision(4) << gemm_ms << ','
                << combined_ms << ',' << rows * 1000.0 / gemm_ms << ','
                << rows * 1000.0 / combined_ms << '\n';
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FP8 linear benchmark failed: " << error.what() << '\n';
    return 1;
  }
}
