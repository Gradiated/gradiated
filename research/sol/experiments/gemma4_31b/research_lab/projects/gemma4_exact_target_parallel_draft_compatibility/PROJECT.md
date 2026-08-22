# Exact-target parallel-draft compatibility

## Question

Which currently available DFlash, EAGLE-3, Gemma assistant/MTP, or equivalent
parallel-draft path can produce decision-bearing accepted target tokens for the
exact `google/gemma-4-31B-it` revision
`b9ea41a2887d8607f594846523f94c6cc75ac8a4` without changing target semantics,
and what is the shortest source-complete component experiment for the campaign
c32 workload?

## Why it matters

The campaign needs roughly 20% service-time reduction from the fixed qualified
H200 result to reach the seed-frontier objective. Fixed PQ output-head
retrieval is now closed: its largest shortlist missed 168 stock candidates,
failed exact greedy agreement, and scanned codes far slower than the dense
reference. Exact-target parallel drafting is materially different: it reduces
target forwards only when accepted work is real, while preserving target
semantics.

## Scope and evidence

- Bind the exact target checkpoint, tokenizer, vocabulary, hybrid-attention
  geometry, KV-commit boundary, and campaign c32 request shape.
- Inspect current public model/revision identities and the pinned/current
  SGLang or vLLM consumer source only as needed.
- Compare DFlash, EAGLE-3, Gemma assistant/MTP, and one materially distinct
  public exact-target path when available.
- Trace one actual draft producer through target verification, acceptance, and
  KV commit. Source labels or checkpoint names alone are not compatibility.
- Prefer an existing runnable adapter. If none fits, localize the smallest
  incompatibility and select one implementable adapter or explicit falsifier.
- Do not train, claim a GPU, call `gpu_pool`, SSH, Docker, CUDA, endpoint
  traffic, or provider APIs in this project.

## Result that changes the portfolio

Within 45 minutes publish
`EXACT_TARGET_PARALLEL_DRAFT_COMPATIBILITY.json` with immutable identities,
exact symbols and tensor/token contracts, target-semantic invariants, current
runtime support, competing explanations, an executable CPU/source consumer
falsifier or source-complete adapter, and one typed `promote` or `close`
decision. Promotion must name the exact target-GPU component command and
acceptance/accepted-token-per-verifier-second evidence required next.
