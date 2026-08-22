# FP8 down-projection → residual → next-normalization dataflow

## Question

For the exact pinned Gemma 4 31B c32 decode path on H200, can the dynamic-FP8
MLP down-projection epilogue hand its `[M,5376]` result through residual
addition and the next RMSNorm/dynamic-E4M3 producer with less global
materialization, launch, or reread traffic than the current runtime while
preserving the exact residual and normalization semantics?

This is a materially different boundary from the closed QKV-mainloop cluster
handoff. That consumer fans one `[M,5376]` activation across 256
`N=16384` output tiles. Here the producer itself creates the hidden-width
`N=5376` row consumed by residual addition and the next normalization.

## Why it matters

The campaign must move the qualified `0.625149101968745 s/request` denominator
toward `0.500119281574996`, or produce an equivalent price-normalized result.
The funded corrected materialized norm→FP8 component can remove one normalized
BF16 intermediate, but the completed mainloop study proves that a portable
SM90 cluster cannot distribute that activation economically across the real
QKV consumer. A different cross-operator boundary is valuable only if its
producer/output geometry permits a bounded synchronization and traffic win.

## Evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang `v0.5.13@28b095c01005d4a3a2a5b637b7d028b07fba31b2`.
- Image: `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Target: NVIDIA H200 SXM, sm_90a, 132 SMs.
- Decode shapes: `M ∈ {1,16,32}`, hidden/output width `5376`; derive and bind
  the exact down-projection K, layouts, scales, producer symbol, residual
  symbol, next RMSNorm symbol, and first downstream quantized consumer from
  pinned source rather than assuming them.
- Predecessor evidence:
  `../gemma4_h200_rmsnorm_fp8_qkv_mainloop_fusion/MECHANISM_TERMINAL.json`
  and `MECHANISM_ANALYSIS.json`. Treat their cluster-handoff and bounded
  recomputation families as closed controls, not candidates to rename.

## Scope

Use `$kernel-research` and `$experiment-run` with a deep profile. Trace the
actual pinned down-projection epilogue through residual mutation, next
normalization, dynamic-E4M3 quantization, and its first real consumer. Build a
typed opportunity register and compare at least:

1. an epilogue that persists the required residual output while producing
   exact row-statistic partials for a bounded finalizer;
2. a legal SM90a cluster/DSM decomposition across the hidden-width output;
3. a persistent or two-phase producer/finalizer that reduces rereads without
   duplicating the down-projection or changing its accumulation;
4. the unchanged materialized runtime as a negative control.

For every decomposition calculate compulsory bytes, extra bytes, useful and
duplicated FLOPs, grid waves, cluster scope, synchronization, registers,
shared memory, and a whole-request upper bound. Preserve exact FP8 scale
granularity, residual ordering, BF16 boundaries, RMSNorm reduction/rounding,
zero/saturation behavior, CUDA-graph legality, and tensor-parallel ownership.

Produce either:

- one concrete source-level decomposition with a CPU/reference fragment
  oracle, exact indexing/layout evidence, and an H200 exact-consumer contract
  that measures the unchanged materialized control against the candidate; or
- a typed analytical negative proving all three legal decompositions are
  dominated or cannot preserve the pinned semantics.

Write `MECHANISM_TERMINAL.json` last. Do not claim a bench, invoke CUDA,
reserve spend, inspect the norm execution project or R5, or mutate provider
lifecycle. A GPU contract is a later director decision, not authority.

## Decision rule

Promote only a source-level candidate whose physical bound remains positive
after all synchronization, partial-statistic, residual-output, and reread
traffic and whose oracle reaches the exact pinned consumer. Otherwise close
only these down-projection/residual/normalization decompositions and preserve
the quantitative negative.

## Budgets

- Wall clock: 75 minutes.
- GPU/CUDA: zero.
- Spend: `$0`.
- Storage: 2 GiB.
