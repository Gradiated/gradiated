# Gemma 4 MI355X MXFP6 transformer-linear co-design

## Question

Can a real native block-scaled MXFP6 producer/consumer on MI355X reduce the
exact Gemma 4 transformer-linear path enough to improve the preserved MI355X
FP8 placement bound, while retaining all layers, widths, parameters, tokens,
and vocabulary capacity? Return a source-complete physical candidate or typed
`none`.

This is a representation and dataflow hypothesis on the already-ranked
MI355X placement, not another provider survey. It must not modify or delay the
preserved FP8 next-dollar lifecycle.

## Authoritative bindings

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only,
  non-reasoning mode.
- Primary workload: background c32 around 4,214 prompt and 358 output tokens
  per request, with 12.7% of prompt tokens served from cache.
- Locked H200 denominator and target: `0.625149101968745` and
  `0.500119281574996 s/request`; sustainable cost target
  `$0.109725/M total tokens`.
- The preserved MI355X FP8 placement uses online per-tensor OCP E4M3FN
  transformer linears, FP8 KV, and a BF16 tied head. At the `$2.60/hour`
  planning rate its analytical bound is `0.6000950932112802 s/request`
  against a placement-specific `0.625149101968745 s/request` hurdle, only
  `0.025054008757464774 s/request` of margin. It fails at the current
  `$2.75–$2.95/hour` sensitivity rates.
- Shared accelerator inventory binds MI355X/gfx950 native MXFP6 capability,
  288 GB HBM3e, 8,000 GB/s bandwidth, and ROCm/AITER software. Peaks are
  screening priors, not performance evidence.
- The completed MI355X FP8 exact-shape falsifier remains the sole next funded
  lifecycle at `$0.9833333333333333`. This project has no authority to alter,
  prepare, execute, or stack onto that lifecycle.

## Scope

1. Bind current production source for the first real MXFP6 weight producer
   and decision-bearing MI355X/gfx950 GEMM consumer in vLLM/ROCm, AITER,
   hipBLASLt, Quark, or another maintained exact path.
2. Map every Gemma 4 transformer-linear shape at prefill/verification `M=384`
   and decode `M=32`, including Q/K/V/O and gate/up/down projections. Bind
   block geometry, scale encoding, padding, layout, dtype conversions,
   epilogues, and fallback behavior.
3. Preserve all 60 layers, hidden width 5,376, intermediate width 21,504,
   attention heads, checkpoint parameters, and token work. MXFP6
   quantization is an explicitly quality-unqualified representation change;
   layer/width/parameter deletion, sparsity, conditional execution, and
   capacity credit are invalid.
4. Keep FP8 KV attention and the BF16 tied 262,144-row head identical to the
   preserved MI355X placement. Credit only the transformer-linear
   representation change and charge every quantization, scale, padding,
   conversion, dispatch, metadata, and fallback cost.
5. Implement a source-complete exact-shape producer-to-consumer discriminator
   with deterministic synthetic inputs. CPU simulation may establish packing
   and accounting, but generic source, format availability, vendor peaks, or
   unsupported generated code cannot establish target execution.
6. Reconstruct the whole-request bound from the preserved non-overlapping
   component accounting. A candidate must be conservatively faster than
   `0.6000950932112802 s/request` and remain at or below the
   `0.625149101968745 s/request` MI355X price hurdle after all overhead. Do
   not transfer timing from B200, H100, TPU, Trainium2, Gaudi, or another
   model/workload.
7. Emit `MI355X_MXFP6_PHYSICAL_SCREEN.json` as either:
   - `source_complete_mi355x_mxfp6_candidate`: the exact producer, consumer,
     shapes, physical accounting, no-fallback path, and a strictly improved
     whole-request bound are source-complete, with one finite target-MI355X
     validation discriminator; or
   - `typed_none`: identify the first decisive missing producer, consumer,
     exact-shape support, fallback, overhead, physical-impact, or economic
     gate.

## Invalid shortcuts

- Do not download the checkpoint, use paid APIs, claim hardware, contact a
  provider, log in, or create resources.
- Do not sweep MXFP4, INT4, W4A8, sparsity, block sizes, layers, widths, or
  formats. Test the single native MXFP6 mechanism.
- Do not infer speed from nominal bytes, vendor peaks, another accelerator,
  another model, or format support alone.
- Do not reuse the closed B200 NVFP4 or H200/L40S INT4 evidence as
  scope-matched proof.
- Do not stack prompt-state, global-KV, recurrent-local, speculative,
  placement, or other model/runtime gains.
- Do not promote a source-complete physical candidate as measured,
  quality-qualified, or production-eligible.

## Resource envelope

- Wall clock: at most 90 minutes.
- Local compute: at most 4 CPU-hours; no local accelerator assumption.
- Storage: at most 2 GiB of new source and artifacts.
- Provider/API spend: `$0`.

## Portfolio consequence

A qualifying result may nominate an MXFP6 arm for a later director-ranked
target-MI355X discriminator, but it does not displace or amend the preserved
FP8 lifecycle in this turn. A typed negative closes only this current
MXFP6 transformer-linear source/dataflow path.
