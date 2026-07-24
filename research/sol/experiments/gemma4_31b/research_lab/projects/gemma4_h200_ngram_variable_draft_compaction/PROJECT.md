# NGRAM variable-draft target compaction

## Question

Can the native NGRAM producer compact each verification batch to real tree
nodes before target forward, then remap logits and KV ownership exactly,
reducing padded target work without changing drafts, acceptance, or served
tokens?

## Evidence and mechanism

The pinned producer currently asserts
`total_draft_token_num == batch_size * 12`. `NgramVerifyInput` allocates cache
slots, positions, tree masks, `qo_indptr`, logits, and acceptance tensors at
that fixed width. In 54 persisted verification events, the nonzero draft
prefix histogram was `{1:15, 2:1, 4:1, 6:1, 8:1, 9:1, 12:34}`: mean `8.3704`
real-looking draft nodes and `30.25%` padded positions. The acceptance
histogram was `{1:18, 2:5, 4:1, 6:1, 8:1, 12:28}`.

The exact repaired c32 trace attributed `62.66%` of its window to target
attention and also paid target MLP, FP8-linear, LM-head, KV-allocation, and
sampling work per fixed query position. M16 and M32 attention tiles are closed:
both produced the same sliding numerical miss. Compaction instead changes the
producer/consumer work set while retaining the stock M64 attention arithmetic.

## Experiment

Use `$kernel-research`. Bind the C++ corpus output, tree mask, retrieve graph,
`NGRAMWorker._prepare_draft_tokens`,
`NgramVerifyInput.prepare_for_verify`,
`generate_attn_arg_prefill`, target logits, acceptance, cache freeing, and
request-result consumers. Do not infer validity from token ID zero: establish
the official valid-node invariant from the producer mask/retrieve structure.

Implement exactly one variable-length representation carrying per-request
valid draft lengths. Compact draft tokens, positions, masks, cache slots,
`qo_indptr`, and target-forward rows; after target logits, remap acceptance,
accepted KV locations, cache eviction, usage, and request ownership to the
unchanged request-major semantics. Preserve stock `BLOCK_M=64`, M64 numerical
arithmetic, BF16 activations, FP8-E5M2 page-1 KV, 32/16 GQA heads, head
dimension 256, hybrid 50-local/10-global attention, TP1, CUDA streams, and
fallback behavior.

On warm bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`, make the first target
GPU call a fresh-process exact-producer/consumer smoke. Then run a compact
component over all-one, persisted mixed, and all-twelve valid-node batches.
Require exact target logits/accepted IDs, cache ownership and eviction,
positions, finish reason, usage, and full output consumption against the
fixed-width control. Benchmark warm profiler-off and collect only query-row
count, target-forward kernel time, allocated/freed KV slots, launch/grid
geometry, and compiled resources needed to prove the causal change.

Only a correct component with fewer target rows and a positive whole-request
bound may admit one matched c32 control/candidate endpoint pair. Preserve the
qualified NGRAM launch and exact request bytes. No quality replay, attention
tile, draft-depth/settings, corpus, concurrency, sampling, or backend sweep is
allowed. Keep ordinary source/API/retrieval repairs in one claim with a
detached durable owner.

## Decision

Retain only if the official producer invariant proves real padding, every
component boundary is exact, the endpoint completes 32/32 with identical
served semantics, and measured target-row removal explains a positive service
and cost effect. A false padding premise, ownership/cache mismatch, graph or
dynamic-shape cost that removes the gain, or non-positive endpoint closes this
single compaction realization.

## Resources

- Priority: `6990`
- Researcher profile: `deep`
- Authorized cumulative spend: `$10`
- Compute: retained H200, at most 180 claimed GPU-minutes
- Wall clock: release by `2026-07-24T16:45:00Z`
- Storage: at most 14 GiB of new artifacts
- Provider mutation: forbidden

