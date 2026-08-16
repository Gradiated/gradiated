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

## Offline integration budget and prohibitions (completed phase)

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

## 2026-07-28 direct SM89 component phase

New campaign authority reopens this same scientific question. The offline
terminal is preserved at
`L40S_DUAL_KV4_ALLOCATOR_0953_OFFLINE_TERMINAL.json`
(`sha256 e98777580a46ef458e1ea704ceea6fc827030150fe4efa8e67ef380e99fd0090`);
do not regenerate it or change either representation. Its positive memory
interval is necessary but not sufficient: local and global complete
producer-plus-consumer timings, compiled resources, integration overhead, and
the exact all-E5M2 L40S control remain unmeasured.

Use `$kernel-research` to implement one lifecycle-pure, checkpoint-free SM89
program that:

- measures current-runtime all-E5M2 pack plus paged attention against the
  unchanged local D256 KV4-plus-four-outlier producer and fused consumer;
- independently measures that same comparator against the unchanged global
  D512 recent-1024-E5M2/old-KV4-plus-eight-outlier producer and mixed-tier
  online-softmax consumer;
- binds c32, 358 decode steps, the exact local/global layer counts and head
  geometry, page size one, E5M2 scale semantics, padded no-op rows, warmups,
  repeats, and complete-output correctness/error evidence;
- synchronizes after each arm's first untimed invocation and persists an
  arm-specific completion marker before any timing, so a CUDA fault is
  attributable;
- reports warm timing distributions, registers, spills, shared memory,
  occupancy, and the measured terms in the terminal's complete-request
  inequality without inventing endpoint overhead.

Reuse the proven repair-aware lifecycle mechanics in
`../gemma4_l40s_kv4_outlier_sm89_component/l40s_component_owner.py`, including
resident-image detection before any pull. Hash-bind the new combined runner,
packet, manifest, and bounded detached owner in
`L40S_DUAL_KV4_SM89_COMPONENT_READY.json`. The first target-GPU call is the
discovery audit; ordinary compile, API, layout, transfer, or retrieval defects
remain repairable on the same mutable claim while the scientific arms are
unconsumed and the absolute window still fits.

The requested cumulative project authority is `$1.50`. A later director may
create one L40S only after the exact reservation and readiness artifact are
durable. The planned provider lifecycle is at most 90 minutes at the latest
measured `$0.8629833/hour`, or `$1.29447495`, including cold image setup,
compile, the two paired component measurements, repair margin, terminal
retrieval, release, deletion, and cleanup verification. Do not stage or read a
checkpoint, start a model server, run an endpoint, sweep parameters, or claim
the campaign objective from components. Promote to the existing fixed-`0.953`
c32 endpoint command only after a later director consumes complete positive
component evidence.

## 2026-07-28 staged-E5M2 stock-consumer phase

Attempt 2 is a valid consumed component sample and closes the fixed custom
fused-attention implementation. The local candidate was about `11.66x`
slower than its all-E5M2 comparator with relative-L2 error `0.150925`; the
global candidate was about `39.78x` slower with relative-L2 error `0.999379`.
Do not replay, tune, or reinterpret that sample.

The positive memory ledger leaves one materially different consumer question:
can the unchanged fixed local/global KV4 payloads be decoded into a bounded
E5M2 scratch workspace and then consumed by the already-fast current-runtime
E5M2 paged-attention path? This separates representation capacity from the
failed custom attention implementation.

Consume
`DIRECTOR_DUAL_KV4_STAGED_E5M2_CONSUMER_BINDING_20260728T0916Z.json` and use
`$kernel-research`. First spend at most ten wall-clock minutes offline to
hash-bind one lifecycle-pure runner and repair-aware owner. The runner must
measure both exact complete producer-to-stock-consumer pairs, attribute pack,
decode, attention, and complete time, preserve the bound numerical oracle,
and prove peak scratch ownership against the existing physical margin.
Persist `L40S_DUAL_KV4_STAGED_E5M2_SM89_READY.json` with one exact later
detached command or typed `none`.

Do not claim the bench during offline implementation. Do not change either
representation, workload, runtime, allocator split, or layer placement; do
not sweep, stage a checkpoint, start a model server, run an endpoint, or
replay attempt 2. A later director may bind at most one new paired component
sample on the retained L40S for at most 1,500 seconds and must release by
`2026-07-28T09:53:30Z`.
