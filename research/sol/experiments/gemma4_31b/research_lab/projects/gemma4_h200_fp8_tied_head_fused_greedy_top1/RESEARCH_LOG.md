# Research log

## 2026-07-23 — exact fused greedy component rejected

Question: can one fixed E4M3 `M<=32, K=5376, N=262144` head kernel emit
deterministic per-row partial top-1 pairs plus one device reduction faster than
the predecessor full BF16 logits, softcap, and greedy scan?

Action: snapshotted every hash-bound predecessor input project-locally, claimed
the retained H200, and ran a Triton `BM=16, BN=64, BK=64` implementation on the
captured real hidden rows for all padded M. The benchmark consumed the exact
BF16 embedding and predecessor per-tensor E4M3 weight/activation scales. Two
pre-science wiring failures (unsupported explicit activation padding and a
missing Triton constexpr) were repaired without changing the candidate. A
subsequent root-owned cache cleanup defect incorrectly released the safe bench;
`artifacts/INVALIDATED_PRE_SCIENCE_TERMINAL.json` preserves that invalidated
terminal. The same unconsumed candidate was restored to the retained bench and
invoked once scientifically.

Evidence (measured): every real-row token matched at M
`1,2,4,8,12,16,24,32`; all partial and final values were finite; three repeats
were deterministic; every captured graph replay matched; the BF16 embedding
was unchanged; and non-greedy plus logprob probes both returned full
`[M,262144]` BF16 logits with zero candidate calls. The fixed candidate was
slower at every shape: M1 `0.618752` versus `0.402768 ms`, M16 `0.617200`
versus `0.441184 ms`, and M32 `1.111776` versus `0.466080 ms`. The all-zero
tie discriminator also returned token 1 versus the required stock token 0.
Canonical evidence is
`artifacts/component-attempt1/COMPONENT_RESULT.json` (`c034bb97…`) and
`artifacts/FINAL_TERMINAL.json` (`5f66da05…`).

Interpretation (derived): the 4,096-vocabulary-tile grid gives up the library
GEMM's efficient scheduling even for one M tile. At M 24 and 32, `BM=16`
creates two M grids that each stream the approximately 1.409 GB E4M3 head,
matching the observed latency step from about `0.617` to `1.112 ms`. Reduced
output traffic cannot repay that duplicated weight traffic and scheduling
loss. This exact fixed decomposition is a component reject; the conditional
c32 endpoint was not run.

Next: close this candidate. A future project would need a materially different
single-pass library/CUTLASS epilogue that preserves cross-row weight reuse and
proves lowest-index ties; it must not replay this consumed arm.
