# Persistent Gemma target executor

## Question

Can a persistent or SM-task-graph executor across Gemma's recurring target
verification boundaries reduce the qualified endpoint by at least 10% without
changing model architecture or target semantics?

## Scope

Start from current profiler and DFlash target-verification traces. Attribute
the exact recurring boundaries among:

- RMSNorm and dynamic FP8 quantization;
- QKV GEMM, attention, output projection, and residual;
- RMSNorm, gate/up GEMM, activation, down GEMM, and residual; and
- verification hidden states, depth-major tied LM head, acceptance, and KV
  commit.

This is independent of the packed attention project: choose a cross-operator
boundary whose non-overlapping measured wall share remains material after
excluding the attention candidate. The full 31B weights cannot reside on
chip, so the intervention must explain which intermediate HBM
materializations, synchronizations, launches, or producer/consumer barriers it
removes.

## Immediate experiment

Use the pinned runtime source and existing traces to extract one exact hot
block with production shapes, dtypes, scales, layouts, stream dependencies,
and strongest baseline. Implement a working persistent CUDA/Triton/ThunderKittens
or equivalent task-graph candidate for that block. The candidate must consume
real producer outputs and feed the real next consumer; a launch-overhead
microbenchmark or design document is not a result.

Measure exact work, finite/nonzero output, justified numerical tolerance,
interval time, materialized bytes, launch/synchronization count, occupancy,
and register/shared-memory resources. Derive a non-overlapping whole-request
bound. If positive and operationally plausible, bind the smallest endpoint
replacement in this project.

## Decision

Write `PERSISTENT_TARGET_EXECUTOR_RESULT.json` as:

- `hot_block_positive`: a measured working block removes enough physical work
  for a credible 10%-class endpoint path; or
- `typed_none`: the valid cross-operator implementation or measured wall share
  cannot support the target.

## Resources

- Researcher profile: `deep`
- Initial provider spend: `$0`; implementation and trace extraction first
- Wall clock: 6 hours
- Storage: 8 GiB
- No generic executor survey, separate readiness project, provider mutation,
  or quality run
