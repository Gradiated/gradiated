# Research log

## 2026-07-26T09:31:53Z — information-carrying prompt-state discriminator

**Question.** Can an early-layer prompt-state merge move the qualified
`0.625149101968745 s/request` exact c32 result to the locked
`0.500119281574996 s/request` target while every input token contributes to
downstream state?

**Action.** The first selector-only branch was invalidated by the amended
contract. Replaced it in the same project with pinned SGLang model/runner
patches plus an executable merge and compact-KV-view path. The candidate runs
layers 0-5 on all 4,214 prompt tokens, preserves 535 shared-prefix and 384
recent states plus configured special/tool states, and maps every other input
exactly once into a nonempty, contiguous, hidden-RMS-weighted summary. The
fixed output is 1,152 causally ordered singleton/summary states. A compact
request-to-token view uses each state's final contributor slot for later KV
writes and decode/verification reads; original slots remain allocator-owned
for safe early-layer state and normal cleanup.

The invalid selector's original bytes were already overwritten by the
same-project repair before the director invalidation became visible. The
director record in `STATUS.json` preserves its path, SHA-256
`42006d1e9bfe3d31fdc53dffa7534c773e65adc36305574bf176a044514d49a5`,
classification, reported bound, and causal reason; it does not falsely claim
the bytes remain present.

**Evidence.**

- Measured/source-bound: exact c32 evidence attributes
  `0.1859440808124998 s/request` to prefill attention plus FP8 linears and
  `0.11386745088915105 s/request` to the conservative 33.3125-pass target
  verification reconstruction.
- Derived: with 10% non-scaling floors, the candidate retains
  `0.06455696554899805 s/request` of counted prefill and
  `0.0938069296163633 s/request` of counted verification work, saving
  `0.1414476365362895 s/request`.
- Conservative bound: holding `0.3253375702670941 s/request` fixed and adding
  `0.015 s/request` for scoring, partitioning, weighted summaries, movement,
  KV-map/metadata switching, graph shape, synchronization, and fragmentation
  yields `0.49870146543245547 s/request`, `0.0014178161425404956` below target.
- Exact physical removal: 5,291,136 downstream c32 GEMM rows, 5,291,136 late
  KV writes, 215,048,853 late prefill attention pairs/request, and 10,582,272
  global verification key positions/cycle. Ordinary decode, allocator
  capacity, and concurrency receive zero timing credit.
- Contribution invariant: five behavioral/source-binding tests prove all
  4,214 input indices occur exactly once across 1,152 singleton/summary
  groups, protected states remain singleton, groups are nonempty and causally
  ordered, protected overflow fails closed, and first reference late
  linear/attention/KV consumers receive exactly 1,152 states/slots.
- Sensitivity: 1,184 output states bind to
  `0.4999723892806893 s/request`; 1,200 miss at
  `0.5006094931926245`. The 1,152-state schedule tolerates at most
  `0.01641781614254051 s/request` total incremental overhead.

**Interpretation.** `PROMPT_STATE_MERGE_PHYSICAL_SCREEN.json` is
`source_complete_physical_candidate`, SHA-256
`fc87cbfcb3380d4d039f553687e58d5967ace2dd8e4ecc76f97cbe0a2cedbec8`.
This is an intentionally semantics-changing, quality-unqualified physical
proxy, not a GPU measurement or accuracy claim. The candidate uses one full
134,848-state c32 prefill cohort; fit and overhead remain analytical.

**Next move.** Preserve the merge candidate and the director's recorded
selector invalidation. Reopen only with separate authority for checkpoint
recovery, target-GPU execution, merge-quality/overflow measurement,
distillation or continued training, and exact GPQA-Diamond, TauBench,
long-context, tool-use, formatting, and endpoint gates. Do not download the
checkpoint, claim a GPU, or contact a provider under this project.
