# B200 price-normalized v0.5.15 placement

## Question

Can one B200 SXM run the exact official SGLang v0.5.15 Gemma 4 31B
dynamic-FP8, E5M2 page-1 KV, native depth-12 NGRAM stack below the campaign's
`$0.14/M` sustainable planning target, and does the bound image exercise an
official SM100 path without changing runtime or workload semantics?

## Why this matters

The H200 runtime lane is recovering one startup conflict, while the H100 lane
has a positive analytical fit and is entering execution. B200 is a materially
different SM100 realization with higher planning cost and potentially much
higher throughput. Its value depends on exact image support, model/cache fit,
graph and Triton geometry, and a substantially stricter price-normalized
service-time hurdle—not transferred H100/H200 throughput.

## Scope and immediate result

Mechanically verify `DIRECTOR_BINDING.json`. Trace the bound official v0.5.15
image and source against shared B200 geometry, the exact Gemma hybrid-attention
layout, dynamic-FP8 linear path, FP8 E5M2 KV, NGRAM target verification, and
CUDA-graph capture. Derive the exact `$0.14/M` raw and sustainable service-time
hurdles from the bound workload. Return at most one immutable execution packet
with a smallest activation/fit discriminator and conditional endpoint, or
typed `none`.

This phase has `$0` provider authority. Do not create or claim a GPU, transfer
weights, infer throughput from H100/H200, or sweep flags, runtimes, or
representations.

## Budget and decision gate

- Provider/GPU spend: `$0`.
- Wall clock: 75 minutes.
- Local compute: at most 2 CPU-hours.
- Storage: at most 4 GiB; no model weights or container layers.
- Nominate only if official SM100 support is source-proved, safe memory fit is
  analytical, and the price-normalized hurdle is physically credible enough
  to justify a later direct measurement.
