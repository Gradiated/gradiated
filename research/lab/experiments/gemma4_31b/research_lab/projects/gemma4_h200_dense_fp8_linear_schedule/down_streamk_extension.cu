#include <torch/extension.h>

#include "cutlass/epilogue/fusion/sm90_callbacks_tma_warpspecialized.hpp"
#include "cutlass_extensions/gemm/fp8_gemm_sm90_dispatch.cuh"

torch::Tensor fp8_down_streamk(
    const torch::Tensor& mat_a,
    const torch::Tensor& mat_b,
    const torch::Tensor& scales_a,
    const torch::Tensor& scales_b) {
  TORCH_CHECK(mat_a.is_cuda() && mat_b.is_cuda(), "inputs must be CUDA tensors");
  TORCH_CHECK(mat_a.dim() == 2 && mat_b.dim() == 2, "inputs must be matrices");
  TORCH_CHECK(mat_a.size(0) > 128, "candidate is restricted to prefill M > 128");
  TORCH_CHECK(mat_a.size(1) == 21504, "candidate requires K=21504");
  TORCH_CHECK(mat_b.size(0) == 21504 && mat_b.size(1) == 5376, "candidate requires a 21504x5376 weight");
  TORCH_CHECK(mat_a.stride(1) == 1, "activation must be row major");
  TORCH_CHECK(mat_b.stride(0) == 1, "weight must be column major");
  TORCH_CHECK(mat_a.scalar_type() == torch::kFloat8_e4m3fn, "activation must be E4M3FN");
  TORCH_CHECK(mat_b.scalar_type() == torch::kFloat8_e4m3fn, "weight must be E4M3FN");
  TORCH_CHECK(scales_a.scalar_type() == torch::kFloat32 && scales_a.numel() == mat_a.size(0), "invalid row scales");
  TORCH_CHECK(scales_b.scalar_type() == torch::kFloat32 && scales_b.numel() == 5376, "invalid column scales");
  TORCH_CHECK(scales_a.is_contiguous() && scales_b.is_contiguous(), "scales must be contiguous");

  auto output = torch::empty({mat_a.size(0), 5376}, mat_a.options().dtype(torch::kBFloat16));
  using Config = sm90_fp8_config_down_streamk<cutlass::float_e4m3_t, cutlass::bfloat16_t>;
  cutlass_gemm_caller_sm90_fp8_scaled<typename Config::Cutlass3xGemm>(
      output, mat_a, mat_b, scales_a, scales_b);
  return output;
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("fp8_down_streamk", &fp8_down_streamk);
}
