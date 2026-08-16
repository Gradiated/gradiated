# Research log

## 2026-07-15 — Direct current-AWQ c16 dispatch

**Question.** Does the current content-addressed AWQ L40S c16 arm improve background output throughput by at least 5% over c8 or reach 397.279 output tok/s?

**Action.** Rechecked the current local AWQ revision, its four-shard manifest, and tokenizer bytes. The direct launcher's V21 tokenizer gate was stale (`19e773…`/`31a173…`) and would fail before vLLM; I rebound it to the verified current inputs (`353a3f…`/`b6b807…`, with unchanged template `d63ad…`) and added a focused regression test. The 21-test direct-launcher suite passed. A single authorized L40S dispatch then received an instance-create exit 1 even though Nebius created the named instance and disk.

**Evidence.** [events.jsonl](artifacts/nebius_current_awq_c16_direct_2026-07-15/events.jsonl) records the verified local model and generic create failure. [summary.json](artifacts/nebius_current_awq_c16_direct_2026-07-15/summary.json) and [orphan-cleanup.json](artifacts/nebius_current_awq_c16_direct_2026-07-15/orphan-cleanup.json) retain the terminal accounting and two-view cleanup: zero final instances/disks, 43.516 s exposure, and $0.010372718 derived cost. The launcher discarded provider stdout/stderr, so the exact provider cause is unobserved.

**Interpretation and next move.** No request, model-load, quality, telemetry, c8, or c16 data exists; the batching hypothesis remains untested. This route is paused rather than retried unchanged. A future owner should first use a launcher that retains typed create diagnostics (including stdout/stderr) and then select a fresh, current c8/c16 control/candidate session.

## 2026-07-15 — Current-AWQ c8/c16 frontier result

**Question.** Does c16 improve the current cache-off 8,192-input/1,024-output L40S background point over c8 by at least 5%, or reach $0.60/M output tokens?

**Action.** Ran one reconciled direct Nebius L40S session with the pinned current AWQ revision, vLLM 0.15.0, `num_kv_splits=4`, `max_num_seqs=16`, and c1/c8/c16. The session retained the provider create diagnostic, full checkpoint/model identity, raw profiles, metrics, semantic/quality diagnostics, GPU telemetry, content-addressed bundle, and cleanup evidence.

**Evidence.** [summary.json](artifacts/nebius_current_awq_c16_direct_2026-07-15-r2/summary.json) records 100% complete exact-geometry requests, semantic pass, paired-diagnostic pass, artifact SHA-256 `ba19a850…`, and verified zero instances/disks. c8 measured 352.112 output tok/s; c16 measured 535.286 output tok/s, a 52.02% gain. At the pinned $0.8581222/hour rate, c16 is $0.445308/M output tokens (34.22% lower than c8), clearing the $0.60/M gate. Session exposure was 1,412.452 s and $0.336682 derived.

**Interpretation and next move.** Promote c16 as the measured current-AWQ background cost frontier under this project's latency-trade policy. The inherited interactive TTFT screen marks `batch_pass=false` because c16 p95 TTFT was 10.060 s, but it is not this background experiment's acceptance criterion; all requests completed in the 300-second arm envelope. The result still carries the existing absolute BF16-quality limitation and does not support a provider-matched or quality-adjusted claim. Close this batching geometry; the next provider intervention should be materially different.
