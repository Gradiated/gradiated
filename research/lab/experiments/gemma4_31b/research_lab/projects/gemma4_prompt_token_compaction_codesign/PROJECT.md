# Gemma 4 prompt-token compaction codesign

## Question

Can an early-layer, request-local prompt-state compaction path merge every
input token into retained or summary states while reducing the actual Gemma 4
c32 prefill GEMM rows, attention pairs, KV writes, and later decode KV reads
enough to move the qualified
`0.625149101968745 s/request` service time to the locked
`0.500119281574996 s/request` target after scoring, compaction, graph, and
state-management overhead?

This is an information-carrying representation and model/runtime co-design
proxy. It is independent of the out-of-scope conditional-depth bound: every
transformer layer remains active, while earlier token states are explicitly
merged into a smaller set of later states and KV entries.

## Bound evidence and scope

- Model: `google/gemma-4-31B-it` at revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Workload: text-only, default non-reasoning c32 traffic with 4,214 prompt
  tokens, 535 shared-prefix tokens, and 358 output tokens per request.
- Qualified baseline: `0.625149101968745 s/request`.
- Locked target: `0.500119281574996 s/request`.
- Exact model geometry:
  `../gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json`,
  SHA-256
  `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`.
- Trace-backed layer and attention reconstruction:
  `../gemma4_hybrid_attention_placement_codesign/PLACEMENT_SIMULATION_RESULT.json`,
  SHA-256
  `2af53085953393785204eafb2c2dd0e9d335805f8a8e5963ae46fb57ed99e40b`.
- Exact c32 trace:
  `../gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/trace/exact_c32_profile.trace.json.gz`,
  SHA-256
  `37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b`.

The prompt bytes and hidden states are not locally retained. Therefore this
project may establish or reject only the physical mechanism and executable
runtime path; it may not estimate semantic quality from invented token
importance scores.

Pure token deletion is forbidden. A candidate must define a source-complete
merge, summary, or reconstructable state transformation in which every input
token contributes to retained downstream state. A speedup that merely tracks
discarded prompt capacity is out of scope, just like blunt layer deletion.

## Immediate evidence path

1. Reconstruct non-overlapping prefill, verification/decode, attention,
   FP8-linear, KV, and fixed residual costs from the bound artifacts.
2. Evaluate a small set of executable schedules that merge token states after
   an early block boundary into explicit summary budgets. Include a
   no-compaction control and preserve shared-prefix, recent, special, and
   tool-format states where merging would violate serving semantics.
3. Account for merge/scorer work, summary construction, gather and scatter,
   ragged batching or padding, RoPE positions, causal ordering, request
   ownership, KV allocation, graph variants, synchronization, and any later
   work that does not shrink with token count.
4. Inspect the pinned Gemma/SGLang source path and implement the smallest
   source-complete reference intervention or patch from the token-state merge
   producer through the first later-layer attention/linear consumers and KV
   allocation. A mask that retains padded GEMM rows or full attention/KV work,
   or a selector that simply drops unchosen tokens, is negative.
5. Report the earliest compaction layer, retained prompt-token fraction,
   exact work removed by phase, conservative service-time bound after all
   overhead, KV-capacity effect, state-contribution invariant, and sensitivity
   to batch fragmentation. Preserve a later quality-recovery route using
   distillation or continued training plus exact GPQA-Diamond, TauBench,
   long-context, tool-use, and formatting gates.

The researcher may choose the token-scoring mechanism, but the physical
terminal must not depend on unmeasured scoring accuracy.

## Invalid selector attempt

`PROMPT_TOKEN_COMPACTION_PHYSICAL_SCREEN.json` (SHA-256
`42006d1e9bfe3d31fdc53dffa7534c773e65adc36305574bf176a044514d49a5`)
is preserved as an invalid attempt. It stable-selects 1,152 existing token
slots after layer 5; the other 3,062 prompt tokens do not contribute to late
state through a merge, summary, or reconstruction path. Its analytical
`0.49570146543245547 s/request` bound describes forbidden token deletion, not
the admitted mechanism, and must not be relabeled or overwritten.

The next implementation must replace that selector-only boundary with an
actual state transformation. For example, fixed causal segments may produce
weighted summary states alongside protected tokens, but every prompt token
must have a mechanically checked contribution to one retained state. Charge
the complete reduction, normalization, weighting, summary-position/causal
metadata, movement, and synchronization path against the service bound.

## Terminal

Write `PROMPT_STATE_MERGE_PHYSICAL_SCREEN.json` as exactly one of:

- `source_complete_physical_candidate`: a source-complete information-carrying
  state-compaction path demonstrably shrinks the counted downstream tensor/KV
  work, proves every prompt token contributes to retained or summary state,
  and has a
  conservative bound at or below `0.500119281574996 s/request` after all
  scorer, movement, graph, synchronization, and fixed residual costs; or
- `typed_none`: the prefill/decode attribution, required keep fraction,
  runtime state semantics, fragmentation, or overhead cannot meet the locked
  target, with the strongest attainable physical bound preserved.

A nominal token-count or FLOP reduction, pure token deletion, generic
token-pruning literature review, unbound mask, or semantic-quality claim is
not a terminal. A positive terminal remains quality-unqualified and
unmeasured until separately authorized checkpoint recovery and GPU/quality
evaluation.

## Budgets

- Wall clock: 150 minutes.
- Compute: at most 12 local CPU-hours; zero accelerator compute.
- Storage: at most 4 GiB of new durable artifacts.
- Provider spend: `$0.00`.
- Checkpoint download, provider contact or mutation, and GPU claims are
  forbidden.
