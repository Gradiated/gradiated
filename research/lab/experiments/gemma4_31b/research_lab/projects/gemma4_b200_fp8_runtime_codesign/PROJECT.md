# Gemma 4 B200 FP8 runtime co-design

## Question

Can one B200 serve the exact pinned Gemma 4 31B background workload at or
below the campaign's locked cost target by mapping its hybrid-attention,
dynamic-FP8 transformer, KV, and tied-head geometry to current Blackwell
consumers?

This is an independent hardware-placement and runtime hypothesis. It must not
alter, wait on, or duplicate the H100 registered-Attention adapter repair.

## Decision hurdle

The locked H200 target is `0.500119281574996 s/request` at
`$3.25/GPU-hour`. The fresh shared price inventory gives B200 a
`$5.15/GPU-hour` production-planning rate and a `$4.6475–$5.72` sensitivity
range. At matched workload, utilization, reliability, and accounting, B200
must therefore reach:

- `0.315609255362861553 s/request` or better at `$5.15/hour`;
- `0.349733763339158042 s/request` or better at `$4.6475/hour`; and
- `0.284158682713065909 s/request` or better at `$5.72/hour`.

The `$3.95/hour` public-preemptible experiment rate would require
`0.411490548131325823 s/request`; it is not the production headline.

## Bound scope

- Model: `google/gemma-4-31B-it` at revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Workload: text-only, non-reasoning c32 around 4,214 prompt and 358 output
  tokens per request, with the campaign's prefix-cache accounting.
- Architecture: 60 text layers, ten repetitions of five 1,024-token sliding
  layers and one global-attention layer, plus the 262,144-way tied output
  projection.
- Comparator: the locked H200 target and B200 price-normalized hurdles above;
  do not use BF16, early-FP8, peak-throughput, or MI355X estimates as measured
  B200 evidence.
- Stable hardware and price inputs:
  `research/factory/data/accelerator_inventory.json` and
  `research/factory/data/gpu_prices.json`, fresh at admission.
- Exact model geometry input:
  `../gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/config.json`
  (SHA-256
  `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`).

## Immediate evidence path

Work offline. Inspect current primary vLLM, SGLang, TensorRT-LLM, CUTLASS, and
NVIDIA Blackwell documentation or source only where needed to bind a real
producer and consumer. Use `$kernel-research` if the discriminator becomes
kernel-level.

Produce executable, content-addressed source that:

1. extracts the exact transformer-linear, local/global attention, FP8-KV,
   normalization, and tied-head shapes for prefill, ordinary c32 decode, and
   384-row target verification;
2. maps every material FP8/BF16 operation to a current SM100 runtime symbol
   and its dtype, scale, layout, and accumulator contract, explicitly marking
   any Hopper fallback or unsupported boundary;
3. models non-overlapping HBM/L2 traffic, tensor work, conversion, launch,
   occupancy, KV capacity, and topology without transferring H100, H200, or
   MI355X efficiency;
4. executes the smallest CPU/source discriminator for the highest-uncertainty
   production boundary and includes a localized implementation or exact
   reproducer when current source is incomplete; and
5. specifies one cheapest later B200 exact-shape falsifier with the predicted
   counter change, strongest source-supported baseline, numerical gate,
   wall-clock bound, and maximum provider spend.

FP4 or FP6 may be used only as an explicitly quality-unsafe execution proxy
unless a current exact-checkpoint representation and recovery contract are
source-bound. Do not convert proxy speed into a deployability claim.

## Terminal

Write `B200_FP8_RUNTIME_SCREEN.json` as exactly one of:

- `source_complete_b200_candidate`: production input reaches bound current
  consumers, the executable discriminator passes, a conservative
  non-overlapping bound clears the applicable production-planning hurdle, and
  one bounded GPU falsifier is ready; or
- `typed_none`: runtime support, exact geometry, attainable work reduction,
  topology, or quality/recovery burden makes B200 noncompetitive, with the
  failing evidence preserved.

A generic Blackwell survey, nominal peak ratio, or another launch/readiness
artifact is not a terminal.

## Budgets

- Wall clock: 180 minutes.
- Compute: at most 12 local CPU-hours; zero accelerator compute.
- Storage: at most 4 GiB of new durable artifacts.
- Provider spend: `$0.00`.
- Provider contact, mutation, and GPU claims: forbidden.
