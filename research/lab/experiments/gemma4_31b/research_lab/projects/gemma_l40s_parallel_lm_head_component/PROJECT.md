# Gemma 4 tied ParallelLMHead component on L40S

## Decision question

Does the actual pinned-image BF16 `ParallelLMHead` for Gemma 4's tied `5376→262144` vocabulary projection leave enough per-request service budget for an economical L40S endpoint at background batch sizes?

## Why now

The W4 consumer lineage is closed without timing rows, but the tied BF16 head is representation-independent and remains on every candidate's decode path. Its exact matrix is 2.625 GiB. A prior generic M=1 row suggested about 3.862 ms per token, while FLOP-only accounting understated the decision value. Measuring the actual vLLM consumer at M=1–32 is the shortest independent target-GPU falsifier and can either close L40S economics or quantify the batch amortization available to future representations.

## Immutable inputs

- Exact target `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning, TP=1.
- Image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`; exact-image inspection SHA-256 `725bcd0437cdcaf8f354fab071967f0d8d91d3f0f4bdada808e6da049d2bda9c` records vLLM `0.19.1.dev6+g6d4a8e6d2`.
- Existing actual-consumer script prior SHA-256 `d687c4af53349d3424602de916c39fb942d0d17d19cf79fdeb64d6d47ebbb071`; consume it as a starting point, not as a passed benchmark.
- `../tied_vocab_projection_cost_bound/VOCAB_BOUND.json`, SHA-256 `5bbd3d06f6e606005a61dc4327e38ee4326b65f781febdc4d1d2a47affb15fa3`.
- `../l40s_saturation_economic_gate/SATURATION_GATE.json`, SHA-256 `690e0e457c6e8e9121b54fb7f88abc92c3dcc358e1d71accffddb083878d00d6`.
- `../exact_market_venue_decision_surface/MARKET_TARGET.json`, SHA-256 `5d636809dc25450050c565cdc108bf7e91eaa60ce07c027ca390c8011e3b8e51`.
- `../gemma4_mtp_acceptance_economic_bound/MTP_BOUND.json`, SHA-256 `8f31a7071f2a4d0f7a31341211351327ce08264a4cf5b8644f0054a57636b795`.

No model or tokenizer checkpoint is needed for the primary.

## Required paid experiment

Use the existing shared `mla_microbench_control.py`, durable owner, watchdog, pinned image staging, typed retrieval, and verified cleanup. Do not create another controller or provider wrapper. Run the actual installed `vllm.model_executor.layers.vocab_parallel_embedding.ParallelLMHead` with a BF16 zero weight and BF16 deterministic activations at M=1/2/4/8/16/32. Record concrete class and quantization method, source/module identity, shape/dtypes, seeds, warmups/iterations, finite zero-oracle result, raw CUDA-event and wall p50/p95, peak allocated/reserved memory, GPU telemetry, useful-GPU/setup seconds, and artifact hashes. Consume every timed output so an optimized-away/no-op path cannot pass.

Before create, audit the final staged bytes inside the exact local image: import and CPU-safe construction/signature, all six M rows mechanically required, nonzero typed failure, internal manifest/stage terminal, telemetry, and useful-GPU fields. This is one focused same-project check, not a successor. If correct local work outlives a response, use one no-provider systemd owner with a 30-minute deadline and 20-GiB temporary cap; provider create remains gated on its typed terminal.

For each M, derive the 358-step batch wall and per-request head service time. Compare head alone against the 1.394581-second planning and 0.86329-second conservative total request budgets, and compare measured p50 with the 2.818572-GB/864-GB/s bandwidth floor. This is a component lower bound: attention, MLP, KV, scheduler, sampling, queueing, reliability, and endpoint quality remain missing. A scientific pass requires all six actual-consumer rows and oracle/telemetry validity; classify whether the head alone falsifies neither, only conservative, or both economic envelopes.

## Adjacent conditional follow-up

Measured image setup has repeatedly exceeded scored component time. While the primary owner runs, prepare at most one conditional arm from `../gemma4_mtp_acceptance_economic_bound/` using the official assistant identity in `../exact_geometry_runtime_opportunities/ADJACENT_ARM_PACKET.json`. It may stage the content-bound 0.939-GB assistant and run an actual pinned-image one-step proposer component on deterministic synthetic target hidden state, recording proposer wall/CUDA time, memory, symbols, and finite outputs. It does not measure acceptance or endpoint gain.

Run it only if the head consumer passes, the head alone does not falsify both envelopes, and the assistant arm is final-audited and start-ready within ten minutes before the primary owner ends. Use the same retained image/allocation and sequential owner/watchdog. If any trigger is false, record it and clean up immediately. Do not retain for async scheduling, a server, target checkpoint, or any other work.

## Stop rules and artifacts

- Unsupported/false consumer, empty/wrong rows, nonfinite/oracle failure, or head-alone miss of both envelopes is a typed scientific negative and immediate cleanup.
- A pass establishes only a component timing bound, never checkpoint quality or sustainable endpoint cost.
- Write `artifacts/summary.json` with all identities/rows, economic interpretation, conditional trigger/disposition, exposure/spend, hashes, and verified zero-resource cleanup.

## Budgets

- Wall clock: 90 minutes.
- Provider exposure: 20 minutes maximum under one sequential owner.
- Compute: 0.34 L40S GPU-hours and 3 local CPU-hours.
- Storage: one 100-GiB provider disk; 20 GiB bounded project-local temporary and 4 GiB retained artifacts; no shared `/tmp`.
- Spend: `$0.50` maximum including disk; one allocation.
