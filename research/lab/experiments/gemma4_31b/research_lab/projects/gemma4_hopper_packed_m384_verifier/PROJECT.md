# Hopper-native packed M384 verifier

## Question

Can one custom Hopper execution decomposition accelerate Gemma 4's exact
target-verification attention path enough to save approximately 8–10% of the
qualified whole request while preserving numerical and target-token semantics?

## Causal basis

The qualified endpoint is `0.625149101968745 s/request`; the seed target is
`0.500119281574996`. Existing NCU evidence shows the global d512 attention
kernel at 255 registers/thread, one CTA/SM, about 12.5% achieved warp
occupancy, low DRAM utilization, and substantial L2 activity. Merely shrinking
`BLOCK_M` regressed. The next intervention must change execution
decomposition, not repeat a tile sweep.

Use `$kernel-research`. Bind the exact production consumers:

- c32 target verification with query length around 12 and M384 work;
- fifty local layers with d256, GQA2, window 1,024;
- ten global layers with d512, GQA8, campaign contexts;
- dynamic E4M3 linear state and direct FP8 paged-KV consumption;
- current strongest exact-shape/runtime baseline and qualified endpoint
  denominator.

## Experiment

Implement a working CUDA/Triton exact-consumer candidate that combines the
highest-value subset of:

- packing heterogeneous request/query-KV regions into balanced work groups;
- TMA producer warps separated from WGMMA/softmax consumers;
- context partitioning with exact online-softmax reduction to lower live
  accumulator/register pressure;
- direct paged FP8 KV reads without dense materialization; and
- CUDA-graph-compatible fixed production shapes.

Do not produce a design-only terminal. First make the candidate compile and
pass finite/nonzero, justified numerical-tolerance, output-consumption,
no-fallback, and exact-work gates on H100. Measure profiler-off paired p50/p95
against the strongest baseline, then collect only the counters needed to test
register residency, active warps, L2/HBM traffic, grid waves, and interval
time. If the component is positive, bind and run the cheapest compatible
endpoint stack rather than opening an integration successor.

## Decision

Write `PACKED_M384_VERIFIER_RESULT.json` as either:

- `component_positive`: measured exact-consumer saving with a quantified
  whole-request projection and direct endpoint command; or
- `typed_none`: a valid implementation shows insufficient physical or
  whole-request benefit.

Compile/API/integration failures before a valid candidate row are repairable
inside the same retained claim and do not reject the mechanism.

## Endpoint promotion

The H100 component is decision-bearing and positive. Preserve it without
replay and use `$kernel-research` to integrate the measured V2 local/global
consumers into the pinned qualified c32 endpoint stack. The next scientific
result is one matched profiler-off control/candidate endpoint pair with exact
request, token, cache, and target-token sanity gates. Keep source integration
inside this project; do not open an endpoint successor.

## Resources

- Researcher profile: `deep`
- Target: retained or fresh authenticated H100 SXM
- Authorized cumulative spend: `$8`
- GPU exposure: at most 90 minutes, including repair and retrieval
- Wall clock: 6 hours
- Storage: 12 GiB including build cache and profiler artifacts
- Reuse the current H100 image/compiler state when safe; never create or
  destroy provider resources from the researcher
