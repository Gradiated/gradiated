# Gemma 4 FP8 SwiGLU-to-down tile fusion co-design

## Decision question

Does the exact Gemma 4 31B c32 FP8 gate/up–SwiGLU–down boundary materialize
enough intermediate traffic, launch work, or synchronization to support a
credible tile-level fusion that materially reduces whole-request service time
without changing the model's BF16-visible outputs?

This is independent of DFlash request-state semantics and of the consumed FP8
weight-stream module. The campaign target remains
`0.500119281574996 s/request` against the qualified
`0.625149101968745 s/request` denominator.

## Hypothesis and competing explanation

The hypothesis is that the packed FP8 gate/up producer materializes a large
SwiGLU intermediate and pays a separate activation/down launch and memory
boundary at exact c32 shapes. A Hopper tile schedule that overlaps activation
with operand movement and feeds down-projection tiles without full
materialization can remove a measurable fraction of the request critical path.

The competing explanation is that the pinned runtime already hides or fuses
the relevant work, down projection is compute-bound with no reusable tile
lifetime, or the required FP8/BF16 rounding boundary makes a fused consumer
either numerically invalid or too resource-heavy to improve occupancy.

## Immediate deep cycle

Use `$researcher`, `$evidence-research`, and `$kernel-research` only for
mechanism-level source and accelerator reasoning. Consume the pinned runtime
source, exact Gemma MLP geometry, and existing request/component profiler
artifacts. Do not claim a GPU, compile a candidate, replay an endpoint, or
write another general literature review.

Produce one source-bound causal map of the exact gate/up output, SwiGLU
activation, quantization/rounding, down input, residual, and allocator
boundaries. Reconcile bytes, tensor shapes, invocation counts, critical-path
time, and overlap from existing measured evidence. Then design the smallest
exact-shape tile/dataflow candidate only if the traffic and time attribution
supports a credible positive whole-request bound and a cheap target-GPU
discriminator relative to competing portfolio work.

The result must be either:

- `source_complete_component_nomination`: a content-addressed candidate packet
  with exact shapes, dataflow, rounding semantics, resource model, expected
  counters, one target-GPU discriminator, and a conservative whole-request
  bound; or
- `typed_none`: evidence that materialization, critical-path share, numerical
  boundaries, or Hopper resource geometry cannot support a positive,
  testable opportunity.

## Quality and decision rules

- Preserve the pinned model, FP8 weight/scaling semantics, SwiGLU definition,
  BF16-visible down output, residual order, request ownership, and exact c32
  workload.
- A future component nomination must require bitwise equality at the
  BF16-visible consumer boundary. If exact equality is analytically
  impossible, return typed none rather than substituting a tolerance.
- The 2026-07-25T23:09Z director decision supersedes the original positive-only
  promotion rule: a nomination must clear 5% of the complete
  gate/up–activation–quant–down component and 1% of the measured whole-request
  window under a conservative bound. It must also be source-complete or
  narrowly implementable and cheap enough to beat competing warm-bench uses.
- Do not transfer H100/Qwen literature speedups to Gemma/H200; use them only to
  motivate the dataflow question.

## Budgets and artifacts

- Researcher profile: `deep`
- Wall-clock: at most 120 minutes
- New provider spend: `$0`
- GPU claims and provider mutation: forbidden
- Local storage: at most 2 GiB
- Artifacts: `SWIGLU_DOWN_FUSION_CAUSAL_MAP.json`, optional reproducible
  analytical script, optional source-complete candidate packet, and
  `SWIGLU_DOWN_FUSION_TERMINAL.json`

Stop after the typed terminal. A positive packet requires a later director
admission before compilation or GPU execution.
