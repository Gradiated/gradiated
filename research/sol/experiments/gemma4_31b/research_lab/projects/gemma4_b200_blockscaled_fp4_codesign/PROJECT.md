# Gemma 4 B200 block-scaled FP4 co-design

## Question

Can a B200-native block-scaled FP4 representation for the dominant Gemma 4
linear/weight-stream path plausibly beat the campaign's price-normalized
service-time target, with an implementation and recovery burden competitive
with the retained H200 dense-FP8 stack?

This is a representation-and-placement hypothesis, not a transfer of H200
throughput to B200 and not a generic Blackwell survey.

## Why it matters

The locked qualified H200 denominator is `0.625149101968745 s/request`, and the
campaign target at the H200 production-planning rate is
`0.500119281574996 s/request`. The current shared price inventory gives
`$3.25/GPU-hour` for H200 and `$5.15/GPU-hour` for B200. A B200 candidate must
therefore support approximately `0.315609255362861 s/request` or better at the
planning-rate base case to beat the target, with sensitivity thresholds
`0.349733763339158` and `0.284158682713066 s/request` at the B200 planning
range endpoints `$4.6475` and `$5.72/GPU-hour`.

B200 exposes native FP4/FP6, 8 TB/s HBM, a 126-MB last-level cache, SM100 tensor
cores, TMA, and thread-block clusters. Those facts make a lower-bit
model/accelerator co-design materially different from the H200 FP8 scheduler
experiment. They do not establish that Gemma's exact shapes, dynamic
activations, runtime consumer, quality burden, or multi-GPU topology can use
the advertised formats efficiently.

## Bound scope

- Exact model: `google/gemma-4-31B-it` at revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Primary workload: text-only, non-reasoning traffic around 4,214 prompt and
  358 output tokens per request at background-serving concurrency, including
  the campaign's cache accounting.
- Comparator: the locked qualified H200 result at
  `0.625149101968745 s/request`, plus the target derived above. Do not compare
  to the original BF16 baseline.
- Stable hardware and price facts come from
  `research/factory/data/accelerator_inventory.json` and
  `research/factory/data/gpu_prices.json`, current as of this delegation.
- Use the exact checkpoint index/config and the pinned serving source already
  bound in the retained H200 projects for tensor geometry. Do not copy model
  weights or claim the H200.

## Immediate evidence path

Work offline and do not claim or provision any GPU. Reconstruct the dominant
linear families, production M32/M384 consumer shapes, weight reuse, activation
quantization path, scale granularity, and adjacent epilogues from the exact
checkpoint and pinned source. Inspect current upstream SGLang, TensorRT-LLM,
vLLM, CUTLASS/cuBLASLt, and NVIDIA documentation only where it resolves a
specific SM100 FP4 consumer or layout uncertainty.

Produce executable, content-addressed source that:

1. enumerates the exact Gemma tensors and bytes affected by a supported
   block-scaled FP4 or FP6 format;
2. maps them to an identified current producer/consumer ABI and exact SM100
   tile/dataflow rather than peak-TFLOP extrapolation;
3. separates prefill, ordinary decode, target-verification, output-head,
   attention/KV, and non-linear residual work so the achievable whole-request
   bound cannot double count;
4. estimates memory residency, HBM/L2 traffic, scale traffic, conversion,
   launch, saturation, and required topology at the campaign workload; and
5. names one cheapest exact-shape GPU falsifier, including predicted physical
   or counter change, strongest supported baseline, correctness check, runtime
   image/source identity, expected wall time, and maximum spend.

Treat FP4 weights or activations as quality-unsafe unless a concrete
calibration/recovery method is identified. A proxy may establish the physical
cost mechanism, but it is not a deployable model result. Use `$kernel-research`
if the chosen discriminator requires exact-shape kernel work.

Return `B200_BLOCKSCALED_FP4_SCREEN.json` as either:

- `source_complete_candidate`: one current, implementable representation and
  consumer with a credible path to the base-case `0.315609255362861
  s/request` threshold, an explicit quality-recovery burden, and a bounded
  later B200 experiment; or
- `typed_none`: direct evidence that current support, exact geometry,
  attainable non-overlapping work reduction, topology, or quality burden
  makes this route less competitive than the retained alternatives.

Planning prose alone is not a result.

## Portfolio consequence

A source-complete candidate may trigger a later director-owned B200
create/register decision after immutable identities and spend are bound. A
typed negative closes only this exact block-scaled B200 representation and
releases the deep slot to another hardware/representation mechanism.
