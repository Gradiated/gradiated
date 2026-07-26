# Gemma 4 MI355X tied-K/V projection reuse co-design

## Question

Can the exact Gemma 4 `attention_k_eq_v` contract eliminate the duplicated V
projection GEMM—computing the shared raw K/V projection once, then forking K
into its existing normalization/RoPE path and V into its unchanged value
path—while preserving exact model semantics and reducing the conservative
MI355X bound from `0.6000950932112802` to at most
`0.5910500600431771 s/request`?

## Why this is the next experiment

The completed AITER bridge is a source-complete later measurement candidate,
but contains no target timing. Another precision or support screen would not
add enough information. The pinned Gemma runtime instead exposes an exact
model-specific redundancy: with `attention_k_eq_v`, the loader clones K
weights into V, yet the packed QKV projection still emits separate equal raw
K and V columns. K is subsequently normalized and RoPE-transformed while V is
not, so the raw projection can be shared only before those downstream paths.

Across the exact geometry, the duplicated V slice is:

- sliding layers: `50 * 5,376 * 4,096 = 1,101,004,800` parameters;
- global layers: `10 * 5,376 * 2,048 = 110,100,480` parameters;
- total: `1,211,105,280` redundant executed projection weights.

That is about 4.12% of the `29,396,828,160` executed transformer-linear
parameters. The preserved MI355X screen needs only
`0.009045033168103123 s/request` improvement to clear the `$2.75/hour`
sensitivity. This is a semantic-preserving model/runtime intervention, not
capacity deletion: every Q, K, and V output remains present and the logical
weight tie is unchanged.

## Bound evidence

- Exact campaign identity and workload: `CAMPAIGN.md`.
- Baseline geometry, source path, and accounting:
  `../gemma4_mi355x_fp8_runtime_codesign/MI355X_FP8_RUNTIME_SCREEN.json`.
- Pinned runtime identities:
  `../gemma4_mi355x_fp8_runtime_codesign/SOURCE_BINDINGS.json`.
- Preserve the completed AITER bridge terminal and patch as an independent
  later measurement candidate; do not stack its unmeasured gain.

## Experiment contract

Use `$kernel-research` for the exact producer/consumer and gfx950 physical
analysis.

1. Rebind the pinned Gemma model/config/loader/attention sources and the exact
   checkpoint identity. Prove from source and streamed checkpoint metadata
   that `attention_k_eq_v` supplies identical raw K and V projection weights,
   input, scale, bias, and accumulation contract in all 50 sliding and 10
   global layers. Do not copy or download checkpoint bytes.
2. Preregister exactly one intervention: remove the duplicated V columns from
   the packed projection, compute Q plus one raw shared K/V slice, then fork
   that slice before K-only normalization/RoPE while preserving the original
   V layout consumed by hybrid attention.
3. Implement a project-local minimal patch against the pinned runtime. It
   must reach the real Gemma forward and AITER attention consumer at prefill,
   M32 decode, and M384 target verification for both head geometries. A
   tensor-only demonstration, post-RoPE alias, changed attention equation, or
   unreachable helper is invalid.
4. Build deterministic CPU-available fixtures for sliding/global shapes,
   padding, layouts, scale granularity, graph metadata, and fork ownership.
   Compare Q, post-transform K, V, and attention inputs against the stock
   path. Use a justified numerical envelope for changed GEMM packing; require
   finite outputs and localize any difference to the projection.
5. Charge reduced-QKV kernel efficiency, new shapes/tiles, raw-K/V copy or
   alias materialization, memory traffic, normalization/RoPE separation,
   metadata, launches, graph behavior, padding, fallback, load-time state,
   attention consumption, and unchanged request/service costs. Credit neither
   nominal parameter removal nor vendor peak throughput.
6. Emit `MI355X_TIED_KV_PROJECTION_REUSE_SCREEN.json` with source and patch
   hashes, exact logical and physical geometry, all fixture results, complete
   full-request accounting against the unstacked `0.6000950932112802`
   baseline, and one finite target-MI355X exact-consumer measurement program.
7. Classify as `source_complete_measurement_candidate` only if the real path
   is complete, every semantic and memory gate passes, and conservative
   evidence reaches at most `0.5910500600431771 s/request`. Otherwise emit
   typed `none`.

The candidate classification is not target timing, endpoint performance, or
quality evidence. Do not amend the existing paid MI355X baseline falsifier.

## Budgets and prohibited actions

- Wall clock: at most 75 minutes.
- Compute: local CPU only; no accelerator claim.
- Storage: at most 4 GiB of new project-local source, fixtures, and artifacts.
- Spend: `$0`.
- Do not copy or download the checkpoint.
- Do not contact a provider, use paid APIs, create resources, or mutate GPU
  inventory.
- Do not sweep packing, projection, alias, tile, or fallback policies.
- Do not stack AITER-bridge, batching, compression, prompt, attention, or
  output-head gains.
- Do not delete heads, layers, width, untied parameters, requests, or tokens.

## Portfolio-changing result

A valid source-complete candidate becomes a distinct exact-consumer arm for a
later compatible MI355X itinerary when durable authority exists. A typed
negative closes only this pre-normalization tied-K/V compute-reuse mechanism
and requires the next portfolio decision to change abstraction.
