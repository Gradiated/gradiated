# Persistent dispatch for Gemma 4 sm_120 FP8 linears

## Question

Can one exact recurring Gemma 4 decode-M32 dynamic-FP8 linear boundary on
sm_120 replace repeated quantize/GEMM/epilogue launch and synchronization work
with a persistent or grouped dispatch while preserving every stock numerical
boundary?

## Why this matters

The exact RTX PRO 6000 SGLang endpoint is more than 2x slower than its
price-normalized target. Full-stack runtime replacement is the direct lane;
this independent lane tests whether the recurring FP8 linear dataflow itself
is a large sm_120 tax that a source-level dispatch intervention can remove.
It is distinct from the closed generic hot-block task-graph attempt: this
project must choose one concrete production linear consumer and implement its
actual dispatch path.

## Scope

Use `$researcher` with the deep profile and `$kernel-research`. Do not claim a
GPU. Trace the exact pinned Gemma 4 decode-M32 producer through per-token E4M3
quantization, scale convention, one repeated projection/GEMM, its residual or
cast epilogue, and the first BF16 consumer in the SGLang 0.5.16/CUDA 13 source
realized on the RTX bench. Bind exact symbols, M/K/N, layouts, dtypes, scales,
call count per c32 request, and the strongest current library path.

Form one physical hypothesis about launch/host-dispatch/synchronization or
underfilled-grid cost. Implement one non-generic persistent or grouped
dispatch entrypoint in project-local source that preserves all stock tensor
and scale boundaries. It must include an sm_120 target build/run command and a
future exact activation/scale/output oracle against the installed stock
consumer. Do not write a design-only executor, alter model geometry, fuse
across an unpreserved numerical boundary, or claim endpoint impact without a
measured component.

Persist `SM120_FP8_LINEAR_PERSISTENT_DISPATCH_OFFLINE_RESULT.json` with source
hashes, exact integration point, predicted physical counter/movement change,
auditable batch-total and per-request bound, target command, and the smallest
future GPU discriminator. Return typed `none` if no concrete boundary with
credible whole-request relevance survives source tracing.

## Budget and decision rule

Budget: 60 minutes wall clock, zero GPU and zero provider spend, at most 5 GiB
project-local build/source storage. This lane cannot claim the RTX bench until
the vLLM direct lane releases and the director explicitly assigns it.

Advance to a component measurement only if the implementation reaches the
unchanged production consumer and predicts a measurable reduction in launch,
synchronization, or physical data movement. A working positive component
would then be integrated into whichever scope-matched endpoint runtime
survives.
