#include <torch/extension.h>

void local_kv4_outlier_pack(torch::Tensor input, torch::Tensor locations,
                            torch::Tensor cache);

torch::Tensor local_kv4_outlier_paged_attention(
    torch::Tensor query, torch::Tensor cache_k, torch::Tensor cache_v,
    torch::Tensor qo_indptr, torch::Tensor kv_indptr, torch::Tensor kv_indices,
    int64_t window, int64_t max_query_len, double softmax_scale,
    bool corrected);

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("pack", &local_kv4_outlier_pack);
  module.def("paged_attention", &local_kv4_outlier_paged_attention);
}
