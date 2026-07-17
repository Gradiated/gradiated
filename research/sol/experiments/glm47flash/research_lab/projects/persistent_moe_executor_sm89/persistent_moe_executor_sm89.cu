#include <cuda_bf16.h>
#include <cuda_runtime.h>

constexpr int kHidden = 2048;
constexpr int kIntermediate = 1536;
constexpr int kExperts = 64;
constexpr int kTopK = 4;
constexpr int kGroupSize = 32;
constexpr int kThreads = 256;

struct PersistentMoEArgs {
  const __nv_bfloat16* activations;
  const int* expert_ids;
  const __nv_bfloat16* route_weights;
  const unsigned int* gate_packed;
  const unsigned int* up_packed;
  const unsigned int* down_packed;
  const __nv_bfloat16* gate_scales;
  const __nv_bfloat16* up_scales;
  const __nv_bfloat16* down_scales;
  __nv_bfloat16* routed_output;
  int assignments;
  int* next_assignment;
};

__device__ inline float dequant_w4(const unsigned int* packed,
                                   const __nv_bfloat16* scales, int row,
                                   int column, int columns) {
  const int packed_column = column >> 3;
  const unsigned int word = packed[row * (columns / 8) + packed_column];
  const int nibble = (word >> ((column & 7) * 4)) & 15;
  const int signed_nibble = nibble >= 8 ? nibble - 16 : nibble;
  return static_cast<float>(signed_nibble) *
      __bfloat162float(scales[row * (columns / kGroupSize) + column / kGroupSize]);
}

// One resident worker repeatedly claims a routed assignment.  The caller has
// already written the shared-expert contribution into routed_output; this
// kernel only atomically adds the exact route-weighted routed contribution.
// It deliberately has no fallback path: unsupported shape/packing is a launch
// error in the host integration, not a semantic substitution.
extern "C" __global__ void persistent_moe_w4(PersistentMoEArgs args) {
  for (;;) {
    const int assignment = atomicAdd(args.next_assignment, 1);
    if (assignment >= args.assignments) return;
    const int token = assignment / kTopK;
    const int slot = assignment % kTopK;
    const int expert = args.expert_ids[assignment];
    if (expert < 0 || expert >= kExperts) asm("trap;");
    const float route = __bfloat162float(args.route_weights[assignment]);
    const unsigned int* gate = args.gate_packed + expert * kIntermediate * (kHidden / 8);
    const unsigned int* up = args.up_packed + expert * kIntermediate * (kHidden / 8);
    const unsigned int* down = args.down_packed + expert * kHidden * (kIntermediate / 8);
    const __nv_bfloat16* gate_scale = args.gate_scales + expert * kIntermediate * (kHidden / kGroupSize);
    const __nv_bfloat16* up_scale = args.up_scales + expert * kIntermediate * (kHidden / kGroupSize);
    const __nv_bfloat16* down_scale = args.down_scales + expert * kHidden * (kIntermediate / kGroupSize);
    const __nv_bfloat16* x = args.activations + token * kHidden;
    for (int output = threadIdx.x; output < kHidden; output += blockDim.x) {
      float total = 0.0f;
      for (int middle = 0; middle < kIntermediate; ++middle) {
        float gated = 0.0f;
        float upped = 0.0f;
        for (int input = 0; input < kHidden; ++input) {
          const float value = __bfloat162float(x[input]);
          gated += dequant_w4(gate, gate_scale, middle, input, kHidden) * value;
          upped += dequant_w4(up, up_scale, middle, input, kHidden) * value;
        }
        const float silu = gated / (1.0f + __expf(-gated));
        total += dequant_w4(down, down_scale, output, middle, kIntermediate) * silu * upped;
      }
      atomicAdd(reinterpret_cast<float*>(args.routed_output + token * kHidden + output), route * total);
    }
  }
}

extern "C" cudaError_t launch_persistent_moe_w4(const PersistentMoEArgs& args,
                                                  cudaStream_t stream) {
  if (args.assignments <= 0 || args.assignments > 128 || args.assignments % kTopK != 0) {
    return cudaErrorInvalidValue;
  }
  persistent_moe_w4<<<142, kThreads, 0, stream>>>(args);
  return cudaGetLastError();
}
