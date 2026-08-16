#include <torch/extension.h>

void decode_local_kv4(torch::Tensor packed, torch::Tensor output);
void decode_global_tiered_kv4(
    torch::Tensor recent, torch::Tensor old,
    torch::Tensor recent_locations, torch::Tensor old_locations,
    torch::Tensor output);

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("decode_local", &decode_local_kv4);
  module.def("decode_global", &decode_global_tiered_kv4);
}
