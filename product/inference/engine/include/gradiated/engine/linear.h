#pragma once

#include <cstddef>
#include <memory>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

class Bf16Linear {
 public:
  explicit Bf16Linear(std::size_t workspace_bytes = 64ULL * 1024ULL * 1024ULL);
  ~Bf16Linear();
  Bf16Linear(const Bf16Linear&) = delete;
  Bf16Linear& operator=(const Bf16Linear&) = delete;

  void run(const void* input, const void* row_major_weight, void* output,
           int rows, int input_width, int output_width, cudaStream_t stream);

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
