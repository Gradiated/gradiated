# Gemma 4 MI355X FP8 runtime co-design

## Question

Can one MI355X serve the exact pinned Gemma 4 31B background workload more
economically than the campaign target by exploiting its 288-GB HBM3e,
8-TB/s memory system, and current ROCm FP8 execution path, without transferring
throughput claims from NVIDIA hardware?

This is an independent representation, runtime, and hardware-placement
hypothesis. It must not alter or wait on the claimed H100 registered-Attention
component.

## Decision hurdle

The locked qualified H200 denominator is `0.625149101968745 s/request`, and the
campaign target is `0.500119281574996 s/request` at the `$3.25/GPU-hour` H200
production-planning rate. The fresh shared price inventory gives MI355X a
`$2.60/GPU-hour` production-planning rate and `$2.40–$2.75` sensitivity range.
At matched workload, utilization, reliability, and accounting, the MI355X
candidate must therefore reach:

- `0.625149101968745 s/request` or better at `$2.60/hour`;
- `0.6772448604661404 s/request` or better at `$2.40/hour`; and
- `0.5910500600431771 s/request` or better at `$2.75/hour`.

The current `$2.95/hour` experimental listing would require
`0.5509788695317752 s/request`; it is an experiment-cost hurdle, not the
production headline.

## Bound scope

- Model: `google/gemma-4-31B-it` at revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Workload: text-only, non-reasoning c32 around 4,214 prompt and 358 output
  tokens per request, with the campaign's prefix-cache accounting.
- Architecture: 60 text layers, ten repetitions of five 1,024-token sliding
  layers and one global-attention layer, plus the 262,144-way tied output
  projection.
- Comparator: the qualified H200 service-time denominator and target above;
  do not use BF16 or early-FP8 baselines.
- Stable hardware and price inputs:
  `research/factory/data/accelerator_inventory.json` and
  `research/factory/data/gpu_prices.json`, fresh on admission.
- Exact model geometry input:
  `../gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/config.json`
  (SHA-256
  `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`).

## Immediate evidence path

Work offline. Inspect current primary ROCm, vLLM, SGLang, composable-kernel,
hipBLASLt, and AMD documentation only where needed to bind a real producer and
consumer. Use `$kernel-research` if the discriminator becomes kernel-level.

Produce executable, content-addressed source that:

1. extracts the exact Gemma linear, hybrid-attention, KV, normalization, and
   tied-head shapes and separates prefill, ordinary decode, and 384-row target
   verification;
2. maps each material FP8 or BF16 operation to a current ROCm runtime symbol,
   dtype/scale/layout contract, and identified consumer, marking unsupported
   boundaries explicitly;
3. models non-overlapping HBM/L2 traffic, tensor work, conversion, launch,
   occupancy, KV capacity, and topology at c32 rather than extrapolating peak
   FLOPS;
4. constructs the smallest runnable CPU/source discriminator for the highest
   uncertainty boundary and, if current source is incomplete, includes a
   working localized implementation or exact reproducer rather than a support
   wish list; and
5. derives the cheapest later MI355X exact-shape falsifier with predicted
   counter change, strongest supported baseline, numerical gate, wall-clock
   bound, and maximum provider spend.

Label evidence as measured, analytical, derived, inferred, synthetic, or
vendor-reported. Do not claim checkpoint quality or deployability from a
proxy.

## Terminal

Write `MI355X_FP8_RUNTIME_SCREEN.json` as exactly one of:

- `source_complete_mi355x_candidate`: the production input reaches a bound
  current consumer, the executable discriminator passes, the conservative
  non-overlapping bound clears the applicable price hurdle, and one bounded
  GPU falsifier is ready; or
- `typed_none`: exact runtime support, geometry, attainable work reduction,
  topology, or quality/recovery burden makes this route less competitive,
  with the failing evidence preserved.

Planning prose, peak-throughput transfer, or a generic AMD survey is not a
terminal.

