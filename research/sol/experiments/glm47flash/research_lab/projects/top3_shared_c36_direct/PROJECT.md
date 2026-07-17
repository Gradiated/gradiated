# Top-3/shared c36 background frontier

## Question

Does the bracketed top-3/shared architecture gain more throughput at background concurrency 36 than at 32, enough to materially improve its narrow sustainable-cost headroom on L40S?

## Why it matters

Top-3/shared is the strongest smaller-divergence full-47 architecture-cost result: `644.318005` tok/s, `1.062619x` a stable top-4 control mean, and raw planning-GPU COGS of `$0.474231/M`. The corrected economics frontier shows that this point needs `93.2–97.1%` productive utilization at the `$1.10/hour` base rate depending on omitted-cost reserve. Background latency is secondary, so a concurrency increase is valuable only if it produces a real throughput gain rather than the stock model's measured c36 collapse.

## Exact experiment

Use one fresh preemptible Nebius L40S and the last successful full-model path:

- shared lifecycle launcher `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py` and retained-session recovery `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_recover_existing.py`;
- checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`;
- pinned vLLM `0.15.0` L40S AWQ runtime, top-3 routing with the stock shared expert, BF16 KV, `num_kv_splits=4`, prefix cache off, and the exact 8,192-input/1,024-output workload;
- existing ordered-frontier support from `../full47_stock_maxseq36_split8_frontier/` and typed background/quality handling from `../full47_top3_shared_c32_direct/`.

Run a same-server top-3/shared c32 control followed by top-3/shared c36, each with exactly 64 complete requests. Set the server geometry to admit c36 from the start; change only request concurrency between the two primary arms. Before create, exercise the real typed launcher summary, freeze the c32/c36 sequence and the conditional c40 recovery command, and prove from measured setup/arm/recovery/cleanup durations that the full reachable sequence fits the absolute budget. Launch in that same researcher turn or close locally; do not return readiness.

Authorize one provider create, no retry, at most 3,300 allocation seconds and `$0.80` total experimental exposure, under one durable external-systemd main and one independent instance/disk watchdog. Provider identity, input-hash, runtime, request, artifact, deadline, or cleanup failure is terminal.

## Gates

Both primary arms must preserve the exact identities, 64/64 geometry, 300-second background completion envelope, semantic and typed-harness completeness, cache-disabled/zero evidence, HBM/allocator telemetry, utilization, power, throughput, useful GPU seconds, allocation cost, archive hashes, and authenticated cleanup.

First require the fresh c32 control to remain within `3%` of the prior `644.318005`-tok/s top-3 result; otherwise return `CONTROL_TRANSFER_CLOSE`. Promote c36 only if it is at least `663.647545` tok/s (`1.03x` the prior result), at least `1.03x` its fresh same-server c32 control, and retains at least `512 MiB` of conservative device-memory headroom. This threshold implies raw base-rate GPU COGS no worse than `$0.460419/M`, or about `10.42%` raw headroom to the authoritative target before lifecycle and omitted costs. Return `TOP3_C36_PASS` only when every gate passes; otherwise return `TOP3_HIGHER_CONCURRENCY_CLOSE`.

This is architecture-cost evidence only. Preserve and report the existing `QUALITY_ARTIFACT_CLOSE`; do not relabel development evidence, claim deployability, or start quality/recovery work.

## Conditional retained follow-up

Pre-register one adjacent c40 arm before launch under `TOP3_C36_PASS_AND_C40_MEMORY_ADMISSION`. It is true only if c36 passes every primary gate and the measured c36 peak plus a conservative exact four-sequence KV/allocator increment predicts c40 at or below `45,556 MiB` (`512 MiB` below the `46,068 MiB` envelope). On true, reuse only the verified runtime/checkpoint through the established sequential recovery path, restart at max-seqs 40, and run one 64-request top-3/shared c40 arm. Promote it only if it completes every evidence gate and is at least `1.03x` c36; otherwise retain the c36 decision. On false, or if less than the measured 10-minute recovery-plus-arm reserve remains, clean immediately. No other adjacent arm is authorized.

## What changes the portfolio

A c36/c40 pass provides a materially stronger raw-cost candidate for later production-policy and execution-bearing quality work. A close ends higher-concurrency tuning for top-3/shared and leaves A40 c8/c16 as the next materially different direct intervention once TensorDock authority exists. No result in this project is a sustainable all-in or provider-beating claim.

## Available resources

- `/root/workspace/research/factory/tools`
- `/root/workspace/research/sol/experiments/glm47flash/campaign_100`
