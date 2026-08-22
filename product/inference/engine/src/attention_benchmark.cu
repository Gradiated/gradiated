#include "gradiated/engine/attention.h"
#include "gradiated/engine/gemm_attention.h"

#include <cuda_runtime.h>

#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

class Allocation {
 public:
  explicit Allocation(std::uint64_t bytes) {
    check(cudaMalloc(&pointer_, static_cast<std::size_t>(bytes)), "cudaMalloc attention buffer");
    check(cudaMemset(pointer_, 0, static_cast<std::size_t>(bytes)), "cudaMemset attention buffer");
  }
  ~Allocation() { cudaFree(pointer_); }
  void* get() { return pointer_; }

 private:
  void* pointer_{nullptr};
};

float benchmark(int batch, int kv_heads, int query_group, int context, int dimension,
                bool fused) {
  const std::uint64_t query_bytes = 2ULL * batch * kv_heads * query_group * dimension;
  const std::uint64_t cache_bytes = 2ULL * batch * kv_heads * context * dimension;
  Allocation query(query_bytes), key(cache_bytes), value(cache_bytes), output(query_bytes);
  gradiated::engine::GemmGroupedDecodeAttention attention(batch, kv_heads, query_group, context);
  const auto run = [&] {
    if (fused) {
      gradiated::engine::grouped_decode_attention_bf16(
          query.get(), key.get(), value.get(), output.get(), batch, kv_heads,
          query_group, context, dimension, nullptr);
    } else {
      attention.run(query.get(), key.get(), value.get(), output.get(), batch, kv_heads,
                    query_group, context, dimension, nullptr);
    }
  };
  for (int iteration = 0; iteration < 2; ++iteration) {
    run();
  }
  check(cudaDeviceSynchronize(), "attention warmup");
  cudaEvent_t begin{}, end{};
  check(cudaEventCreate(&begin), "create begin event");
  check(cudaEventCreate(&end), "create end event");
  constexpr int iterations = 5;
  check(cudaEventRecord(begin), "record begin event");
  for (int iteration = 0; iteration < iterations; ++iteration) {
    run();
  }
  check(cudaEventRecord(end), "record end event");
  check(cudaEventSynchronize(end), "attention benchmark synchronization");
  float milliseconds = 0;
  check(cudaEventElapsedTime(&milliseconds, begin, end), "attention elapsed time");
  cudaEventDestroy(end);
  cudaEventDestroy(begin);
  return milliseconds / iterations;
}

}  // namespace

int main() {
  try {
    std::cout << "kind,batch,context,milliseconds,physical_kv_gb_s,naive_avoided_gb\n";
    for (const int batch : std::vector<int>{1, 2, 4, 8, 10, 16}) {
      const float sliding_ms = benchmark(batch, 16, 2, 1024, 256, false);
      const float sliding_fused_ms = benchmark(batch, 16, 2, 1024, 256, true);
      const double sliding_bytes = 4.0 * batch * 16 * 1024 * 256;
      std::cout << "sliding," << batch << ",1024," << std::fixed << std::setprecision(4)
                << sliding_ms << ',' << std::setprecision(2) << sliding_bytes / (sliding_ms / 1000.0) / 1e9
                << ',' << sliding_bytes / 1e9 << '\n';
      std::cout << "sliding_fused," << batch << ",1024," << std::fixed
                << std::setprecision(4) << sliding_fused_ms << ',' << std::setprecision(2)
                << sliding_bytes / (sliding_fused_ms / 1000.0) / 1e9 << ','
                << sliding_bytes / 1e9 << '\n';
      const float global_ms = benchmark(batch, 4, 8, 8192, 512, false);
      const float global_fused_ms = benchmark(batch, 4, 8, 8192, 512, true);
      const double global_bytes = 4.0 * batch * 4 * 8192 * 512;
      std::cout << "global," << batch << ",8192," << std::fixed << std::setprecision(4)
                << global_ms << ',' << std::setprecision(2) << global_bytes / (global_ms / 1000.0) / 1e9
                << ',' << 7.0 * global_bytes / 1e9 << '\n';
      std::cout << "global_fused," << batch << ",8192," << std::fixed
                << std::setprecision(4) << global_fused_ms << ',' << std::setprecision(2)
                << global_bytes / (global_fused_ms / 1000.0) / 1e9 << ','
                << 7.0 * global_bytes / 1e9 << '\n';
      const double total_ms = 50.0 * sliding_ms + 10.0 * global_ms;
      const double fused_total_ms = 50.0 * sliding_fused_ms + 10.0 * global_fused_ms;
      std::cout << "all_layers," << batch << ",8192," << std::fixed << std::setprecision(4)
                << total_ms << ",0,0\n";
      std::cout << "all_layers_fused," << batch << ",8192," << std::fixed
                << std::setprecision(4) << fused_total_ms << ",0,0\n";
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "attention benchmark failed: " << error.what() << '\n';
    return 1;
  }
}
