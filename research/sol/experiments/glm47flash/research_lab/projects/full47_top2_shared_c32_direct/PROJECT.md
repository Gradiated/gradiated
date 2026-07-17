# Full-47 config-native top-2/shared c32 direct endpoint

## Question

At the newly measured c32 saturation point, can the exact full-47 current-AWQ model reduce routed experts per token from four to two while retaining the stock BF16 shared expert and improve output-token economics by at least 3%?

## Why this matters

The old c16 screen closed top-2/shared because its `6.187016%` optimistic routed-work ceiling projected only `588.587` tok/s. The new exact bracketed c32 controls average `602.157121` tok/s. Applying the same ceiling only as a nomination prior gives `641.870` tok/s, above the absolute `606.355` gate and the drift-resistant `1.03x` gate (`620.221834`). This operating point has never been measured.

This is not a retry of the terminal top-2/no-shared patch. Change only `num_experts_per_tok: 4 -> 2`; retain `n_shared_experts: 1`, every checkpoint tensor, the stock shared-expert branch, full depth, MLA/KV state, precision, runtime, and scheduler. No source-forward patch, skipped tensor, zero-width module, shared-65 fusion, or custom kernel is allowed. The result is an architecture-cost proxy; recovery and production quality remain mandatory later.

## Fixed inputs and owner

- Checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, config SHA-256 `079f8fcd477b07378deafc21ecc5c3b974bf109ce5c9115854d97f88fa7622b9`, and index SHA-256 `b9c53433e94f2fe7870cdbc3fcb6ed1431eb500c5242a039de93fef4bb988695`.
- Pinned vLLM `0.15.0` image `sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`.
- Proven launcher `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, retained-session helper `vllm_recover_existing.py`, and the background-knee systemd-main plus independent-watchdog ownership pattern.
- Current control archive `../full47_current_background_knee_direct/artifacts/l40s_background_knee_20260716_r1/vllm-awq-batch.tar.gz`, SHA-256 `94e2f841e3a0aa1b4c166e4a4defa20e2b3c5b0cd2ab23f9acc7877ae4d86dbf`.
- Planning rate `$1.10/L40S-hour`; exact cache-off 8,192-input/1,024-output workload; `max_num_seqs=32`, `max_num_batched_tokens=65536`, BF16 KV, and four KV splits.

One external-systemd main owns provider mutation, all sequential science, retained state, and cleanup; one independent watchdog owns the absolute deadline. Authorize one Nebius L40S create, at most `$0.60` and `2,400` allocation seconds. Fresh inventory must be zero before create. Do not return readiness: bind the two content-addressed configs, prove every non-config byte identical, and launch in the same researcher turn or close locally.

## Original A/B/A sequence

On one allocation with only content-bound runtime/checkpoint state reused, run fresh server processes in this order:

1. stock top-4/shared c32 pre;
2. config-native top-2/shared c32 candidate;
3. restored stock top-4/shared c32 post.

Each arm must complete 64 exact requests inside 300 seconds and retain ordered identity, rows, token geometry and histograms, prefix-cache zero deltas, semantic diagnostics, actual routed-top-k/config evidence, load and resident memory, throughput/latency, power/clocks/utilization, useful GPU seconds, exposure, archive hashes, and cleanup evidence. A capacity, load, request, or semantic failure is scientific evidence, not a retry trigger.

If the stock anchors differ by more than `3%` of their mean, return `UNSTABLE_CONTROL_CLOSE`. Otherwise return `TOP2_SHARED_PROXY_PASS` only if top-2 is at least `606.355` tok/s and at least `1.03x` the anchor mean. Every other valid endpoint returns `TOP2_SHARED_CLOSE`.

## One conditional adjacent follow-up

The measured create/SSH/bootstrap/checkpoint staging time (`828.180 s`) exceeds the expected scored A/B/A time, so preregister one adjacent top-3/shared c32 arm. Before create, content-address its config and bind it to the existing retained-session helper and the same sequential owner/watchdog; if this cannot be ready within ten minutes, omit it and clean normally.

Retain after the post-control only on named trigger `TOP2_SHARED_PASS_ENABLES_TOP3_RECOVERY`: controls are stable and top-2 passes both gates with every diagnostic complete. Then restart once with `num_experts_per_tok: 3`, reuse only verified runtime/checkpoint state, and run one exact c32 arm. If top-3 also reaches `606.355` and `1.03x` the original anchor mean, prefer it as the smaller semantic divergence; otherwise preserve the top-2 result. If the trigger is false, the command is not ready, or any follow-up evidence fails, tear down immediately. No second create, repair, retry, further top-k value, or post-result retention is allowed.

## Available resources

Use the fixed projects above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

## Cycle 136 terminal ownership correction

The top-4 pre-control completed 64/64 exact requests at `614.925626` output tok/s in `106.575 s`, with exact geometry, semantic pass, and zero prefix-cache deltas. The generic launcher nevertheless returned nonzero because its inherited interactive `fixed_slo_pass` was false. That SLO is not the campaign's background completion envelope, but the durable sequential science owner exited on the return code before top-2, post-control, or top-3 ran.

Only the independent cleanup watchdog remains. This allocation is cleanup-only: do not attach a replacement science process, run a recovery arm, or treat the hash-only top-3 config as an executable preregistration. Authenticate zero instance/disk inventory after teardown. The scientific question is transferred to `../full47_top2_shared_c32_direct_corrected/` as one material fresh correction after cleanup.
