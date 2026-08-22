# SM120 semantics-preserving FP8 hot-block task graph

## Question

Can an exact Gemma 4 decode-M32 execution boundary on `sm_120` remove recurring
host dispatch, launch, or synchronization work across stock RMSNorm,
per-token E4M3 quantization, scaled GEMM, residual, cast, and the first real
consumer without changing any stock numerical boundary?

## Why this matters

The campaign needs a 20% price-normalized endpoint improvement and has already
seen a residual-aware fused producer save component time while changing
dynamic-FP8 activation semantics. RTX PRO 6000 has 188 SMs, 96 GiB GDDR7,
SM120 FP8/FP4 tensor cores, a 256-KiB register file per SM, and no NVLink
dependency for a single-GPU endpoint. A task graph that preserves the proven
stock producer/consumer bytes tests a materially different mechanism from
arithmetic fusion: fewer launches and host/synchronization gaps with unchanged
math.

## Scope

Use `$researcher` with deep profile plus `$kernel-research`. Bind the exact
stock Gemma 4 decode M32 path from the pinned runtime source: producer and
consumer symbols, K/N shapes, layouts, BF16/FP32/E4M3 scale convention,
residual and rounding boundaries, and expected calls per completed c32
request. Inspect current CUDA Graph, CUTLASS, cuBLASLt, vLLM, and SGLang
support before writing custom device code.

Implement one working non-generic entrypoint or exportable graph description
that preserves every stock tensor boundary and removes only launch,
host-dispatch, or synchronization work. Provide:

- an offline describe/export path that resolves exact integration symbols and
  emits a source-hash-bound task graph;
- a target-`sm_120` execution path for the smallest later correctness-bearing
  discriminator;
- a future oracle requiring exact activation, scale, residual, and downstream
  BF16-consumer agreement; and
- predicted movement in launches, host gaps, graph replay, and normalized
  seconds/request, with batch-total and per-request units separate.

Do not claim a GPU in the immediate offline phase, replay prior B200 samples,
change reduction/quantization semantics, or treat occupancy as the objective.

## Evidence and decision

Target model revision:
`b9ea41a2887d8607f594846523f94c6cc75ac8a4`. Target accelerator inventory
identity: `nvidia-rtx-pro-6000-blackwell-server`, `sm_120`, 188 SMs. The later
GPU discriminator may reuse the direct RTX PRO 6000 bench only after the
endpoint project releases it and the director explicitly assigns the handoff.

Persist `SM120_FP8_HOTBLOCK_TASKGRAPH_OFFLINE_RESULT.json` with measured,
source-backed, derived, and inferred fields. Return typed `none` if no
non-generic working boundary survives unchanged stock semantics. A working
entrypoint with a credible launch-gap bound earns one exact-consumer SM120
component run; prose design alone does not.
