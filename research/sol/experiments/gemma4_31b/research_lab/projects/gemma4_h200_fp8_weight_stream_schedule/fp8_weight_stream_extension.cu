#include <torch/extension.h>

#include <type_traits>

// The SGLang scaled-MM epilogue aliases Sm90EVT/Sm90Compute from this pinned
// CUTLASS header.  It must be visible before the dispatcher is instantiated.
#include <cutlass/epilogue/fusion/sm90_callbacks_tma_warpspecialized.hpp>
#include <cutlass/gemm/kernel/tile_scheduler_params.h>
#include "cutlass_extensions/gemm/fp8_gemm_sm90_dispatch.cuh"

namespace {

using ElementInput = cutlass::float_e4m3_t;
using ElementOutput = cutlass::bfloat16_t;
// Gate/up is intentionally identical to the pinned stock dispatcher.  The
// intervention is only deterministic Stream-K decomposition for the long-K
// down projection.  All three aliases come from the content-bound SGLang
// v0.5.13 dispatcher, preserving its stock tensor-core tile and cluster/grid
// parallelism instead of inventing another output-channel-wide kernel.
using M32StockGemm =
    typename sm90_fp8_config_M32_largeN<ElementInput, ElementOutput, false>::
        Cutlass3xGemm;
using M384StockGemm =
    typename sm90_fp8_config_default<ElementInput, ElementOutput, false>::
        Cutlass3xGemm;

// The pinned image dispatcher exposes the stock persistent template but does
// not parameterize its scheduler. Reuse its exact mainloop/epilogue types and
// replace only GemmUniversal's scheduler tag with CUTLASS Stream-K.
using DownPersistentBase = cutlass_3x_gemm_sm90_fp8<
    ElementInput,
    ElementOutput,
    c3x::ScaledEpilogue,
    Shape<_128, _128, _128>,
    Shape<_2, _1, _1>,
    cutlass::gemm::KernelTmaWarpSpecializedCooperativeFP8FastAccum,
    cutlass::epilogue::TmaWarpSpecializedCooperative>;

struct DownStreamKGemm : public DownPersistentBase {
  using KernelType = enable_sm90_or_later<cutlass::gemm::kernel::GemmUniversal<
      cute::Shape<int, int, int, int>,
      typename DownPersistentBase::CollectiveMainloop,
      typename DownPersistentBase::CollectiveEpilogue,
      cutlass::gemm::StreamKScheduler>>;
  struct GemmKernel : public KernelType {};
};

void call_down_streamk(
    torch::Tensor& output,
    const torch::Tensor& mat_a,
    const torch::Tensor& mat_b,
    const torch::Tensor& scales_a,
    const torch::Tensor& scales_b) {
  using GemmKernel = typename DownStreamKGemm::GemmKernel;
  using StrideA = typename GemmKernel::StrideA;
  using StrideB = typename GemmKernel::StrideB;
  using StrideC = typename GemmKernel::StrideC;

  const int32_t m = mat_a.size(0);
  const int32_t n = mat_b.size(1);
  const int32_t k = mat_a.size(1);
  const auto problem_shape = cute::make_shape(m, n, k, 1);
  const auto a_stride =
      cutlass::make_cute_packed_stride(StrideA{}, cute::make_shape(m, k, 1));
  const auto b_stride =
      cutlass::make_cute_packed_stride(StrideB{}, cute::make_shape(n, k, 1));
  const auto c_stride =
      cutlass::make_cute_packed_stride(StrideC{}, cute::make_shape(m, n, 1));

  typename GemmKernel::MainloopArguments mainloop_args{
      static_cast<ElementInput*>(mat_a.data_ptr()),
      a_stride,
      static_cast<ElementInput*>(mat_b.data_ptr()),
      b_stride};
  auto* output_ptr = static_cast<ElementOutput*>(output.data_ptr());
  typename GemmKernel::EpilogueArguments epilogue_args{
      DownStreamKGemm::Epilogue::prepare_args(scales_a, scales_b),
      output_ptr,
      c_stride,
      output_ptr,
      c_stride};
  typename GemmKernel::TileSchedulerArguments scheduler;
  using SchedulerParams =
      cutlass::gemm::kernel::detail::PersistentTileSchedulerSm90StreamKParams;
  scheduler.decomposition_mode =
      SchedulerParams::DecompositionMode::StreamK;
  scheduler.reduction_mode = SchedulerParams::ReductionMode::Deterministic;
  cutlass_gemm_caller<GemmKernel>(
      mat_a.device(),
      problem_shape,
      mainloop_args,
      epilogue_args,
      scheduler);
}

void check_inputs(
    const torch::Tensor& mat_a,
    const torch::Tensor& mat_b,
    const torch::Tensor& scales_a,
    const torch::Tensor& scales_b) {
  TORCH_CHECK(mat_a.is_cuda() && mat_b.is_cuda(), "inputs must be CUDA tensors");
  TORCH_CHECK(
      scales_a.is_cuda() && scales_b.is_cuda(), "scales must be CUDA tensors");
  TORCH_CHECK(mat_a.dim() == 2 && mat_b.dim() == 2, "inputs must be matrices");
  TORCH_CHECK(
      mat_a.size(0) == 32 || mat_a.size(0) == 384,
      "candidate is restricted to exact M=32 or M=384");
  TORCH_CHECK(mat_a.size(1) == mat_b.size(0), "K mismatch");
  TORCH_CHECK(
      (mat_a.size(1) == 5376 && mat_b.size(1) == 43008) ||
          (mat_a.size(1) == 21504 && mat_b.size(1) == 5376),
      "candidate is restricted to Gemma 4 31B gate/up or down projection");
  TORCH_CHECK(mat_a.stride(1) == 1, "activation must be row major");
  TORCH_CHECK(mat_b.stride(0) == 1, "weight must be column major");
  TORCH_CHECK(
      mat_a.scalar_type() == torch::kFloat8_e4m3fn &&
          mat_b.scalar_type() == torch::kFloat8_e4m3fn,
      "inputs must be E4M3FN");
  TORCH_CHECK(
      scales_a.scalar_type() == torch::kFloat32 &&
          scales_a.numel() == mat_a.size(0),
      "invalid per-row activation scales");
  TORCH_CHECK(
      scales_b.scalar_type() == torch::kFloat32 &&
          scales_b.numel() == mat_b.size(1),
      "invalid per-output-channel weight scales");
  TORCH_CHECK(
      scales_a.is_contiguous() && scales_b.is_contiguous(),
      "scales must be contiguous");
}

torch::Tensor fp8_weight_stream(
    const torch::Tensor& mat_a,
    const torch::Tensor& mat_b,
    const torch::Tensor& scales_a,
    const torch::Tensor& scales_b) {
  check_inputs(mat_a, mat_b, scales_a, scales_b);
  auto output = torch::empty(
      {mat_a.size(0), mat_b.size(1)},
      mat_a.options().dtype(torch::kBFloat16));
  const bool is_down =
      mat_a.size(1) == 21504 && mat_b.size(1) == 5376;
  if (is_down) {
    call_down_streamk(output, mat_a, mat_b, scales_a, scales_b);
  } else if (mat_a.size(0) == 32) {
    cutlass_gemm_caller_sm90_fp8_scaled<M32StockGemm>(
        output, mat_a, mat_b, scales_a, scales_b);
  } else {
    cutlass_gemm_caller_sm90_fp8_scaled<M384StockGemm>(
        output, mat_a, mat_b, scales_a, scales_b);
  }
  return output;
}

pybind11::dict schedule_metadata() {
  pybind11::dict value;
  value["arm"] = "stock_gate_up__deterministic_streamk_down";
  value["gate_up_m32_tile_mnk"] = pybind11::make_tuple(64, 32, 256);
  value["gate_up_m32_cluster_mnk"] = pybind11::make_tuple(1, 1, 1);
  value["gate_up_m32_swap_ab"] = true;
  value["gate_up_m384_tile_mnk"] = pybind11::make_tuple(128, 128, 128);
  value["gate_up_m384_cluster_mnk"] = pybind11::make_tuple(2, 1, 1);
  value["gate_up_m384_swap_ab"] = false;
  value["down_tile_mnk"] = pybind11::make_tuple(128, 128, 128);
  value["down_cluster_mnk"] = pybind11::make_tuple(2, 1, 1);
  value["down_scheduler"] = "cutlass::gemm::StreamKScheduler";
  value["down_decomposition"] = "StreamK";
  value["down_reduction"] = "Deterministic";
  value["down_kernel"] =
      "KernelTmaWarpSpecializedCooperativeFP8FastAccum";
  value["m32_gate_shared_storage_bytes"] =
      sizeof(typename M32StockGemm::GemmKernel::SharedStorage);
  value["m384_gate_shared_storage_bytes"] =
      sizeof(typename M384StockGemm::GemmKernel::SharedStorage);
  value["down_shared_storage_bytes"] =
      sizeof(typename DownStreamKGemm::GemmKernel::SharedStorage);
  value["output_dtype"] = "bfloat16";
  value["accumulator_dtype"] = "float32";
  value["epilogue"] = "c3x::ScaledEpilogue";
  return value;
}

}  // namespace

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("fp8_weight_stream", &fp8_weight_stream);
  module.def("schedule_metadata", &schedule_metadata);
}
