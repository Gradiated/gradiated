# Research log

## 2026-07-25T23:09:33Z — director admission

Admitted as the independent zero-GPU deep lane. The first terminal must decide
whether exact Gemma c32 FP8 gate/up–SwiGLU–down materialization and rounding
semantics justify one later H200 component discriminator. No GPU, compilation,
or provider mutation is authorized.

## 2026-07-25T23:21:52Z — source-complete causal screen returns typed none

Pinned SGLang source proves the exact boundary is BF16 gate/up output, FP32
GELU-tanh×up with one BF16 product rounding, then a two-pass row-wide BF16
amax/FP8 conversion before the unchanged down GEMM. The retained trace measures
3,660 activation launches at `0.215339387 s` and the sequence-joined down-input
quant family at `0.184573931 s` inside a `22.344871517 s` request window.

The smallest exact dataflow is one 256-thread CTA per row with a 43,008-byte
shared BF16 stage. It removes the activated global write, both quant global
reads, and one launch while preserving the BF16 rounding before amax. A
same-effective-bandwidth point model plus the larger full correlated launch
credit predicts `0.244711135 s` saved: `6.2622%` of the optimistic component
denominator and `1.0952%` of the request window. This is not a conservative
bound. It leaves only `0.021262420 s` request-gate margin and requires the new
shared-memory/reduction kernel to retain at least `89.5282%` of the current
pair's effective bandwidth, with no counter or candidate measurement bounding
barriers, staging, exact-M=32 occupancy, or integration cost.

Terminal: `typed_none`, reason
`conservative_whole_request_gate_not_supported`. No scientific sample,
compilation, GPU claim, provider mutation, or spend occurred. The reproducible
analysis is `analyze_swiglu_down_fusion.py`; the causal map is
`SWIGLU_DOWN_FUSION_CAUSAL_MAP.json`.

Two local tooling amendments were non-scientific: the accelerator inventory
CLI did not accept an attempted output-format flag, and the first analytical
script pass expected the CLI-normalized architecture object rather than the
raw inventory's profile reference. The invalid operations persisted no result;
only those parsing calls were corrected and rerun.
