#include <cuda/std/cstdint>
#include <cuda_fp8.h>

__global__ void cuda_toolchain_probe(cuda::std::uint32_t* output) {
  output[threadIdx.x] = threadIdx.x;
}
