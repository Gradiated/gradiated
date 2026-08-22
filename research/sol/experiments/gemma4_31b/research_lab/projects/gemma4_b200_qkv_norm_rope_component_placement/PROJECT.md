# B200 QKV→normalization/RoPE exact-consumer placement

## Question

On one NVIDIA B200, does the already accepted Gemma 4 decode-c32 direct-Q /
direct-E5M2-KV epilogue preserve the unchanged pinned SGLang decode-attention
consumer and deliver enough absolute component speed to improve
price-normalized placement versus the measured H200 component?

This is a hardware-transfer question. It does not replay or amend the accepted
H200 sample, and it cannot promote an endpoint by itself.

## Why it matters

The exact H200 component removed four pre-attention launches and
2.62–2.88 MB of compulsory epilogue traffic per c32 call. It reduced the
local/global component medians by 26.7%/18.6% with consumer relative-L2 at
zero. B200 has substantially higher HBM bandwidth and a different SM100
execution target, but costs `$3.95/GPU-hour` experimentally versus the
measured H200 `$2.45/GPU-hour`. A direct exact-consumer measurement cheaply
tests whether bandwidth and launch realization can overcome that 1.612× rate
ratio before considering a full B200 endpoint.

## Frozen inputs

- Model identity: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime identity: SGLang `v0.5.13@28b095c01005d4a3a2a5b637b7d028b07fba31b2`.
- Container identity:
  `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Exact runner:
  `inputs/bound/qkv_direct_consumer_bench.py`,
  SHA-256 `10d2538ce6d35a4fbedf4b8db946d8e93d7004690fa1a0c6f0cae3c6427e63ff`.
- H200 comparator terminal:
  `inputs/bound/H200_SCIENTIFIC_TERMINAL.json`,
  SHA-256 `6aa40802441a36184129bcef9486180acf0b5eba432b68715085d9f7c58d55a2`.
- H200 raw result:
  `inputs/bound/H200_RESULT.json`,
  SHA-256 `ad4192d8cb86c56791f2470e5b4bd0586a4e445d033e03cda76326677a938caf`.

The runner covers the exact local
`Q32/KV16/d256/window1024/full-RoPE` and global
`Q32/KV4/d512/context4570/partial-RoPE-0.25` decode-c32 geometries with BF16
QKV producer output, direct E5M2 K/V cache rows, and the unchanged
`decode_attention_fwd` consumer.

## Hypothesis and falsifier

The candidate is primarily launch- and memory-traffic sensitive. B200's
8 TB/s HBM and SM100 implementation may reduce absolute stock and candidate
time enough to offset its higher experimental hourly rate. At the measured
provider rates, equal component cost requires a B200/H200 latency ratio no
greater than `2.45/3.95 = 0.620253`.

The placement signal is falsified if the correct B200 candidate costs more per
call than the accepted H200 candidate at actual experiment rates. That closes
only this component-level B200 placement signal; it does not establish that a
full B200 endpoint is uneconomic.

## Experiment

Use `$researcher` with execution profile, `$kernel-research`, and
`$experiment-run`. After a director supplies a claimed B200, reuse the exact
frozen runner. Treat the first tiny CUDA invocation as the discovery smoke,
repair ordinary B200 image/compiler/runtime defects in the same mutable claim,
then execute one profiler-off local/global comparison. Do not transfer H200
timings as B200 results.

Require:

- exact B200 identity, driver, image, runtime, and loaded candidate/consumer
  symbols;
- stock and candidate first-call completion markers for each geometry;
- full numerical gates and candidate-path proof;
- alternating warm timing distributions for both geometries;
- B200/H200 latency and actual-rate-normalized cost ratios;
- useful GPU seconds, provider exposure, and generation-fenced release.

## Gates

- Numerical gate: consumer relative-L2 `<= max(0.002, 2× stock A/A)`, finite
  output, correct Q and K/V cache layouts, and unchanged consumer invocation.
- Evidence gate: both geometries complete with stock and candidate timings,
  path proof, and no profiler in the timed interval.
- Placement-positive gate: correct candidate and actual-rate-normalized
  component cost no worse than H200 for at least one geometry. Report any
  correct B200 within-device speedup even if placement-negative.

## Resources and limits

- Target: authenticated Nebius 1×B200 preemptible placement; the 2026-07-29
  selector found high availability at `$3.95/GPU-hour`.
- Cumulative project spend ceiling: `$5.00`.
- Provider lifecycle: at most 70 minutes from create attempt through verified
  cleanup, including boot, image/runtime preparation, execution, retrieval,
  and release/cleanup margin.
- No checkpoint is required. Additional storage is limited to 100 GiB boot
  disk and 2 GiB experiment artifacts.
- Exactly one complete local/global scientific ledger. Pre-science integration
  repairs remain inside the same claim and do not consume a sample.

Provider creation and teardown remain director-owned.
