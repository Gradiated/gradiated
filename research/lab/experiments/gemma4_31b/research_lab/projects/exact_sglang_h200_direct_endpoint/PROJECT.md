# Exact Gemma 4 direct SGLang H200 endpoint

## Decision question

Can the pinned exact Gemma 4 31B checkpoint serve the campaign workload through SGLang BF16 weights plus FP8-E5M2 KV on one H200 at c32 below the strict `0.47201182295214134 s/request` planning ceiling, with nonempty outputs and usable batch completion?

This project is reactivated because its prior allocation failed before SSH solely on a user/system watchdog-scope defect and produced no engine or hardware evidence. The now-proven corrected H200 lifecycle has completed provider create, checkpoint transfer, image launch, retrievable diagnostics, model loading, and a real retained repair window. This is a distinct engine/representation hypothesis from the exhausted vLLM AWQ-W4 endpoint line, not another W4 retry.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it` at revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning.
- Read-only checkpoint: `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint`, governed by its passing `CHECKPOINT_TERMINAL.json`. Do not rematerialize it locally.
- SGLang runtime: source commit and immutable amd64 image from `../sglang_gemma4_exact_precreate_binding/START_PACKET.json`: `docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427`, BF16 weights, `--kv-cache-dtype fp8_e5m2`, TP=1.
- Exact primary trace: consume `../gemma_exact_cache_trace_contract/TRACE_PACKET.json`. It contains exact token-ID arrays for 4,214 input / 358 output at true simultaneous c1/c4/c8/c16, a 535-token intended common prefix, at most 528 block-cacheable tokens, and a disjoint 10,000-input / 358-output c1 view. Preserve the token arrays, body hashes, seed, sampling, stop IDs, stream terminals, warmup/scored ordering, and live cache-counter deltas. If SGLang requires its native token-ID field, use that field without retokenizing and retain the submitted token arrays and their hashes.
- Hardware: Nebius `gpu-h200-sxm`, `1gpu-16vcpu-200gb`, one 141-GB H200, one 250-GiB disk, lowercase RFC-1123 resource names.
- Economic terminal: `../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json`. At the `$3.25/H200-hour` planning rate, the strict primary planning-base market gate is 2.094181–2.118591 completed requests/s and the market request-cost range is `$0.000614287–$0.000621447`. Use the authenticated experiment meter for spend and the planning rate/range for production comparisons.
- Proven lifecycle: adapt the corrected retained lifecycle and regression bound in `BINDINGS.json` from `../h200_w4_full_endpoint_background_frontier/`. Preserve its user-systemd owner, provider reconciliation, project-relative artifacts, independent watchdog, retrievable container/GPU/state/exit/OOM diagnostics, earlier repairable work deadline, real 600-second retained-development context, and authenticated cleanup. Change only the checkpoint size, SGLang image/argv, and request program.

`BINDINGS.json` mechanically binds the authoritative checkpoint, SGLang packet, request trace, economic gate, component floor, and corrected lifecycle. The researcher must verify every digest and recheck only mutable placement/rate/inventory facts before provider create.

## Required execution

Use one mutable retained development owner for all provider mutation, spend, resident state, repair, and cleanup. Provider creation is gated on the bound digests, authenticated empty inventory, current H200 placement/rate, corrected owner regression, and a rendered SGLang program whose exact argv, trace bytes, diagnostics, deadline, retrieval, and cleanup are inspectable. Missing runner code is ordinary in-project implementation. Cold transfer, image pull, and model load may outlive a response.

Run c32 first. Submit the exact 4,214-token prompt and require 358 generated tokens, served-model identity, nonempty raw output, request/response hashes, and a typed stream/HTTP terminal. Then run enough warmup and scored simultaneous c32 batches to measure completed requests/s, service time/request, batch duration, TTFT, ITL/decode rate, queueing, failures/reloads, effective cache-read tokens, allocator/HBM peak, continuous GPU utilization/power, useful-GPU seconds, provider exposure, and actual compute/disk/other cost. Ordinary launch, API, trace, telemetry, or packaging failures are repaired in place against the same resident resource.

The strict decision gate is `>=2.118591` completed requests/s (`<=0.47201182295214134 s/request`) at the campaign mix. The measured H200 BF16 c32 linear-plus-head floor is `0.22476958992984145 s/request`; no component timing is an endpoint claim. Do not spend on c16: its component floor leaves only about 30 ms/request before all omitted work. Run the bound 10K/358 single-stream view sequentially only if c32 is semantically valid, no reliability failure occurred, and at least 20 provider minutes remain. A valid market miss closes this route. A pass promotes representative quality and feature validation, not deployment eligibility.

## Budgets and terminal contract

- Wall clock: 120 minutes including implementation, provider work, retrieval, and cleanup.
- Provider exposure: 80 minutes maximum under one retained owner.
- Compute: 1.34 H200 GPU-hours and 3 local CPU-hours.
- Storage: reuse the read-only verified local checkpoint; one 250-GiB provider disk; at most 12 GiB project artifacts; no shared `/tmp`.
- Spend: `$3.75` maximum including compute, disk, and other metered provider charges.

Write the pre-create terminal, owner/watchdog snapshot, atomic SGLang c32 bundle, conditional 10K disposition and bundle if run, `artifacts/SUMMARY.json`, concise `RESEARCH_LOG.md`, and terminal `STATUS.json`. Cleanup is part of the terminal: authenticated zero named instances and disks or an explicit live-watchdog handoff.
