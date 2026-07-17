# Exact Gemma primary cache-trace contract

## Question

Can the campaign's exact 4,214-input / 358-output primary workload realize approximately 12.7% prompt-token cache reads through one deterministic, tokenizer-bound trace without accidentally sharing the suffix or overstating reuse at vLLM block boundaries?

## Decision relevance

The first H200 baseline program accidentally generated identical full prompts while claiming only a 535-token shared prefix. A corrected endpoint result is uninterpretable unless submitted identities, warmup/order, block alignment, cache-query/hit metrics, and the difference between intended shared tokens and realized cached tokens are explicit. Produce one reusable `$0` trace/validator packet for the exact checkpoint; do not modify or wait on the paid baseline project.

## Scope and method

- Bind `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4` and the verified tokenizer under `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint`.
- Inspect the pinned vLLM runtime/source or exact-image evidence already in the lab for prefix-cache block semantics and metrics. Do not transfer conclusions from a different runtime revision without labeling them.
- Construct deterministic c1/c4/c8/c16 request groups at exactly 4,214 input tokenizer IDs and 358 requested output tokens. Prove the common prefix length, distinct suffix hashes/IDs, pairwise longest-common-prefix distribution, request ordering/barriers, warmup semantics, and an unambiguous 10K/358 separate stream.
- Reconcile the target 12.7% token mix with cache block granularity. Distinguish intended common-token fraction, maximum cacheable block-aligned fraction, and the runtime metric needed to measure realized cache-read tokens. Do not claim exact realization from construction alone.
- Emit `TRACE_PACKET.json`, a small offline validator or fixtures, and `TRACE_TERMINAL.json` with a typed `pass` or `none`. The packet may nominate only content-bound runner inputs/assertions; it may not create a controller or provider resource.

## Stop rule

Stop after one validated trace packet, or return typed none if the available pinned runtime cannot expose realized cached-token accounting. Do not broaden into endpoint execution, quality testing, provider readiness, or a new runtime lineage.

## Budgets

- Wall clock: 25 minutes.
- Compute: 1 local CPU-hour; no GPU.
- Storage: 1 GiB project-local artifacts; no shared `/tmp`.
- Spend: `$0`; provider mutation forbidden.

## Handoff

Keep `RESEARCH_LOG.md` concise. Set `STATUS.json` to complete/terminal with the exact result and next action. The active H200 owner may consume the packet only if identities match and doing so neither delays launch nor weakens its own typed final-program gate.
