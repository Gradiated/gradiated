# L40S tiered global KV4-outlier cache

## Question

Can one fixed, source-complete global-attention cache keep the most recent
1,024 tokens in E5M2 while representing older history as group-64 signed KV4
plus eight deterministic E5M2 residual outliers per D512 K/V vector, reducing
L40S residency with a credible numerical and execution path?

## Why this changes the portfolio

The exact host-prefetch terminal proves that relocating unchanged global E5M2
history cannot work: its compulsory decode H2D floor is
`1.797792871875 s/request`, already above the entire price-normalized
`1.4776251501079425 s/request` boundary. The global cache must remove old
history bytes rather than move them.

The active local-KV component covers D256 sliding-window attention only. This
project asks a different question at the D512 full-history boundary. A fixed
recent-high-precision/old-low-bit split may reduce the `5,311,979,520`-byte
global pool while protecting the tokens most likely to dominate the next
attention step. A source-complete negative would prevent another paid global
KV attempt; a positive representation and complete bound would create a later
exact SM89 consumer candidate.

## Fixed scope

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`
- Runtime: official SGLang commit
  `c6a6200a1a778a799ba61c395ac292317f01ebc9`
- Exact global geometry: 10 layers, 4 KV heads, D512, page size 1, c32,
  4,214 prompt tokens, and 358 output tokens
- Recent tier: the newest 1,024 logical tokens remain unchanged E5M2
- Old tier: group-64 signed KV4, eight BF16 scales, and eight deterministic
  E5M2 residual outliers per D512 K or V vector
- Consumer: one exact online-softmax pass across both tiers; no dequantized
  cache or output intermediate
- Global page ownership and request mapping remain unchanged

Bind the model/workload identities from:

- `../gemma4_l40s_global_kv_host_prefetch/L40S_GLOBAL_KV_HOST_PREFETCH_OFFLINE_TERMINAL.json`
- `../gemma4_l40s_local_kv4_outlier_codesign/L40S_LOCAL_KV4_OUTLIER_OFFLINE_TERMINAL.json`

Do not read checkpoint shards or transfer numerical claims from D256 to D512.

## Immediate experiment

Within 90 wall-clock minutes, use `$kernel-research` to implement:

1. a deterministic D512 producer and high-precision reference for the fixed
   recent/old representation;
2. one source-complete SM89 paged-attention consumer that traverses E5M2 recent
   pages and corrected KV4 old pages in a single exact online-softmax
   reduction;
3. focused CPU checks for scale and nibble conventions, saturation, outlier
   uniqueness/order, empty-old-tier, the 1,023/1,024/1,025 transitions,
   request isolation, padded rows, and full-history positions 4,214 and 4,571;
4. exact cache bytes, metadata, producer/consumer work, compulsory reads,
   arithmetic intensity, grid-wave and resource bounds, plus the complete
   L40S allocator and locked-request implications; and
5. `L40S_GLOBAL_TIERED_KV4_OUTLIER_OFFLINE_TERMINAL.json` with direct hashes,
   raw numerical evidence, complete uncertainty labels, and one real later
   SM89 component command or typed none.

Use the current runtime's E5M2 global consumer as the later hardware
comparator. The implementation must reach its first decision-bearing consumer;
an encoder, memory calculation, or standalone decoder is not source-complete.

## Decision contract

Pass the offline representation only if:

- every output is finite and structurally valid;
- the corrected full-history proxy reaches relative L2 at most `0.08` and
  cosine at least `0.995` at both bound query positions;
- the recent/old transition and request/page ownership checks pass;
- the complete resident-byte bound materially improves the fixed L40S
  allocator margin; and
- a real current-runtime SM89 component can compare the full producer plus
  mixed-tier consumer against E5M2 without changing semantics or workload.

These synthetic numerical checks are an early discriminator, not production
quality evidence. Return typed none if any condition fails.

## Resources and prohibitions

- Spend: `$0`
- Wall clock: 90 minutes
- Researcher profile: `deep`

Do not claim a GPU, use SSH/provider APIs/endpoints, run CUDA, read checkpoint
shards, train, change the 1,024-token split, sweep precision/group size/outlier
count, alter global-layer placement, compress recent tokens, reuse D256 error
as D512 evidence, or count dependent synchronization as saved.
