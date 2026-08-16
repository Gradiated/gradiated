# Hierarchical tied-head co-design

## Question

Can an executable coarse-to-fine tied vocabulary head preserve the full
262,144-token output domain while avoiding enough of the compulsory
`5376 × 262144` logit work to reduce the locked exact-c32 service bound from
`0.625149101968745` to at most `0.500119281574996 s/request`, after all
routing and runtime overhead?

This is an exploration-phase physical discriminator. It may intentionally
change model semantics, but it is not permission to delete vocabulary rows,
reduce the output domain, or claim quality.

## Why this matters

Gemma 4 has a tied 262,144-row embedding/output matrix and the campaign
workload emits 358 tokens per request. The vocabulary head is therefore a
compulsory decode/verification consumer and is materially distinct from the
completed prompt-state compaction lineage. A hierarchical head can keep every
token reachable while using a small coarse score to route each hidden state
to a bounded set of layout-resident fine rows.

The completed prompt-state merge is preserved separately at
`../gemma4_prompt_token_compaction_codesign/PROMPT_STATE_MERGE_PHYSICAL_SCREEN.json`
(SHA-256 `fc87cbfcb3380d4d039f553687e58d5967ace2dd8e4ecc76f97cbe0a2cedbec8`).
Do not stack or transfer its savings into this discriminator.

## Bound evidence

- Exact checkpoint identity:
  `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Exact geometry:
  `../gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json`
  (SHA-256
  `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`);
  `text_config.hidden_size=5376`, `text_config.vocab_size=262144`, and
  `tie_word_embeddings=true`.
- Exact-c32 trace:
  `../gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/trace/exact_c32_profile.trace.json.gz`
  (SHA-256
  `37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b`).
- Pinned runtime source identity is commit
  `28b095c01005d4a3a2a5b637b7d028b07fba31b2`.
- Workload: 32 concurrent requests, 4,214 prompt tokens and 358 output
  tokens per request, with the locked qualified denominator and target above.

## Scope

Run a zero-provider-spend, source-and-physical-cost discriminator:

1. Attribute the existing trace's vocabulary-head/logits work through runtime
   scopes, CUDA correlations, exact shapes, or another falsifiable join. If
   head cost cannot be separated credibly, return typed `none`; do not infer
   it from peak FLOPS.
2. Design a learned coarse-to-fine head in which all 262,144 tied token rows
   remain stored and every token is reachable through at least one coarse
   route. The route may partition or overlap token groups, but it may not
   remove rows or count a smaller vocabulary as the intervention.
3. Implement the production data path from the model hidden-state consumer
   through coarse scoring, route selection, layout-resident or explicitly
   gathered fine-row evaluation, logit softcap, scatter/index semantics, and
   the actual sampler/logits-processor boundary. Metadata alone, a standalone
   selector, or arithmetic without the consumer is not source-complete.
4. Charge coarse projection, route top-k, token-row access or repacking,
   grouped/ragged GEMM inefficiency, softcap, sampling, graph variants,
   synchronization, fallback, and any full-head verification needed for the
   proposed semantics. Credit no quality, cache, allocator, batching, or
   unrelated kernel savings.
5. Report sensitivity to cluster count, selected token rows, routing overhead,
   and conservative non-scaling floors. The candidate must reach
   `0.500119281574996 s/request` after the full envelope.

Do not download checkpoint bytes, claim a GPU, contact a provider, train a
model, or run broad market research. Leave a later checkpoint recovery,
distillation, GPQA-Diamond, TauBench, tool-call validation, and target-GPU
measurement explicit.

## Success and invalidity

A physical candidate requires all of:

- every vocabulary token remains stored and mechanically reachable;
- the implemented source reaches the real logits/sampler consumer;
- the cost bound is exact-geometry and trace-backed;
- all routing, fine-row, softcap, sampling, fallback, and runtime overhead is
  charged; and
- conservative service time is at most
  `0.500119281574996 s/request`.

Classify typed `none` if the target requires deleting vocabulary rows,
reducing token reachability, assuming a free gather/repack, transferring
unmatched hardware throughput, omitting the consumer path, or exceeding the
target after overhead. A possible future training recipe cannot qualify an
invalid current mechanism.

## Terminal

Write `HIERARCHICAL_TIED_HEAD_PHYSICAL_SCREEN.json` as exactly one of:

- `source_complete_physical_candidate`, with bound input identities, complete
  route and consumer source identities, reachability proof, trace attribution,
  physical accounting, sensitivities, limitations, and the separate quality
  recovery path; or
- `typed_none`, with the strongest attempted design and the first binding,
  source, physical, or target failure.

