# Fixed-c48 dual-KV L40S saturation geometry

## Question

Does the source-complete dual-KV representation make one fixed c48 workload
physically admissible and runtime-reachable on a single L40S at
`--mem-fraction-static 0.953`, with a price-normalized path that is materially
different from the live exact-c32 component?

## Why this matters

The dual-KV terminal removes enough cache state to leave
`1,579,875,259..2,547,378,835` bytes of conservative physical margin at c32.
The campaign permits latency-for-cost tradeoffs for background traffic, so the
memory saving is valuable not only as a c32 placement mechanism but also if it
admits more concurrent useful work. One fixed c48 geometry is the shortest
non-sweep test of that capacity translation. Historical H200 c48 behavior does
not transfer to this L40S representation, runtime, or memory ownership.

This project is independent of the live c32 claim. Its immediate result is an
offline physical/runtime/economic discriminator, not a readiness artifact and
not permission to touch the shared bench.

## Bound evidence and identities

- Campaign target: `CAMPAIGN.md`, including the fixed
  `0.625149101968745 s/request` qualified denominator,
  `0.500119281574996 s/request` H200 target, and approximately
  `$0.109725/M` total-token planning target.
- Dual-KV physical and source terminal:
  `../gemma4_l40s_dual_kv4_allocator_0953_integration/L40S_DUAL_KV4_ALLOCATOR_0953_OFFLINE_TERMINAL.json`
  (`e98777580a46ef458e1ea704ceea6fc827030150fe4efa8e67ef380e99fd0090`).
- Dual-KV packet and exact consumers:
  `../gemma4_l40s_dual_kv4_allocator_0953_integration/L40S_DUAL_KV4_SM89_PACKET_MANIFEST.json`
  (`2f2e4f4bd1f0a178c77bf17a7834dad5f3920eaa63820982b4afa2e28182e5bb`).
- Model: `google/gemma-4-31B-it` at
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang commit
  `c6a6200a1a778a799ba61c395ac292317f01ebc9` and image
  `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Representation: 50 local D256 group-64 KV4-plus-four-outlier layers and
  10 global D512 recent-1024-E5M2/old-group-64-KV4-plus-eight-outlier layers,
  page size 1.
- Workload: exactly 48 concurrent requests, each with the campaign's 4,214
  prompt and 358 output tokens, text-only non-reasoning mode. Do not sweep
  concurrency.
- Target accelerator: one NVIDIA L40S SM89 at the sole allocator split
  `0.953`. Use the shared accelerator and price inventories for stable chip
  and production-rate facts.

## Immediate research contract

Use `$kernel-research`. Within 90 wall-clock minutes:

1. Reconstruct the non-double-counted c48 physical/static/dynamic memory
   ledger from the exact c32 ownership model. Show every concurrency-scaled
   and shared term and identify allocator rounding, graph pools, request/token
   pools, page tables, and producer/consumer scratch ownership.
2. Trace the pinned SGLang scheduler, memory-pool, batch construction, and
   CUDA-graph capture path that would admit exactly c48. Identify the minimum
   current-runtime configuration or source composition; do not infer support
   from a CLI flag.
3. Derive the exact c48 production-cost hurdle from the campaign denominator,
   token accounting, utilization assumption, and current committed L40S
   planning rate. Keep execution time symbolic; do not transfer c32, H200, or
   RTX throughput.
4. Implement only the smallest offline launcher/workload/accounting bytes
   needed to make a later single c32-versus-c48 saturation measurement
   reproducible if the physical and runtime gates pass.
5. Persist
   `L40S_DUAL_KV4_C48_SATURATION_OFFLINE_TERMINAL.json` with direct hashes,
   raw ledgers, source symbols, the exact workload identity, focused
   ownership/rounding/graph checks, the symbolic terminal inequality, and
   either one real later command or typed `none`.

## Prohibitions

- Do not inspect, claim, heartbeat, SSH to, or otherwise interact with the
  live c32 L40S bench or its owner/artifacts.
- Do not use provider APIs, credentials, endpoints, checkpoint shards, CUDA,
  or GPU execution.
- Do not change either KV representation, the allocator split, model,
  runtime, token workload, or c48 concurrency.
- Do not sweep batch size, graph sizes, memory fractions, compiler settings,
  kernels, or placement.
- Do not infer performance from memory fit, hardware specifications, c32
  components, H200 behavior, or RTX pricing.

## Portfolio-changing result

- **Positive conditional lane:** exact c48 fits conservatively, the pinned
  runtime path is source-complete, and a measured later c32-versus-c48 command
  plus price-normalized inequality are explicit. A later director may queue
  that one discriminator only after the live component releases and its
  result keeps dual-KV useful.
- **Typed none:** c48 cannot fit, runtime ownership cannot preserve the fixed
  semantics, or even the candidate-favorable economic bound cannot reach the
  campaign target. Close only fixed-c48 saturation, not dual-KV or alternative
  capacity geometries.
