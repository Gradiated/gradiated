# B200 FP8 cross-operator executor

## 2026-07-29 semantics-preserving task-graph reopening

The first exact B200 consumer rejected one realization, not the campaign's
cross-operator question. The residual-aware fused RMSNorm/quant primitive was
`35.392 us/call` faster than the compiled stock boundary, but it changed the
dynamic-FP8 activation and downstream BF16 gate-up output beyond the bound.
That component is consumed and must not be replayed.

Reopen this project for one materially different zero-GPU deep result:
construct a source-complete task-graph or persistent-dispatch realization that
sequences the pinned stock RMSNorm, per-token E4M3 quantization, scaled-MM, and
residual boundaries without moving a cast, reduction, scale, or rounding
point. The intervention may remove host/CUDA launch and synchronization
boundaries, but the stock FP8 activation bytes, FP32 `[M,1]` scales,
`residual_out`, and unchanged BF16 consumer output are the correctness
contract.

Bind the implementation to decode `M=32`, hidden `K=5376`, gate-up
`N=43008`, 60 layers, 21,480 selected calls per exact endpoint batch, pinned
vLLM commit `6d4a8e6d204a9b2827544003b26321fff62923da`, and B200 `sm_100`.
Use the existing discriminator and final terminal as the only historical
starting evidence. Produce a working exact-shape/hot-block entrypoint with a
CPU/offline describe or export path and a target-CUDA run path; a generic
executor design, literature report, or another residual-aware fused primitive
does not satisfy the project.

The offline terminal must identify exact producer and consumer symbols, graph
and stream boundaries, tensor lifetimes, predicted launches/synchronizations
removed, required runtime integration point, and the smallest later B200
measurement. Separate measured facts from derived launch/byte accounting and
inferred endpoint effect. Fail closed unless the proposed target run requires
bit-identical stock FP8 activations, scales, residual output, and downstream
BF16 output before timing.

This continuation has no GPU or provider authority. It may recommend one
later component, but it must not claim a bench, replay the consumed component,
submit an endpoint request, or weaken the original numerical contract.

## Question

Can one semantics-preserving execution boundary across a recurring Gemma 4
decode hot block—RMSNorm or residual input, dynamic per-token FP8
quantization, scaled matrix multiplication, and its immediately adjacent
epilogue/residual consumer—remove enough launch, synchronization, or
intermediate-memory cost to justify an exact B200 component measurement and a
short path to the fixed campaign endpoint target?

## Why this matters

The valid absolute B200 runtime-dynamic-FP8 c32 endpoint is
`0.633995593312477 s/request`, above the fixed
`0.500119281574996 s/request` target. The concurrent M32 project tests only a
Cutlass SM100 tile-dispatch cutoff for six M=32 GEMMs. This project must find
non-overlapping cost across operator boundaries rather than retuning that
dispatcher.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it`
- Revision: `b9ea41a2887d8607f594846523f94c6cc75ac8a4`
- Workload: c32 / 4,214 prompt / 358 output / text-only / non-reasoning
- Valid absolute endpoint:
  `../gemma4_b200_dynamic_fp8_endpoint/artifacts/b200-dynamic-fp8-repair2-20260728t1517z/FINAL_TERMINAL.json`
- Current FP8 source/shape accounting:
  `../gemma4_b200_fp8_residual_hotpath/B200_FP8_RESIDUAL_DISCRIMINATOR.json`
- Pinned image identity:
  `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`
- Economic comparator: `0.625149101968745 s/request`
- Campaign target: `0.500119281574996 s/request`

Treat the endpoint terminal's absolute FP8 result as authoritative. Do not use
its overwritten BF16 arm or any paired-delta field.

## Scope

Use `$researcher` with the deep profile and `$kernel-research`. Trace one
recurring decode block end to end through the exact pinned vLLM source and
Gemma geometry. Quantify its call count, tensor shapes/layouts, dtypes/scales,
producer and consumer symbols, intermediate bytes, launch/synchronization
boundaries, and conservative whole-request relevance.

Produce one concrete intervention from production input through its first
decision-bearing consumer. Prefer an existing runtime/library primitive when
it covers the semantics; otherwise implement a minimal source-level fused,
persistent, or task-graph hot-block path and a lifecycle-pure exact-shape
consumer. State one predicted physical change such as fewer launches, fewer
HBM bytes, or reduced synchronization.

The following are out of scope:

- changing `cutlass_gemm_sm100_fp8_dispatch` or the M32 tile cutoff;
- replaying c32, c64, c96, BF16, or any endpoint arm;
- a flag sweep, generic executor design, literature-only report, or profiler
  plan;
- claiming or mutating the shared B200 bench;
- provider operations or paid spend.

## Decision artifact

Write `B200_FP8_CROSS_OPERATOR_DISCRIMINATOR.json` containing:

- non-overlapping causal accounting from source and exact Gemma geometry;
- the selected hot block and exact producer/consumer contract;
- a hash-bound implementation plus lifecycle-pure exact-shape consumer, or a
  typed mechanism rejection supported by source/geometry;
- correctness oracle and numerical tolerance appropriate to the operation;
- predicted counter change and conservative whole-request relevance;
- the smallest B200 component measurement that would change the portfolio.

When the artifact is durable, pause the project for director review. Do not
claim a GPU or schedule endpoint work.
