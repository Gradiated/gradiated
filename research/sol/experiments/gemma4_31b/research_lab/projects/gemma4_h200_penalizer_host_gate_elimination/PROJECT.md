# Penalizer host-gate elimination on the retained H200

## Question

Can the exact v0.5.13 decode path preserve penalizer semantics while replacing the per-step device scalar read used by `penalizer_orchestrator.is_required` with host-maintained batch state, thereby removing the 358 measured 4-byte D2H predecessors and improving the exact c32 endpoint beyond the retained `0.6870190131 s/request` stack?

## Why it matters

The completed pinned-H2D intervention removed all 358 256-byte H2D copies as immediate predecessors of long synchronization, but all 387 long sync calls remained and 358 moved behind a 4-byte D2H readback. The source decision is driven by request sampling policy and batch membership, so a correctly maintained host predicate is a materially different scheduling intervention from changing token-transfer memory.

## Bound evidence and baseline

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, image `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Exact workload: 32 requests at concurrency 32, 4,214 prompt and 358 completion tokens/request, with 117,728 fresh and 17,120 cached prompt tokens total.
- Control: dynamic E4M3 linears, FP8 E5M2 KV, QKV epilogue, deferred local-KV commit, dynamic chunking at 2,048, plus the retained pinned/nonblocking penalty-token transfer. It measured `0.6870190130937459 s/request` with 32/32 valid rows.
- Mechanism evidence: `SYNC_COUNTER_DELTA.json` reports 387 long syncs in both arms; the candidate has zero 256-byte H2D immediate predecessors and 358 4-byte D2H immediate predecessors.

The authoritative file identities are in `EVIDENCE_BINDING.json`. Do not substitute another checkpoint, runtime, workload, or baseline.

## Scope

Use deep source/accelerator reasoning to identify the exact 4-byte read and maintain an equivalent host predicate at the smallest set of batch mutation points. Freeze one patch only. The predicate must never suppress an active penalty; validate mixed required/not-required requests and filter/merge transitions before timing. Then run exactly one profiler-off control/candidate c32 pair and the minimum trace needed to count 4-byte D2H predecessors and long syncs. Do not replay the pinned-H2D-only candidate, sweep flags, change sampling policy, or alter outputs.

## Resources and limits

- Reuse `h200-sync-linear-e00vhh6h29fj68x91g`; never create or destroy provider resources.
- Reuse its checkpoint, pinned image, build caches, and exact workload.
- Maximum three claimed GPU-hours, four wall-clock hours from first claim, 5 GiB retrieved artifacts, and `$16.00` cumulative authorization.
- Release warm for `gemma4_h200_local_attention_register_residency`.

## Decision rule

Require 32/32 complete sane rows, exact token/cache accounting, control/candidate feature parity, and explicit mixed-batch predicate tests. The causal prediction is 358→0 4-byte D2H predecessors without introducing a replacement host/device scalar read. Retain any reproducible simple endpoint gain without material downside; promote the stack only if it reaches `0.6381105231 s/request`. A semantic failure or no positive endpoint movement closes this exact host-gate mechanism.
