#include <torch/extension.h>

#include <type_traits>

#include "cutlass/epilogue/fusion/sm90_callbacks_tma_warpspecialized.hpp"
#include "cutlass_extensions/gemm/fp8_gemm_sm90_dispatch.cuh"

namespace {

using ElementInput = cutlass::float_e4m3_t;
using ElementOutput = cutlass::bfloat16_t;
using EpilogueSchedule = cutlass::epilogue::TmaWarpSpecialized;

// The stock M=32 large-N path swaps A/B and covers 64 logical output
// channels per scheduler tile with Shape<64, 32, 256>. Keep the exact
// 32-row and K=256 reduction realization, but stream 128 output channels
// through each scheduler/epilogue tile.
using M32Tile = Shape<_128, _32, _256>;
using M32Cluster = Shape<_1, _1, _1>;
using M32Schedule = cutlass::gemm::KernelTmaWarpSpecializedFP8FastAccum;
using M32Gemm = cutlass_3x_gemm_sm90_fp8<
    ElementInput,
    ElementOutput,
    c3x::ScaledEpilogue,
    M32Tile,
    M32Cluster,
    M32Schedule,
    EpilogueSchedule,
    true>;

// The stock M=384 path uses Shape<128, 128, 128>, Cluster<2, 1, 1>.
// Retain the two-CTA M multicast cluster and K=128 reduction order while
// doubling only the logical output-channel tile.
using M384Tile = Shape<_128, _256, _128>;
using M384Cluster = Shape<_2, _1, _1>;
using M384Schedule =
    cutlass::gemm::KernelTmaWarpSpecializedPingpongFP8FastAccum;
using M384Gemm = cutlass_3x_gemm_sm90_fp8<
    ElementInput,
    ElementOutput,
    c3x::ScaledEpilogue,
    M384Tile,
    M384Cluster,
    M384Schedule,
    EpilogueSchedule>;

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
  if (mat_a.size(0) == 32) {
    cutlass_gemm_caller_sm90_fp8_scaled<M32Gemm>(
        output, mat_a, mat_b, scales_a, scales_b);
  } else {
    cutlass_gemm_caller_sm90_fp8_scaled<M384Gemm>(
        output, mat_a, mat_b, scales_a, scales_b);
  }
  return output;
}

pybind11::dict schedule_metadata() {
  pybind11::dict value;
  value["m32_tile_mnk"] = pybind11::make_tuple(128, 32, 256);
  value["m32_cluster_mnk"] = pybind11::make_tuple(1, 1, 1);
  value["m32_swap_ab"] = true;
  value["m32_shared_storage_bytes"] =
      sizeof(typename M32Gemm::GemmKernel::SharedStorage);
  value["m384_tile_mnk"] = pybind11::make_tuple(128, 256, 128);
  value["m384_cluster_mnk"] = pybind11::make_tuple(2, 1, 1);
  value["m384_swap_ab"] = false;
  value["m384_shared_storage_bytes"] =
      sizeof(typename M384Gemm::GemmKernel::SharedStorage);
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
