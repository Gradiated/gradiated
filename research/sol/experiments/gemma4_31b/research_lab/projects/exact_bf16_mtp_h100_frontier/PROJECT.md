# Exact BF16 and MTP H100 serving frontier

## Question

On one Nebius H100, what is the sustainable cost frontier for the exact pinned `google/gemma-4-31B-it` BF16 checkpoint under the campaign's prompt-heavy background workload, and does native Gemma 4 MTP reduce matched end-to-end cost by at least 5% without changing deterministic text output?

## Why this is first

The lab has no runnable control. Official vLLM Gemma 4 guidance says the 31B dense model fits one 80 GB NVIDIA GPU in BF16, documents a Gemma 4-specific container, and supports the 31B assistant checkpoint through the native MTP path. Nebius has a proven one-H100 lifecycle and cleanup path. This is therefore the shortest route to both a content-addressed baseline and a measured intervention; a pre-GPU failure is operational evidence, not evidence against BF16, MTP, or H100.

The market comparison is component-wise: approximately `$0.12/M` fresh input, `$0.09/M` cache read, and `$0.35/M` output at OpenRouter's credible low-price frontier. Also preserve the Artificial Analysis 10K-input single-stream view. Production economics use the fresh shared H100 planning rate of `$2.80/GPU-hour` with its `$2.50-$3.10` range; experiment accounting uses the actual authenticated Nebius meter.

## Exact scope and proven path

- Target: `google/gemma-4-31B-it` at revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, default non-reasoning, text-only.
- Resident/local target inputs at delegation: none; do not substitute another checkpoint or derivative. Bind the official config, tokenizer/chat-template/processor files, model index, and every weight shard to the pinned revision before accepting a result. Record byte counts and SHA-256 identities after staging.
- MTP source: the official 31B Gemma 4 assistant checkpoint named by current vLLM documentation, presently `gg-hf-am/gemma-4-31B-it-assistant`; resolve and bind an immutable revision before use. If that identity cannot be established, skip MTP and use the pre-registered scheduler arm below.
- Runtime: the official `vllm/vllm-openai:gemma4` CUDA image, resolved to an immutable digest before provider creation. Do not assume the GLM campaign's vLLM 0.15.0 image supports Gemma 4.
- Proven provider mechanics: reuse the create/reconcile/watchdog/SSH/telemetry/retrieval/absence-verification mechanics in `research/sol/experiments/glm47flash/campaign_100/nebius/placement_control.py` and `vllm_smoke_control.py`, scoped through code in this project. Do not inherit GLM model, tokenizer, runner, quality, or kernel constants.
- Placement: `gpu-h100-sxm`, `1gpu-16vcpu-200gb`, one preemptible H100, one 200 GiB disk, one sequential owner. Check mutable inventory, authenticated rate, source access, and image digest once as a grouped preflight. One material correction is allowed if creation or staging fails before GPU science; then fall back to the last proven lifecycle rather than opening a new controller lineage.

## Immediate experiment

Run the exact BF16 stock control first. Disable image/audio admission and cap model length at the smallest value that admits both 10,000 input plus 1,500 output tokens and the primary workload. Measure:

1. An Artificial Analysis methodology-matched approximation: 10K input, single stream, fixed output geometry, with TTFT and post-first-token output rate clearly separated from aggregate throughput.
2. The primary OpenRouter-shaped fresh-input workload centered on 4,214 input and 358 output tokens, with a saturation ladder beginning at concurrency 1, 8, and 16 and continuing only while the next point is decision-relevant. Use deterministic, reproducible prompts and complete-request accounting. Latency may trade for cost, but every request must complete within a declared 300-second arm envelope.
3. At the best valid stock concurrency, restart only the server and run native MTP with `num_speculative_tokens=1` against a fresh matched stock repeat. Keep target checkpoint bytes, runtime digest, workload bytes, seed, and allocation fixed. Require exact token/output agreement for deterministic diagnostic prompts plus complete-request and semantic checks. Broad production quality remains deferred.

If measured setup and checkpoint staging exceed scored GPU time, retain the allocation after the stock endpoint only when the next arm is already typed and can start within ten minutes. The named adjacent conditional fallback is vLLM `--async-scheduling` on versus off at the best stock concurrency, prepared by `../exact_geometry_runtime_opportunities/`. It may run only if MTP is unavailable or invalid before its workload starts. Reuse only the content-bound runtime/checkpoint state, keep the same owner and cleanup watchdog, and tear down immediately if neither trigger passes. Do not keep the allocation merely for planning.

## Evidence and decision

Capture setup versus useful GPU seconds, server and request rows, prompt/decode throughput, TTFT/inter-token latency, queueing, KV/cache statistics, GPU memory/utilization/power, failures/reloads, model/runtime/workload identities, storage and VM exposure, actual spend, and verified zero final inventory. A typed envelope containing a nested runner error is not a scientific result.

Report fresh-input, cache-read opportunity, and output economics separately, then the measured workload blend with utilization/headroom sensitivity. Do not claim cache savings without a measured cache arm.

- Promote MTP or async scheduling for the next quality/capacity stage at `>=5%` matched sustainable cost reduction with valid outputs; `>=10%` is a strong promotion.
- A valid sub-5% result closes that arm at this geometry.
- A stock result establishes the new control even if the candidate fails.
- A pre-GPU failure redirects launch mechanics or venue and does not close the scientific intervention.

## Budgets and ownership

- Exclusive provider mutation/spend owner for this lab while active; at most one live allocation.
- Wall clock: 4 hours for the durable owner, with at most 3 hours of provider exposure.
- Compute: 3 H100-hours maximum; local preparation at most 2 CPU-hours.
- Spend: `$8.00` maximum including disk and cleanup margin, within the campaign's `$25` cap.
- Storage: one 200 GiB provider disk; at most 8 GiB of retrieved artifacts in this project. Delete provider resources after terminal retrieval.
- If local checkpoint preparation or transfer must outlive a response, start one bounded durable owner in this project, record `STATUS.json.active_session` with its absolute deadline, artifact root, unit, unit manager, and typed terminal, and keep provider creation gated until that terminal passes. Do not kill correct work at a turn boundary.