## Budgets

- Wall clock: 180 minutes.
- Compute: at most 12 local CPU-hours; zero accelerator compute.
- Storage: at most 4 GiB of new durable artifacts.
- Provider spend: `$0.00`.
- Provider mutation and GPU claims: forbidden.

## Director iteration 2 — exact-shape MI355X falsifier

The source discriminator above is complete and remains immutable evidence.
New campaign authority activates its one predeclared target-hardware
falsifier; do not rerun or rewrite `MI355X_FP8_RUNTIME_SCREEN.json`.

### Scientific contract

- Hardware: one MI355X/gfx950 TP1 bench registered by the director.
- Runtime identities: vLLM
  `0164022c907014a27e81c514cd4dff6091904c2b` and AITER
  `6c48c5fa0e7c299adcf1987c8f4817720ceab311`.
- Baseline: pinned per-tensor online-E4M3
  `ROCmFP8ScaledMMLinearKernel -> torch._scaled_mm`, AITER
  flash/unified FP8-KV attention, and the BF16 tied head.
- Exact arms: every transformer linear at M32 and M384; sliding
  head256/GQA2/window1024 and global head512/GQA8/context4571 attention at
  M32 and M384; and BF16 `[32,5376] x [5376,262144]` tied head including
  twelve independent semantic calls per target cycle.
- Numerical gate: finite outputs; relative-L2 at most `0.02` and cosine at
  least `0.995` for FP8 linears/attention; argmax identity for head fixtures;
  no fallback.
- Timing: compile/autotune first, then warm profiler-off p50/p95 with
  compilation excluded and every output consumed. Collect only compiler
  resources and counters needed to test the bound bandwidth, prefill/M384
  tensor-use, and global-attention spill hypotheses.
- Whole-request gate: measured component aggregate at most
  `0.545847226968745 s/request`, plus the preserved
  `0.07930187499999997` launch/service reserve, for at most
  `0.625149101968745 s/request`.

Use `$kernel-research`. Create the mutable project-local entrypoint
`run_mi355x_exact_shape_falsifier.py`; its command is:

```bash
python3 run_mi355x_exact_shape_falsifier.py \
  --screen MI355X_FP8_RUNTIME_SCREEN.json \
  --output MI355X_EXACT_SHAPE_FALSIFIER.json
```

The entrypoint must verify the pinned source commits, read the current
registered bench identity, implement only ordinary API/layout adapters needed
to reach the unchanged consumers, persist a `science_started` marker before
the first decision-bearing GPU call, and emit raw per-shape timings,
numerical metrics, candidate-path proof, compiler resources, charged
aggregation, and terminal classification. Pre-science compile/API defects are
repairable inside the same claim; scientific identities and gates are not.

`MI355X_EXACT_SHAPE_FALSIFIER.json` is exactly one of:

- `measured_mi355x_candidate` when every consumer, numerical, no-fallback, and
  whole-request gate passes; or
- typed `none` when a valid exact-shape measurement fails a bound.

Missing hardware/source, setup failure, or an ordinary pre-science adapter
defect is operationally recoverable rather than typed `none`.

### Iteration-2 budgets and lifecycle

- Authorized provider spend: `$0.9833333333333333`.
- Provider exposure: at most 20 minutes at `$2.95/hour`, including
  provisioning, bootstrap, experiment, retrieval, and verified cleanup.
- GPU science: one exact-shape suite; no checkpoint transfer or endpoint run.
- Storage: at most 8 GiB of new source, build cache, and artifacts; no model
  checkpoint.
- Wall clock after claim: at most 16 minutes, leaving at least four minutes
  for retrieval and cleanup.
- The researcher may claim only the director-registered MI355X bench and may
  never create, delete, or retire provider resources.
- Do not apply the PTPC bridge, tied-K/V reuse, batching, compression, or any
  other survivor. This is the unstacked baseline falsifier.
