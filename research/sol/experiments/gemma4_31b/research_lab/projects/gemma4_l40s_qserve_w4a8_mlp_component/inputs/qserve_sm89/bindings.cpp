#include <torch/extension.h>

#include "gemm_cuda.h"

void quantize_bf16_s8_cuda(
    torch::Tensor input,
    torch::Tensor output,
    torch::Tensor scales);
void gelu_mul_quant_s8_cuda(
    torch::Tensor input,
    torch::Tensor output,
    torch::Tensor scales);

namespace {

void require_cuda_contiguous(const torch::Tensor &tensor, const char *name) {
  TORCH_CHECK(tensor.is_cuda(), name, " must be CUDA");
  TORCH_CHECK(tensor.is_contiguous(), name, " must be contiguous");
}

void qserve_w4a8_gemm(
    torch::Tensor input,
    torch::Tensor qweight,
    torch::Tensor zeros,
    torch::Tensor scales_i8,
    torch::Tensor weight_scales,
    torch::Tensor activation_scales,
    torch::Tensor output) {
  require_cuda_contiguous(input, "input");
  require_cuda_contiguous(qweight, "qweight");
  require_cuda_contiguous(zeros, "zeros");
  require_cuda_contiguous(scales_i8, "scales_i8");
  require_cuda_contiguous(weight_scales, "weight_scales");
  require_cuda_contiguous(activation_scales, "activation_scales");
  require_cuda_contiguous(output, "output");
  TORCH_CHECK(input.scalar_type() == torch::kInt8, "input must be int8");
  TORCH_CHECK(qweight.scalar_type() == torch::kInt8, "qweight must be int8");
  TORCH_CHECK(zeros.scalar_type() == torch::kInt8, "zeros must be int8");
  TORCH_CHECK(scales_i8.scalar_type() == torch::kInt8, "scales_i8 must be int8");
  TORCH_CHECK(weight_scales.scalar_type() == torch::kFloat16, "weight_scales must be fp16");
  TORCH_CHECK(activation_scales.scalar_type() == torch::kFloat16, "activation_scales must be fp16");
  TORCH_CHECK(output.scalar_type() == torch::kFloat16, "output must be fp16");
  TORCH_CHECK(input.dim() == 2 && qweight.dim() == 2, "input and qweight must be rank 2");
  TORCH_CHECK(input.size(0) > 0 && input.size(0) <= 32, "M must be in [1,32]");
  TORCH_CHECK(input.size(1) % 128 == 0, "K must be divisible by 128");
  TORCH_CHECK(qweight.size(1) * 2 == input.size(1), "packed K mismatch");
  TORCH_CHECK(qweight.size(0) % 64 == 0, "N must be divisible by 64");
  TORCH_CHECK(zeros.sizes() == scales_i8.sizes(), "zero/scale layout mismatch");
  TORCH_CHECK(zeros.size(0) == input.size(1) / 128, "group count mismatch");
  TORCH_CHECK(zeros.size(1) == qweight.size(0), "scale N mismatch");
  TORCH_CHECK(weight_scales.numel() == qweight.size(0), "weight scale mismatch");
  TORCH_CHECK(activation_scales.numel() == input.size(0), "activation scale mismatch");
  TORCH_CHECK(
      output.size(0) == input.size(0) && output.size(1) == qweight.size(0),
      "output shape mismatch");
  gemm_forward_cuda(
      input,
      qweight,
      zeros,
      scales_i8,
      weight_scales,
      activation_scales,
      output);
}

}  // namespace

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("w4a8_gemm", &qserve_w4a8_gemm);
  module.def("quantize_bf16_s8", &quantize_bf16_s8_cuda);
  module.def("gelu_mul_quant_s8", &gelu_mul_quant_s8_cuda);
}
