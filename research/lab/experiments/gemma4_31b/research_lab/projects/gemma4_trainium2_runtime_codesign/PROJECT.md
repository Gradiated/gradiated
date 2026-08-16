# Trainium2 runtime and placement co-design

## Question

Can a currently obtainable AWS Trainium2 topology serve the exact
`google/gemma-4-31B-it` revision
`b9ea41a2887d8607f594846523f94c6cc75ac8a4` with its hybrid five-local /
one-global attention, exact 1,024-token local window, dynamic lower-precision
linears/KV path, and tied 262,144-row head at or below the campaign's locked
`$0.109725/M total tokens` sustainable target?

Return an executable, source-bound placement candidate or typed `none`. A
generic Trainium survey, vendor-peak extrapolation, or unsupported model-name
claim is not a result.

## Why this matters

The H200/H100 paid authority is exhausted for a new lifecycle, while
source-complete B200 and MI355X candidates remain unmeasured. Trainium2 is a
materially different compiler, memory, topology, and pricing route already
represented in the shared accelerator inventory but absent from its price
inventory. It can change the price-normalized frontier without stacking the
quality-unsafe prompt, global-KV, or recurrent-local candidates.

The screen is decision-bearing only if it connects exact Gemma geometry to a
real current Neuron model/runtime consumer and includes the purchasable
instance topology, achievable replica packing, utilization, and all-in
economics.

## Bound inputs

- Campaign: `../../CAMPAIGN.md`.
- Exact model configuration:
  `../gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json`
  (`sha256:e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`).
- Exact c32 trace/workload geometry:
  `../gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/trace/exact_c32_profile.trace.json.gz`
  (`sha256:37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b`).
- Shared hardware facts:
  `../../../../../../factory/data/accelerator_inventory.json`, entry
  `aws-trainium2`.
- Locked qualified service denominator:
  `0.625149101968745 s/request`.
- Locked sustainable target:
  `0.500119281574996 s/request` at the existing H200 planning basis, or
  `$0.109725/M total tokens` after scope-matched price normalization.
- Workload mix: approximately 4,214 prompt and 358 output tokens/request,
  12.7% prompt cache reads, c32 background concurrency, and 90% maximum
  planning utilization before additional headroom.

## Scope

Work entirely offline and spend `$0`.

1. Start from the shared `aws-trainium2` inventory entry. Refresh only missing
   Trainium2 facts: current official purchasable topology/rates and current
   Neuron, NxD Inference, Transformers NeuronX, or vLLM-Neuron support. Do not
   repeat GPU-price research.
2. Pin every external source, documentation page, release, and price by
   retrieval time and content/revision identity. Prefer official AWS/Neuron
   repositories and documentation; label vendor-reported and inferred
   evidence separately.
3. Trace the exact Gemma 4 architecture through a real current runtime model
   class and first consumers. Verify or implement source for:
   - 60 dense layers at hidden width 5,376 and intermediate width 21,504;
   - five 32Q/16KV, head-dim-256 local layers followed by one
     32Q/4KV, head-dim-512 global layer;
   - exact 1,024-token sliding windows and unified global KV;
   - supported FP8/cFP8 producer and linear consumers without hidden BF16
     materialization;
   - the 262,144 x 5,376 tied head, softcap, and sampler; and
   - c32 prompt-heavy batching, cache ownership, and compilation shapes.
4. If stock support is incomplete, implement only the smallest
   source-complete model/runtime adapter needed to reach these consumers.
   Metadata, a manifest, pseudocode, or an uninvoked registration hook is not
   source complete. If the missing compiler/runtime boundary cannot be
   implemented credibly without target hardware or proprietary bytes, return
   typed `none`.
5. Determine the minimum purchasable topology and maximum conservative
   replicas per instance from HBM, executable/cache state, NeuronCore
   placement, collectives, host memory, and failure/headroom constraints.
   Charge the whole instance, not a nominal chip fraction unless concurrent
   replicas mechanically consume the remainder.
6. Produce a conservative service/cost bound using exact model/workload work,
   a current source- or measurement-backed Neuron execution prior, and all
   material input/cache/output, host, storage, orchestration, reload/failure,
   queueing, and 90%-utilization costs. Vendor peaks and GPU throughput
   transfer are forbidden.
7. Emit explicit sensitivities for precision fallbacks, topology/replica
   packing, compile-time shape restrictions, cache rate, utilization, and
   current on-demand versus committed rates. A candidate must clear
   `$0.109725/M` at the selected production planning rate; a favorable
   on-demand experiment rate alone is insufficient.

Do not claim hardware, contact a provider, create AWS resources, download the
checkpoint, or run a paid compile. Do not credit prompt-state, global-KV,
recurrent-local, conditional-depth, or other model-change savings.

## Decision artifact

Emit `TRAINIUM2_RUNTIME_PLACEMENT_SCREEN.json` with:

- `classification`: `source_complete_trainium2_candidate` or `typed_none`;
- bound model, workload, source, price, and hardware identities;
- exact runtime producer/consumer support matrix and adapter source hashes;
- minimum topology, replica packing, HBM/state accounting, and failure
  boundaries;
- conservative service-time and all-in `$ / M total tokens` accounting;
- rate, utilization, cache, topology, and fallback sensitivities;
- explicit measured/vendor/derived/inferred evidence labels;
- remaining compile, target-hardware, quality, and production-availability
  gates; and
- zero-spend resource use.

## What changes the portfolio

A source-complete candidate identifies one later Neuron compile and
exact-workload measurement if new authority becomes available. Typed `none`
closes the current Trainium2/Neuron placement because of a named runtime,
topology, or economic floor; it does not transfer to future Neuron releases
or other accelerators.
