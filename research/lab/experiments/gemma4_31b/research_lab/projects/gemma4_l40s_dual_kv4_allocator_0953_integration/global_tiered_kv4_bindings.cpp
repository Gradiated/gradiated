#include <torch/extension.h>

void tiered_store_recent(torch::Tensor input, torch::Tensor physical_locations,
                         torch::Tensor recent_locations,
                         torch::Tensor recent_cache);
void tiered_pack_old(torch::Tensor input, torch::Tensor physical_locations,
                     torch::Tensor old_locations, torch::Tensor old_cache);
void tiered_retire_recent(torch::Tensor physical_locations,
                           torch::Tensor old_locations,
                           torch::Tensor recent_locations,
                           torch::Tensor recent_cache,
                           torch::Tensor old_cache);
torch::Tensor tiered_paged_attention(
    torch::Tensor query, torch::Tensor recent_k, torch::Tensor recent_v,
    torch::Tensor old_k, torch::Tensor old_v,
    torch::Tensor recent_locations, torch::Tensor old_locations,
    torch::Tensor qo_indptr, torch::Tensor kv_indptr,
    torch::Tensor kv_indices, int64_t max_query_len, double softmax_scale);

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("store_recent", &tiered_store_recent);
  module.def("pack_old", &tiered_pack_old);
  module.def("retire_recent", &tiered_retire_recent);
  module.def("paged_attention", &tiered_paged_attention);
}
