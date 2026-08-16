# Research log

No researcher result yet. Screen only the exact two-card RTX 4090 pipeline topology and its missing same-node economics; do not mutate a provider or repeat the general hardware survey.

## 2026-07-15 — Exact PP support, memory/PCIe bound, and economic close

**Question.** Can two same-node RTX 4090s run the exact current-AWQ GLM-4.7-Flash workload with layer PP below `$0.514/M` after lifecycle costs?

**Action.** Read the retained c16 control and saturation bound, parsed the content-addressed checkpoint headers, checked the shared SM89 inventory, inspected the pinned vLLM 0.15.0 model source, and refreshed only the bounded same-node market reference.

**Evidence.** [dual_rtx4090_pipeline_bound.json](dual_rtx4090_pipeline_bound.json) records the 23/24-layer splits, rank-local embedding/head placement, 512 MiB one-way c16 prefill boundary, 64 KiB decode boundary, and stage weight+KV budgets of 11.99–12.68 GiB. The exact class inherits `SupportsPP`; vLLM creates embeddings only on rank 0 and the LM head only on the last rank. Syaala’s current pricing page lists 2x RTX 4090 at `$1.48/hour` on RunPod and `$1.38/hour` on Vast.ai, but this is a market reference rather than a topology-matched written quote or committed rate.

**Interpretation.** Runtime support and raw memory capacity are not the blockers. The no-loss hurdle is 745–800 output tok/s at those pair rates, rising to 931–1,000 tok/s after the 20% lifecycle allowance; no exact-model PP result supports that floor, and the measured one-card c16 control is 535.286 tok/s. The 4090 route therefore does not jointly clear the campaign target and venue gate.

**Decision / next move.** Close dual-4090 pipeline placement with no paid measurement nomination. Retain A40 as the only conditional cheap-hardware lead. A future re-open requires an orderable same-node written rate at or below roughly `$1.00/hour` plus measured per-rank VRAM and PP throughput; it should then measure only throughput, per-rank peak VRAM, boundary/P2P telemetry, completion envelope, and interruption/reload accounting.
