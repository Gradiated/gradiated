#include <torch/extension.h>

#include <array>
#include <string>
#include <type_traits>
#include <utility>

#include "cutlass/gemm/kernel/tile_scheduler.hpp"
#include "quantization/w8a8/cutlass/c3x/scaled_mm_sm100_fp8_dispatch.cuh"

namespace {

using ElementInput = cutlass::float_e4m3_t;
using ElementOutput = cutlass::bfloat16_t;
using StockDynamicGemm =
    typename vllm::sm100_fp8_config_M64_swap_ab<ElementInput, ElementOutput,
                                                false>::Cutlass3xGemm;

struct M32StaticPersistentGemm : public StockDynamicGemm {
  using GemmKernel = vllm::enable_sm100f_only<
      cutlass::gemm::kernel::GemmUniversal<
          cute::Shape<int, int, int, int>,
          typename StockDynamicGemm::CollectiveMainloop,
          typename StockDynamicGemm::CollectiveEpilogue,
          cutlass::gemm::StaticPersistentScheduler>>;
};

constexpr std::array<std::pair<int64_t, int64_t>, 6> kGemmaShapes{{
    {5376, 16384},
    {8192, 5376},
    {5376, 20480},
    {16384, 5376},
    {5376, 43008},
    {21504, 5376},
}};

void check_inputs(const torch::Tensor& activation,
                  const torch::Tensor& weight,
                  const torch::Tensor& activation_scale,
                  const torch::Tensor& weight_scale) {
  TORCH_CHECK(activation.is_cuda() && weight.is_cuda(),
              "activation and weight must be CUDA tensors");
  TORCH_CHECK(activation_scale.is_cuda() && weight_scale.is_cuda(),
              "scales must be CUDA tensors");
  TORCH_CHECK(activation.dim() == 2 && weight.dim() == 2,
              "activation and weight must be matrices");
  TORCH_CHECK(activation.size(0) == 32, "candidate is restricted to M=32");
  TORCH_CHECK(activation.size(1) == weight.size(0), "K mismatch");
  bool exact_shape = false;
  for (const auto& [k, n] : kGemmaShapes) {
    exact_shape |= activation.size(1) == k && weight.size(1) == n;
  }
  TORCH_CHECK(exact_shape,
              "candidate is restricted to the six Gemma 4 31B families");
  TORCH_CHECK(activation.scalar_type() == torch::kFloat8_e4m3fn &&
                  weight.scalar_type() == torch::kFloat8_e4m3fn,
              "operands must be E4M3FN");
  TORCH_CHECK(activation.stride(1) == 1 && activation.storage_offset() == 0,
              "activation must be zero-offset row-major");
  TORCH_CHECK(weight.stride(0) == 1 && weight.storage_offset() == 0,
              "weight must be zero-offset column-major KxN");
  TORCH_CHECK(activation_scale.scalar_type() == torch::kFloat32 &&
                  activation_scale.numel() == activation.size(0) &&
                  activation_scale.is_contiguous(),
              "activation scale must be contiguous per-token FP32");
  TORCH_CHECK(weight_scale.scalar_type() == torch::kFloat32 &&
                  weight_scale.numel() == 1 &&
                  weight_scale.is_contiguous(),
              "weight scale must be contiguous per-tensor FP32");
}

torch::Tensor m32_static_persistent(const torch::Tensor& activation,
                                    const torch::Tensor& weight,
                                    const torch::Tensor& activation_scale,
                                    const torch::Tensor& weight_scale) {
  check_inputs(activation, weight, activation_scale, weight_scale);
  auto output = torch::empty(
      {activation.size(0), weight.size(1)},
      activation.options().dtype(torch::kBFloat16));
  vllm::cutlass_gemm_caller_sm100_fp8<M32StaticPersistentGemm>(
      output, activation, weight, weight_scale, activation_scale);
  return output;
}

pybind11::dict schedule_metadata() {
  pybind11::dict value;
  value["candidate_symbol"] =
      "M32StaticPersistentGemm::GemmKernel";
  value["scheduler_tag"] = "cutlass::gemm::StaticPersistentScheduler";
  value["stock_scheduler_tag"] = "void";
  value["stock_scheduler_resolves_to"] =
      "cutlass::gemm::PersistentTileSchedulerSm100";
  value["tile_mnk"] = pybind11::make_tuple(128, 64, 256);
  value["cluster_mnk"] = pybind11::make_tuple(4, 1, 1);
  value["swap_ab"] = true;
  value["output_dtype"] = "bfloat16";
  value["accumulator_dtype"] = "float32";
  value["activation_scale"] = "dynamic_per_token";
  value["weight_scale"] = "dynamic_online_per_tensor";
  value["mainloop_identical_to_stock"] =
      std::is_same_v<typename M32StaticPersistentGemm::CollectiveMainloop,
                     typename StockDynamicGemm::CollectiveMainloop>;
  value["epilogue_identical_to_stock"] =
      std::is_same_v<typename M32StaticPersistentGemm::CollectiveEpilogue,
                     typename StockDynamicGemm::CollectiveEpilogue>;
  value["shared_storage_bytes"] =
      sizeof(typename M32StaticPersistentGemm::GemmKernel::SharedStorage);
  return value;
}

}  // namespace

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("m32_static_persistent", &m32_static_persistent);
  module.def("schedule_metadata", &schedule_metadata);
}
