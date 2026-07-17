# Exact Gemma 4 direct SGLang H200 endpoint

## Decision question

Can the pinned exact Gemma 4 31B checkpoint serve the campaign workload through SGLang BF16 weights plus FP8-E5M2 KV on one H200 at a sustainable primary throughput that can beat the current market frontier? If it does, does a sequential matched vLLM BF16 control show at least a 10% SGLang cost advantage?

This is the next paid science lane because the earlier H200 and L40S allocations ended before model execution on owner/bootstrap defects. Those failures are not engine or hardware evidence. The prior matched-H200 project exhausted its retry contract; this project instead uses SGLang as the direct primary runtime and admits no provider-only repair cycle.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it` at revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning.
- Read-only checkpoint: `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint`, governed by its passing `CHECKPOINT_TERMINAL.json`. Do not rematerialize it locally.
- SGLang runtime: source commit and immutable amd64 image from `../sglang_gemma4_exact_precreate_binding/START_PACKET.json`: `docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427`, BF16 weights, `--kv-cache-dtype fp8_e5m2`, TP=1.
- Conditional control runtime: `vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, BF16 weights and default KV.
- Exact primary trace: consume `../gemma_exact_cache_trace_contract/TRACE_PACKET.json`. It contains exact token-ID arrays for 4,214 input / 358 output at true simultaneous c1/c4/c8/c16, a 535-token intended common prefix, at most 528 block-cacheable tokens, and a disjoint 10,000-input / 358-output c1 view. Preserve the token arrays, body hashes, seed, sampling, stop IDs, stream terminals, warmup/scored ordering, and live cache-counter deltas. If SGLang requires its native token-ID field, use that field without retokenizing and retain the submitted token arrays and their hashes.
- Hardware: Nebius `gpu-h200-sxm`, `1gpu-16vcpu-200gb`, one 141-GB H200, one 250-GiB disk, lowercase RFC-1123 resource names.
- Economic terminal: `../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json`. At the `$3.25/H200-hour` planning rate, the strict primary planning-base market gate is 2.094181–2.118591 completed requests/s and the market request-cost range is `$0.000614287–$0.000621447`. Use the authenticated experiment meter for spend and the planning rate/range for production comparisons.
- Proven lifecycle: reuse the provider ownership, diagnostic create reconciliation, SSH/session staging, independent cleanup watchdog, artifact retrieval, and authenticated cleanup primitives from `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/placement_control.py` and `stock_control.py`. The valid prior is `allocations/nebius_h100_complete_stock_v13/summary.json` (`cleanup_pass=true` with real SGLang model work). Adapt the scientific runtime and payload only; do not create a general controller framework.

The director-generated `artifacts/DIRECTOR_IDENTITY_ASSERTION.json` must pass before activation. The researcher must consume it and recheck only mutable placement/rate/inventory facts.

## Required execution

Use one bounded durable local owner for all provider mutation, spend, retained content state, and cleanup. A correct checkpoint transfer, image pull, model load, compilation, or scored run may outlive an agent response; preserve that owner and its independent watchdog. Provider creation remains gated on a final rendered-program audit, passing immutable identities, an authenticated empty inventory, current H200 placement/rate, and an output directory that the owner itself creates under the existing project `artifacts/` parent.

The final program audit must inspect the actual lower program/argv and prove: dedicated user-owned remote workspace parents before transfer; no precreated owner output directory; exact checkpoint and image digests; explicit `--entrypoint` override for image diagnostics so neither SGLang nor vLLM parses `nvidia-smi` flags; exact token arrays and group concurrency; semantic-first stop; atomic per-engine persistence/retrieval; telemetry; spend/deadline; named trigger; watchdog; and authenticated cleanup. Any paid failure before a semantic model response closes this project after cleanup. Do not repair or create a second allocation.

Run sequentially:

1. Start SGLang with the packet-bound BF16/FP8-E5M2-KV command. The first scientific request is one exact primary c1 request. Require served-model identity, HTTP/stream terminal, exactly 4,214 prompt and 358 generated tokens, retained raw response/output IDs where exposed, and no parser/stop/reload failure. If this semantic gate fails, retrieve diagnostics and clean up immediately.
2. If semantic c1 passes, run the exact primary c1/c4/c8/c16 ladder with true simultaneous release, then the separate 10K/358 c1 view. Retain raw requests/responses, output IDs where exposed, server metrics before/warmup/scored, complete requests, failures/reloads, prefill/decode/request wall time, TTFT, ITL, queueing, realized cache-read tokens, HBM/allocator state, continuous GPU utilization/power, provider-active seconds, useful-GPU seconds, and actual GPU/disk/other cost. Persist and retrieve the SGLang decision bundle before any runtime change.
3. While the SGLang owner runs, keep a fully rendered local matched-vLLM program and exact request packet ready. `SGLANG_MARKET_TRIGGER` passes only if semantic and raw telemetry gates pass, there are no failures/reloads, at least one stable c8 or c16 point reaches 2.094181 completed requests/s, the matched vLLM arm can begin within ten minutes, and the absolute owner deadline remains sufficient. Only then pull/start the pinned vLLM image on the same resident checkpoint/allocation and run the same primary ladder plus separate 10K view. Otherwise record the failed trigger and clean up immediately. Do not retain for any other arm.

The vLLM control is adjacent and conditional, not a second allocation or an excuse to delay SGLang. Match checkpoint, token IDs, sampling, output length, concurrency, H200, and accounting. Compare only engine-valid stable saturation points. SGLang promotion requires both the absolute market gate and sustainable cost/request `<=0.90x` matched vLLM, with no worse raw-output/reliability boundary. A market miss is still a valid endpoint result. Do not claim production quality, vision, reasoning, or full OpenRouter eligibility from this project.

## Budgets and terminal contract

- Wall clock: 130 minutes including final audit, provider work, retrieval, and cleanup.
- Provider exposure: 90 minutes maximum under one sequential owner and one allocation.
- Compute: 1.5 H200 GPU-hours and 3 local CPU-hours.
- Storage: reuse the read-only verified local checkpoint; one 250-GiB provider disk; at most 12 GiB project artifacts; no shared `/tmp`.
- Spend: `$4.00` maximum including compute, disk, and other metered provider charges.

Write the final-program audit, owner/watchdog snapshot, atomic SGLang bundle, conditional-vLLM trigger and bundle if run, `artifacts/SUMMARY.json`, concise `RESEARCH_LOG.md`, and terminal `STATUS.json`. Cleanup is part of the terminal: authenticated zero named instances and disks or an explicit live-watchdog handoff.
