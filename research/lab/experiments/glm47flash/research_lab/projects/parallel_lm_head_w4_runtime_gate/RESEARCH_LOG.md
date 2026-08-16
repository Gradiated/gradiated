# Research log

## 2026-07-16 — Director opening handoff

- Reuse the proven exact head pack/oracle and test only one minimal `ParallelLMHead` binding to the existing stock SM89 Marlin operation.
- Preserve tensor-parallel logits and sampler contracts; close on any custom kernel, broad loader rewrite, silent key drop, or non-head change.
- A `$0` pass nominates only the unresolved M16 component measurement at the existing `3.407616x` threshold; it is not endpoint evidence.

## 2026-07-16 — Superseded by the combined endpoint

The campaign pivot makes a head-only runtime gate duplicate work: `full47_head_shared_w4_c32` must already bind the same packed head through load, tensor-parallel logits, sampler, and oracle contracts. Preserve this project's exact pack/oracle as an input, but perform no independent implementation, provider preparation, or spend. The head-only `3.407616x` component threshold does not decide the combined candidate.
