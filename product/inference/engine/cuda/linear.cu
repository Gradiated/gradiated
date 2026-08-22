#include "gradiated/engine/linear.h"

#include <cublasLt.h>
#include <cuda_bf16.h>
#include <cuda_runtime.h>

#include <stdexcept>
#include <string>
#include <map>
#include <memory>
#include <tuple>

namespace gradiated::engine {
namespace {

void cuda_check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
}

void cublas_check(cublasStatus_t result, const char* operation) {
  if (result != CUBLAS_STATUS_SUCCESS) {
    throw std::runtime_error(std::string(operation) + " failed with status " + std::to_string(result));
  }
}

}  // namespace

struct Bf16Linear::Implementation {
  struct Plan {
    cublasLtMatmulDesc_t operation{};
    cublasLtMatrixLayout_t input_layout{};
    cublasLtMatrixLayout_t weight_layout{};
    cublasLtMatrixLayout_t output_layout{};
    cublasLtMatmulHeuristicResult_t heuristic{};

    ~Plan() {
      if (output_layout != nullptr) cublasLtMatrixLayoutDestroy(output_layout);
      if (weight_layout != nullptr) cublasLtMatrixLayoutDestroy(weight_layout);
      if (input_layout != nullptr) cublasLtMatrixLayoutDestroy(input_layout);
      if (operation != nullptr) cublasLtMatmulDescDestroy(operation);
    }
  };

  cublasLtHandle_t handle{};
  void* workspace{nullptr};
  std::size_t workspace_bytes;
  std::map<std::tuple<int, int, int>, std::unique_ptr<Plan>> plans;

  explicit Implementation(std::size_t bytes) : workspace_bytes(bytes) {
    cublas_check(cublasLtCreate(&handle), "cublasLtCreate");
    if (workspace_bytes != 0) cuda_check(cudaMalloc(&workspace, workspace_bytes), "allocate linear workspace");
  }
  ~Implementation() {
    plans.clear();
    if (workspace != nullptr) cudaFree(workspace);
    if (handle != nullptr) cublasLtDestroy(handle);
  }

  Plan& plan(int rows, int input_width, int output_width) {
    const auto key = std::make_tuple(rows, input_width, output_width);
    const auto existing = plans.find(key);
    if (existing != plans.end()) return *existing->second;
    auto result = std::make_unique<Plan>();
    cublas_check(cublasLtMatmulDescCreate(&result->operation, CUBLAS_COMPUTE_32F, CUDA_R_32F),
                 "create matmul descriptor");
    const cublasOperation_t transpose_weight = CUBLAS_OP_T;
    cublas_check(cublasLtMatmulDescSetAttribute(result->operation, CUBLASLT_MATMUL_DESC_TRANSB,
                                                 &transpose_weight, sizeof(transpose_weight)),
                 "set weight transpose");
    cublas_check(cublasLtMatrixLayoutCreate(&result->input_layout, CUDA_R_16BF, rows, input_width, input_width),
                 "create input layout");
    cublas_check(cublasLtMatrixLayoutCreate(&result->weight_layout, CUDA_R_16BF,
                                            output_width, input_width, input_width),
                 "create weight layout");
    cublas_check(cublasLtMatrixLayoutCreate(&result->output_layout, CUDA_R_16BF,
                                            rows, output_width, output_width),
                 "create output layout");
    const cublasLtOrder_t row_order = CUBLASLT_ORDER_ROW;
    cublas_check(cublasLtMatrixLayoutSetAttribute(result->input_layout, CUBLASLT_MATRIX_LAYOUT_ORDER,
                                                   &row_order, sizeof(row_order)), "set input order");
    cublas_check(cublasLtMatrixLayoutSetAttribute(result->weight_layout, CUBLASLT_MATRIX_LAYOUT_ORDER,
                                                   &row_order, sizeof(row_order)), "set weight order");
    cublas_check(cublasLtMatrixLayoutSetAttribute(result->output_layout, CUBLASLT_MATRIX_LAYOUT_ORDER,
                                                   &row_order, sizeof(row_order)), "set output order");
    cublasLtMatmulPreference_t preference{};
    cublas_check(cublasLtMatmulPreferenceCreate(&preference), "create matmul preference");
    cublas_check(cublasLtMatmulPreferenceSetAttribute(preference, CUBLASLT_MATMUL_PREF_MAX_WORKSPACE_BYTES,
                                                      &workspace_bytes, sizeof(workspace_bytes)),
                 "set matmul workspace");
    int returned = 0;
    const cublasStatus_t heuristic_status = cublasLtMatmulAlgoGetHeuristic(
        handle, result->operation, result->input_layout, result->weight_layout, result->output_layout,
        result->output_layout, preference, 1, &result->heuristic, &returned);
    cublasLtMatmulPreferenceDestroy(preference);
    cublas_check(heuristic_status, "select matmul algorithm");
    if (returned == 0) throw std::runtime_error("no cublasLt algorithm for linear shape");
    Plan& reference = *result;
    plans.emplace(key, std::move(result));
    return reference;
  }
};

Bf16Linear::Bf16Linear(std::size_t workspace_bytes)
    : implementation_(std::make_unique<Implementation>(workspace_bytes)) {}
Bf16Linear::~Bf16Linear() = default;

void Bf16Linear::run(const void* input, const void* row_major_weight, void* output,
                     int rows, int input_width, int output_width, cudaStream_t stream) {
  if (rows <= 0 || input_width <= 0 || output_width <= 0) throw std::runtime_error("invalid linear shape");
  auto& plan = implementation_->plan(rows, input_width, output_width);
  constexpr float alpha = 1.0F;
  constexpr float beta = 0.0F;
  cublas_check(cublasLtMatmul(implementation_->handle, plan.operation, &alpha, input, plan.input_layout,
                              row_major_weight, plan.weight_layout, &beta, output, plan.output_layout, output,
                              plan.output_layout, &plan.heuristic.algo, implementation_->workspace,
                              implementation_->workspace_bytes, stream),
               "run BF16 linear");
}

}  // namespace gradiated::engine
