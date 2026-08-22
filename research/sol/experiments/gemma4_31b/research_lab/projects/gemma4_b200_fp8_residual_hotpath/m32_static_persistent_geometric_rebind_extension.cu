#include <torch/extension.h>

#include <ATen/cuda/CUDAContext.h>

#include <array>
#include <string>
#include <type_traits>
#include <utility>

#include "cutlass/gemm/device/gemm_universal_adapter.h"
#include "cutlass/gemm/kernel/tile_scheduler.hpp"
#include "quantization/w8a8/cutlass/c3x/scaled_mm_sm100_fp8_dispatch.cuh"

namespace {

using ElementInput = cutlass::float_e4m3_t;
using ElementOutput = cutlass::bfloat16_t;
using StockDynamicGemm =
    typename vllm::sm100_fp8_config_M64_swap_ab<ElementInput, ElementOutput,
                                                false>::Cutlass3xGemm;

struct M32StaticPersistentGeometricRebindGemm : public StockDynamicGemm {
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

template <typename GemmKernel>
void run_with_bound_sm_count(
    int device_id, cute::Shape<int, int, int, int> problem_shape,
    typename GemmKernel::MainloopArguments mainloop_arguments,
    typename GemmKernel::EpilogueArguments epilogue_arguments) {
  auto const* properties = at::cuda::getDeviceProperties(device_id);
  int sm_count = properties->multiProcessorCount;
  TORCH_CHECK(sm_count >= 4, "static cluster requires at least four SMs");
  cutlass::KernelHardwareInfo hardware_info{device_id, sm_count, 0};
  typename GemmKernel::Arguments arguments{
      cutlass::gemm::GemmUniversalMode::kGemm,
      problem_shape,
      mainloop_arguments,
      epilogue_arguments,
      hardware_info,
      {}};

  using GemmOperator =
      cutlass::gemm::device::GemmUniversalAdapter<GemmKernel>;
  GemmOperator gemm_operator;
  CUTLASS_CHECK(gemm_operator.can_implement(arguments));
  dim3 grid = GemmOperator::get_grid_shape(arguments);
  TORCH_CHECK(grid.x > 0 && grid.y > 0 && grid.z > 0,
              "static-persistent grid must be nonzero");
  TORCH_CHECK(grid.x % 4 == 0,
              "grid x must be divisible by the 4x1x1 cluster");
  TORCH_CHECK(
      GemmKernel::SharedStorageSize <= properties->sharedMemPerBlockOptin,
      "kernel shared storage exceeds the device opt-in block limit");

  size_t workspace_size = gemm_operator.get_workspace_size(arguments);
  auto workspace = torch::empty(
      workspace_size,
      torch::TensorOptions().dtype(torch::kUInt8).device(
          torch::Device(torch::kCUDA, device_id)));
  auto stream = at::cuda::getCurrentCUDAStream(device_id);
  CUTLASS_CHECK(
      gemm_operator.run(arguments, workspace.data_ptr(), stream));
}

torch::Tensor m32_static_persistent(
    const torch::Tensor& activation,
    const torch::Tensor& weight,
    const torch::Tensor& activation_scale,
    const torch::Tensor& weight_scale) {
  check_inputs(activation, weight, activation_scale, weight_scale);
  using GemmKernel =
      typename M32StaticPersistentGeometricRebindGemm::GemmKernel;
  using StrideA = typename GemmKernel::StrideA;
  using StrideB = typename GemmKernel::StrideB;
  using StrideC = typename GemmKernel::StrideC;

  int32_t m = activation.size(0);
  int32_t n = weight.size(1);
  int32_t k = activation.size(1);
  auto problem_shape = cute::make_shape(n, m, k, 1);
  StrideA activation_stride =
      cutlass::make_cute_packed_stride(StrideA{},
                                       cute::make_shape(m, k, 1));
  StrideB weight_stride =
      cutlass::make_cute_packed_stride(StrideB{},
                                       cute::make_shape(n, k, 1));
  StrideC output_stride =
      cutlass::make_cute_packed_stride(StrideC{},
                                       cute::make_shape(n, m, 1));

  auto output = torch::empty(
      {m, n}, activation.options().dtype(torch::kBFloat16));
  typename GemmKernel::MainloopArguments mainloop_arguments{
      static_cast<ElementInput*>(weight.data_ptr()), weight_stride,
      static_cast<ElementInput*>(activation.data_ptr()), activation_stride};
  typename GemmKernel::EpilogueArguments epilogue_arguments{
      M32StaticPersistentGeometricRebindGemm::Epilogue::prepare_args(
          weight_scale, activation_scale),
      static_cast<ElementOutput*>(output.data_ptr()), output_stride,
      static_cast<ElementOutput*>(output.data_ptr()), output_stride};
  run_with_bound_sm_count<GemmKernel>(
      activation.get_device(), problem_shape, mainloop_arguments,
      epilogue_arguments);
  return output;
}

pybind11::dict schedule_metadata() {
  using GemmKernel =
      typename M32StaticPersistentGeometricRebindGemm::GemmKernel;
  pybind11::dict value;
  value["candidate_symbol"] =
      "M32StaticPersistentGeometricRebindGemm::GemmKernel";
  value["scheduler_tag"] = "cutlass::gemm::StaticPersistentScheduler";
  value["launch_correction"] = "runtime_sm_count_binding";
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
      std::is_same_v<
          typename M32StaticPersistentGeometricRebindGemm::CollectiveMainloop,
          typename StockDynamicGemm::CollectiveMainloop>;
  value["epilogue_identical_to_stock"] =
      std::is_same_v<
          typename M32StaticPersistentGeometricRebindGemm::CollectiveEpilogue,
          typename StockDynamicGemm::CollectiveEpilogue>;
  value["shared_storage_bytes"] = GemmKernel::SharedStorageSize;
  value["cluster_size"] = 4;
  return value;
}

}  // namespace

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("m32_static_persistent", &m32_static_persistent);
  module.def("schedule_metadata", &schedule_metadata);
}
