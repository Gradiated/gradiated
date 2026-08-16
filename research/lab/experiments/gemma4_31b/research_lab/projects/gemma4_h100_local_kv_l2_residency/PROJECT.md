# H100 local-KV L2 residency mechanism

## Question

Can Gemma 4's five-local/one-global hybrid-attention cadence be mapped onto a
bounded H100 L2-resident local-KV working set that reduces non-overlapping HBM
traffic without changing attention semantics or request ownership?

## Why this matters

The campaign remains close to its sustainable cost frontier, and the exact
model repeatedly reads a 1,024-token sliding local window in five of every six
attention layers. H100 SXM has 50 MiB of last-level cache and 3,350 GB/s HBM
bandwidth. A source- and geometry-proven residency/layout intervention could
be a compact follow-up on the warm H100 after the endpoint, while a negative
working-set proof prevents another speculative GPU allocation.

## Bound evidence and source

- Exact model/runtime packet:
  `../gemma4_h100_v0515_ngram_price_normalized/packet/candidate-v0.5.15/`.
- Required source paths:
  `source/python/sglang/srt/models/gemma4_causal.py`,
  `source/python/sglang/srt/layers/attention/hybrid_attn_backend.py`, and
  `source/python/sglang/srt/layers/attention/triton_backend.py`.
- Exact request shapes:
  `inputs/requests.jsonl` and `inputs/exact_semantic_rows.jsonl`.
- Shared accelerator record:
  `../../../../../../factory/data/accelerator_inventory.json`,
  accelerator `nvidia-h100-sxm` (132 SMs, 50 MiB L2, 80 GB HBM3,
  3,350 GB/s).
- Packet manifest SHA-256:
  `8127631191fe1afc47e718502ff61980b1e51adb8ac43c2f28e140ff506173bd`.

## Scope

Reconstruct the exact local/global layer cadence, KV dtype/layout, page/block
ownership, request-slot mapping, and bytes touched per decode step. Build a
deterministic address/working-set model over representative bound request
rows. Compare the stock allocator/access order with one concrete
residency-aware layout or access schedule, including:

- hot local-KV bytes per active request and batch;
- whether the reusable set can fit the 50 MiB L2 after realistic contention;
- predicted HBM bytes and L2 reuse change, separated from global-attention and
  linear work;
- the precise producer, allocator, and consumer source boundary;
- semantics and lifecycle hazards for padded rows, request reuse, CUDA graphs,
  and five-local/one-global transitions; and
- one source-level patch plus a checkpoint-free exact-shape falsifier, or a
  typed `none` if the working set or source path defeats the mechanism.

Persist code, bound hashes, and `CAUSAL_RESULT.json`. Synthetic address traces
must be labeled synthetic; source and geometry findings should be labeled
derived. Do not claim endpoint speedup from a byte bound.

## Boundaries and budget

- CPU/source analysis only; no GPU, provider, SSH, or mutation of the current
  H100 bench.
- At most 90 CPU minutes, 4 GiB RAM, and 512 MiB of artifacts.
- Persist a typed result by `2026-07-25T11:55:00Z`.
- Do not replay any scientific arm.

## Portfolio-changing result

A source-complete candidate with a cache-fitting working set and material
non-overlapping HBM-byte bound becomes the first compatible warm-H100
follow-up after the direct endpoint. A typed `none` closes only this L2
residency/layout mechanism.
