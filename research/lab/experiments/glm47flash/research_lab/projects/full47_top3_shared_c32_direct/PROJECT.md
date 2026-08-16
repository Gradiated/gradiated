# Full-47 config-native top-3/shared c32 direct endpoint

## Question

Can config-native top-3 routing with the stock shared expert deliver a stable, at least 3% exact-c32 throughput improvement over top-4/shared while avoiding the stronger top-2 candidate's observed quality truncation?

## Why it matters

Top-2/shared measured `666.860853` tok/s and remains above the campaign gates under the worst admissible control bound, but its typed quality capture truncated and its formal bracket did not complete. Top-3/shared is an unmeasured, smaller semantic change using the identical checkpoint/runtime. It should retain more routed capacity while plausibly realizing part of top-2's robust `8.262%` wall-time reduction.

## Exact experiment

Use the last successful full-model path:

- shared launcher `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py` plus `vllm_recover_existing.py`;
- corrected sequential-owner logic in `../full47_top2_shared_c32_direct_corrected/sequence_owner.py` as the source reference;
- checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`;
- pinned vLLM 0.15.0 L40S AWQ runtime, exact tokenizer/prompt bytes, `num_kv_splits=4`, `max_num_seqs=32`, cache off, and 64 exact 8,192-input/1,024-output requests.

Run one fresh retained sequence: top-4/shared pre-control, top-3/shared candidate, top-4/shared post-control. Restart only the server/config arm while reusing verified content-bound runtime/checkpoint state. Before create, prove against real launcher-shaped artifacts that the owner consumes the background contract rather than wrapper return codes, fail-closes semantic/request/cache/typed-harness errors, and that a measured duration table fits setup, three full arm workflows, retrieval, and cleanup inside the absolute deadline. Then launch in the same researcher turn or close locally; no readiness return.

Authorize one preemptible Nebius L40S create, no retry, at most 3,000 allocation seconds and `$0.75` all-in experiment exposure, under one durable external-systemd main and one independent instance/disk watchdog. The first identity, runtime, request, artifact, deadline, provider, or cleanup failure is terminal.

## Gates

Every arm must retain exact identities, 64/64 geometry, <=300-second request wall, semantics, cache disabled/zero, telemetry, archive hash, useful GPU seconds, cost, and authenticated cleanup. Treat a typed harness error as failure; the deferred absolute-quality exception is valid only with its exact carried-forward marker.

Close `UNSTABLE_CONTROL_CLOSE` if controls differ by more than 3% of their mean. Pass top-3 only at both `>=606.355` tok/s and `>=1.03x` the contemporaneous anchor mean; otherwise close `TOP3_SHARED_CLOSE`. This is architecture-cost evidence, not deployable quality.

## Retention decision

No adjacent follow-up qualifies. Top-2 is terminal/no-retry, split-8 is only about 1.045% inside control drift, lower concurrency regresses, and prefix/speculation/KV/runtime alternatives are terminal or incompatible. Clean immediately after post-control or any earlier failure.

## What changes the portfolio

A valid pass makes top-3/shared the leading smaller-divergence performance candidate and justifies a later bounded quality/recovery decision. A close leaves robust-but-quality-failed top-2 as the sole top-k signal and redirects the paid lane to a materially different mechanism or venue.

## Available resources

- `/root/workspace/research/factory/tools`
- `/root/workspace/research/lab/experiments/glm47flash/campaign_100`
