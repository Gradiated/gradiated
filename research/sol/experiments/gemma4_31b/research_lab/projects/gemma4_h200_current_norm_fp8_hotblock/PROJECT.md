# Gemma 4 current-runtime norm/FP8 hot-block

## Question

In the exact current SGLang Gemma 4 dynamic-FP8 path, can one production
decode hot block fuse the residual/RMSNorm producer with the adjacent
activation quantization boundary strongly enough to remove a launch and a
full hidden-state memory round trip without changing the model, workload, or
existing FP8 semantics?

## Why this matters

The campaign must improve the fixed qualified H200 denominator
`0.625149101968745 s/request` toward `0.500119281574996 s/request`. The live
streamed-global-KV endpoint changes attention memory scheduling; this project
is independent and targets the recurring non-attention linear producer path
across all text layers. A small reproducible gain is stackable.

## Authoritative identities and evidence

- Mechanically read checkpoint, runtime image, exact workload, denominator,
  and target identities from
  `../gemma4_streaming_global_kv_memory_schedule/DIRECTOR_STREAMING_GLOBAL_KV_FRESH_H200_V10_SAME_CLAIM_REPLACEMENT_20260729T1410Z.json`.
- Use the exact checkpoint configuration referenced by that binding to derive
  hidden, intermediate, Q/K/V, batch, and token shapes. Do not hand-copy
  geometry from this brief.
- Use the current pinned SGLang source corresponding to the bound image,
  plus only the narrow prior residual/profile evidence needed from
  `../gemma4_h200_v0513_fp8_qkv_residual_profile/`.
- The retained compatible serving configuration includes dynamic chunking
  with chunk size 2048; preserve it in later endpoint accounting.

## Scope and immediate evidence path

Work for at most 50 wall-clock minutes with zero GPU, zero CUDA execution,
zero provider calls, and at most 2 GiB of new local storage.

Trace one exact recurring production path from residual and RMSNorm through
the first dynamic-FP8 quantized consumer. Identify the pinned symbols,
layouts, scales, dtype conversions, stream/graph boundary, and whether an
intermediate is reused elsewhere. Then produce one of:

1. a source-complete exact-shape Triton/CUDA or runtime adapter plus a CPU
   oracle and a target-H200 runner comparing the strongest current
   producer/consumer boundary with the fused candidate; or
2. a typed falsification showing that the intermediate cannot be eliminated,
   the consumer contract prevents fusion, or the maximum launch/byte bound is
   uncompetitive.

The candidate must predict one physical discriminator: eliminated kernel
launches, bytes removed at the HBM boundary, or a specific occupancy/register
tradeoff. Correctness should use the existing FP8 numerical contract and an
A/A-derived finite tolerance; bitwise equality is not required unless the
pinned runtime requires it.

Do not broaden into a generic fusion survey, flag sweep, static design
document, attention work, checkpoint change, weight pruning, quality replay,
or provider preparation. Do not touch the claimed H200. A later director
decides whether a source-complete survivor merits target-hardware execution.

## Portfolio consequence

A positive, source-complete result becomes a cheap H200 exact-consumer
component candidate and can stack with streamed global KV. A negative result
closes only this exact residual/RMSNorm-to-dynamic-FP8 boundary and redirects
the deep slot to another non-attention critical-path mechanism.

## 2026-07-30 exact-order causal reopen

The first target-H200 run rejected candidate `c24c5a90...`: M=1 was exact,
but M=16 and M=32 differed from the pinned stock producer even though the
producer-plus-real-QKV-consumer median was lower. This is measured evidence
for the physical mechanism and against that implementation, not authority to
reuse its timing or relax exactness.

Follow
`DIRECTOR_NORM_FP8_EXACT_ORDER_REOPEN_20260730T0651Z.json`. Trace and
reproduce the exact pinned RMSNorm reduction, rounding, amax, scale, and E4M3
conversion order in a deterministic zero-GPU oracle before emitting any
corrected source. The only promotion outcome is exact activation and scale
bytes on the full prescribed corpus plus a source-complete physical
falsifier. Otherwise publish the typed exactness negative. The R5 project and
its H200 are outside this project's scope.
