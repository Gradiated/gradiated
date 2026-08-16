# Gemma 4 MI355X AITER FP8 linear bridge co-design

## Question

Can one real current-runtime producer bridge make AITER's gfx950 per-token /
per-channel FP8 linear consumer reachable for every exact Gemma 4 transformer
linear, while preserving all model capacity and reducing the conservative
MI355X request bound from `0.6000950932112802` to at most
`0.5910500600431771 s/request`?

## Why this is the next experiment

Three source-real batching policies are now negative. The strongest static c96
service point was `0.47035474275794686 s/request`, which becomes
`0.5226163808421632 s/request` at the campaign's required 90% utilization even
before finite-stream overhead. Admission policy alone therefore cannot reach
the locked `0.500119281574996` H200-equivalent target.

The preserved MI355X screen exposes a different causal boundary. Current vLLM
online FP8 produces per-tensor activation and weight scales and falls through
`torch._scaled_mm`; current AITER exposes gfx950 FP8 consumers that require
per-token activation scales and per-channel, potentially preshuffled weights.
The transformer-linear account is `0.21629139633045502 s/request` for prefill,
`0.1370320896` for ordinary decode, and `0.0105828581376` for target
verification. Only `0.009045033168103123 s/request` is needed to clear the
preserved `$2.75/hour` MI355X sensitivity. Implementing and binding that
missing producer/consumer seam is a materially different kernel/runtime
question, not another support survey.

## Bound evidence

- Campaign identity: exact pinned Gemma 4 31B checkpoint and the 4,214 prompt /
  358 output-token c32 workload in `CAMPAIGN.md`.
- Baseline and exact geometry:
  `../gemma4_mi355x_fp8_runtime_codesign/MI355X_FP8_RUNTIME_SCREEN.json`.
- Current source identities:
  `../gemma4_mi355x_fp8_runtime_codesign/SOURCE_BINDINGS.json`.
- Preserve the completed batching terminals in
  `../gemma4_mi355x_background_batching_codesign/`; do not stack a batching
  gain into this experiment.
- The prior MXFP6 result closes only its E3M2 block-scaled route and fallback
  path. It does not test this E4M3 per-token/per-channel AITER bridge.

## Experiment contract

Use `$kernel-research` for the gfx950 producer-to-consumer analysis and source
work.

1. Rebind the current official vLLM and AITER commits, the exact Gemma model
   symbols, and the selected AITER consumer. Record source and patch hashes.
2. Preregister exactly one bridge before evaluating it:
   - keep the BF16 checkpoint and tied embedding/head semantics unchanged;
   - create one load-time E4M3 transformer-weight shadow with the exact scale
     granularity and layout required by the selected maintained AITER kernel;
   - produce dynamic per-token activation scales at the real linear callsite;
   - dispatch the same bridge through every sliding-QKV, sliding-O,
     global-QKV, global-O, gate/up, and down projection at exact prefill,
     M32-decode, and M384-verification shapes;
   - preserve every layer, parameter, request, token, and output row.
3. Implement the bridge as project-local source or a minimal patch against the
   pinned runtime. A symbol listing, hypothetical adapter, standalone
   quantizer, or consumer that is unreachable from Gemma forward is invalid.
4. Exercise all CPU-available layout, scale, dispatch, shape, and numerical
   fixtures. Use a justified BF16-reference tolerance for the floating-point
   transformation; bitwise equality is not required. Any missing exact shape,
   nonfinite output, material semantic mismatch, or fallback is negative.
5. Charge load-time conversion amortization, weight-shadow memory, scales,
   preshuffle/padding, dynamic quantization, reduction, synchronization,
   launches, outputs, unsupported-shape fallback, service reserve, and all
   unchanged request components. Do not credit vendor peaks, nominal format
   width, nominal waves, or unmeasured target performance.
6. Emit `MI355X_AITER_FP8_LINEAR_BRIDGE_SCREEN.json` with:
   - exact producer, consumer, layouts, dtypes, scales, phases, and all shape
     results;
   - source/patch identities and test commands;
   - memory and full-request accounting against
     `0.6000950932112802 s/request`;
   - one finite target-MI355X measurement program and its per-shape timing
     hurdles;
   - classification `source_complete_measurement_candidate` only if the real
     bridge is complete and conservative evidence reaches at most
     `0.5910500600431771 s/request`; otherwise typed `none`.

The candidate classification is measurement readiness, not MI355X throughput,
quality, or deployment evidence. Do not amend or supersede the preserved
baseline MI355X falsifier.

## Budgets and prohibited actions

- Wall clock: at most 75 minutes.
- Compute: local CPU only; no accelerator claim.
- Storage: at most 4 GiB of new project-local source, fixtures, and artifacts.
- Spend: `$0`.
- Do not copy or download the checkpoint.
- Do not contact a provider, use paid APIs, create resources, or mutate GPU
  inventory.
- Do not sweep scale granularities, layouts, kernels, or formats.
- Do not reopen batching, MXFP6, lossless compression, placement surveys, or
  output-head interventions.

## Portfolio-changing result

A source-complete candidate below the `$2.75/hour` sensitivity becomes a
distinct later MI355X component falsifier once durable authority exists. A
typed negative closes this one producer/consumer bridge and returns the
portfolio to a different mechanism; it does not weaken the preserved c32
MI355X FP8 lifecycle.
