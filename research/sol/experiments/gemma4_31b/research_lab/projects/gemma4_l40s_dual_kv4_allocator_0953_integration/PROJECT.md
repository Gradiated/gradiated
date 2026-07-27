# L40S dual-KV4 allocator 0.953 integration

## Question

Can the exact Gemma 4 c32 endpoint combine the fixed local D256
KV4-plus-four-outlier representation with the fixed global D512
recent-1024-E5M2/old-KV4-plus-eight-outlier representation under the sole
preregistered `--mem-fraction-static 0.953` split, with a source-complete
allocator-to-attention path and enough physical/dynamic margin to justify a
later endpoint?

## Why this matters

The local representation is source-complete and its exact SM89
producer-plus-consumer timing is currently in flight. The independent global
representation passed fresh D512 numerics and removed exactly
`1,589,350,756` bytes, but its unchanged-allocator endpoint remains
`2,428,118,480..3,395,622,056` bytes over physical L40S memory. The previous
fixed `0.953` local-only allocator analysis retained approximately
`2.114449 GiB` for observed dynamic state and had almost no static margin.
The new global saving materially changes that reliability boundary. The
decision now is the composed placement, not another representation or
allocator sweep.

## Authoritative evidence

- `../gemma4_l40s_kv4_outlier_sm89_component/L40S_KV4_OUTLIER_SM89_COMPONENT_READY.json`
  (`sha256 ac9ea0118c943f33b55cd4f99ce858f70eacba21e3f80f5e7f4d93be59a4043c`)
- `../gemma4_l40s_global_tiered_kv4_outlier/L40S_GLOBAL_TIERED_KV4_OUTLIER_OFFLINE_TERMINAL.json`
  (`sha256 46db0a82a29f1af4299f5e8a6af7ddaf8bf1c859f5c08c823e9bbfb9c4a79e83`)
- `../gemma4_l40s_local_kv4_outlier_codesign/L40S_LOCAL_KV4_OUTLIER_OFFLINE_TERMINAL.json`
  (`sha256 c0a732ef5cf42cb5744a19afab0fe2734ad37cbd5d720ebcc4a16e02a856cfc2`)
- `../../CAMPAIGN.md`, including the exact c32 workload, quality caveat,
  `0.500119281574996 s/request` retained-candidate objective, and
  `1.4776251501079425 s/request` single-L40S price-normalized boundary.

Mechanically verify these artifact identities before using their fields.
Do not assume the two byte savings are additive: reconstruct shared allocator,
directory, padding, graph, context, workspace, and fragmentation ownership
once.

## Fixed scope

Use `$kernel-research`. Bind current official SGLang commit
`c6a6200a1a778a799ba61c395ac292317f01ebc9`, Gemma revision
`b9ea41a2887d8607f594846523f94c6cc75ac8a4`, one NVIDIA L40S SM89, and the
exact c32 workload: 4,214 prompt tokens, 358 output tokens, page size one,
50 local D256 layers with a 1,024-token window, and 10 global D512
full-history layers.

Keep both representations unchanged:

- local: group-64 signed KV4, four BF16 scales and four deterministic E5M2
  residual outliers per D256 K/V vector;
- global: newest 1,024 tokens in E5M2, older history in group-64 signed KV4
  with eight BF16 scales and eight deterministic E5M2 residual outliers per
  D512 K/V vector.

Use only `--mem-fraction-static 0.953`. Reconstruct the complete physical
interval and the exact static/dynamic split, including all weights, scales,
both KV arenas, directories/free stacks, padding, context, graphs,
workspaces, scheduler metadata, allocator rounding, fragmentation, and
release/reuse ownership. Implement the minimum current-runtime integration
from allocation and producer routing through both real paged-attention
consumers. Preserve canonical request/page ownership and the exact five-local
/ one-global layer schedule.

Do not claim endpoint performance from offline source or separate numerical
passes. Carry the in-flight local component and unmeasured global component
as explicit conditional latency inputs, and derive the complete
`1.4776251501079425 s/request` acceptance inequality without inventing their
values.

## Budget and prohibitions

- Wall clock: 90 minutes.
- GPU/provider/endpoint/SSH/CUDA budget: zero.
- Storage: at most 2 GiB of new project-local artifacts; do not copy or read
  checkpoint shards.
- No sweep of allocator fractions, representations, recent-token cutoffs,
  outlier counts, groups, kernels, workload parameters, or layer placement.
- Do not contend with, inspect through SSH, or mutate the live local-component
  claim.
- Do not reopen output-head, QServe/W4/AWQ, host-prefetch, or fixed-E5M2
  mechanisms.

## Required terminal

Persist `L40S_DUAL_KV4_ALLOCATOR_0953_OFFLINE_TERMINAL.json` with:

- direct hashes of every authoritative input and changed source file;
- an exact non-double-counted memory ledger with lower/upper physical,
  static, and dynamic margins;
- producer, allocator, page/directory, transition, padding, release/reuse,
  and local/global consumer ownership contracts;
- focused offline checks at 1,023/1,024/1,025 tokens, padded rows, c1/c31/c32,
  prefill spill, maximum live rows, and page reuse;
- the complete conditional component and price-normalized request bound;
- source/compiler-resource expectations and the one predicted SM89 physical
  change for each consumer;
- a real later current-runtime command only if the combined endpoint is
  source-complete and memory-positive, otherwise typed `none`.

The result changes the portfolio if it proves the composed endpoint has a
positive complete memory interval and a narrow path from both component
results to a paid endpoint, or proves that even this fixed composition cannot
fit without another scientific mechanism.
