# RMSNorm-to-FP8 QKV mainloop fusion

## Question

Can the exact Gemma 4 decode RMSNorm and per-row dynamic-E4M3 producer feed
the real layer-0 QKV GEMM through a Hopper-native producer/consumer handoff
without materializing the FP8 activation and scale through global memory?

This is distinct from the corrected standalone producer now awaiting an H200
component run. It asks whether the producer can be absorbed into, or
cooperatively handed directly to, the QKV GEMM rather than merely making the
producer faster.

## Why it matters

For the fixed c32 workload, the boundary is BF16 `[M, 5376]` input and norm
weight, exact stock RMSNorm reduction order, a BF16 normalization boundary,
per-row E4M3 `amax/448` quantization, and the unchanged
`5376 x 16384` real-QKV `fp8_scaled_mm` consumer. The standalone corrected
producer removes one launch and 688,128 logical BF16 bytes at M=32, but still
emits the E4M3 activation and FP32 scale for a separate GEMM. Eliminating that
interface could create a larger stackable gain; the fan-out across QKV N tiles
and the rowwise reduction may instead make cluster synchronization or
recomputation physically negative.

## Bound evidence and scope

- Target: NVIDIA H200 SM90a.
- Phase and shapes: decode `M=1,16,32`, hidden `K=5376`, QKV `N=16384`.
- Producer semantics: the exact 672-thread vec8/XOR RMSNorm tree, BF16
  boundary, per-row FP32 `amax/448`, E4M3 bytes, signed-zero behavior, and
  stock fallback outside the admitted shapes.
- Consumer: pinned SGLang v0.5.13 real layer-0 `fp8_scaled_mm`.
- Read-only starting evidence:
  `../gemma4_h200_current_norm_fp8_hotblock/MECHANISM_REPAIR_TERMINAL.json`,
  its corrected source/loader/adapter, and
  `inputs/gemma4-layer0-norm-qkv-component.safetensors`.
- Fixed campaign denominator: `0.625149101968745 s/request`; target:
  `0.500119281574996 s/request`.

Do not inspect the credential-blocked R5 project. Do not claim the shared
bench, invoke CUDA, reserve spend, or mutate provider lifecycle.

## Immediate result

Trace the exact pinned producer and GEMM consumer into the Hopper kernel
boundary. Compare at least:

1. a cluster or persistent producer that publishes exact FP8 fragments/scales
   to QKV consumer CTAs;
2. bounded producer recomputation per N-tile or tile group;
3. the materialized standalone corrected producer as the negative control.

For each, quantify CTA/cluster geometry, synchronization, registers, shared or
distributed shared memory, L2/HBM bytes, weight traffic, waves, and the
whole-request ceiling. Build a CPU/reference fragment-indexing and
activation/scale-byte oracle for any legal decomposition.

Publish `MECHANISM_TERMINAL.json` containing either:

- a concrete source-level SM90a candidate and exact-consumer GPU contract
  ready for one later component falsifier; or
- a typed analytical negative showing why every legal handoff loses to the
  standalone producer after fan-out, traffic, synchronization, or occupancy.

The result must identify the smallest target-H200 call that would change the
decision. Planning prose alone is not terminal evidence.
