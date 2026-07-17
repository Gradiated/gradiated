# Gemma 4 tied ParallelLMHead measurement v2

## Decision question

Does the actual pinned-image BF16 `ParallelLMHead` for the exact Gemma 4 31B tied `5376→262144` projection leave enough service time for an economical L40S endpoint at background batches, once the shared create path preserves a typed provider response?

This is the sole provider-mutation and spend owner. The predecessor produced no GPU or scientific result: its exact-image final program passed, but `mla_microbench_control.py` discarded the provider-create stdout/stderr before raising on exit 3. This project repairs that shared observability defect offline and then makes one fresh scientific attempt. It must not reinterpret the predecessor as an L40S capacity failure.

## Immutable science packet

- Target: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only, non-reasoning, TP=1.
- Runtime: `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`; observed vLLM `0.19.1.dev6+g6d4a8e6d2`.
- Consumer: `vllm.model_executor.layers.vocab_parallel_embedding.ParallelLMHead`, source SHA-256 `5cdbd9058a99424bf71732d17027c9bc1b6da032f5c1d35b755365f22bb85494`; `UnquantizedEmbeddingMethod`, source SHA-256 `306785c7b7be41d938e40b29cf78377600c4342f5d402009ae8c0dde1bff1c92`.
- Passed predecessor audit: `../gemma_l40s_parallel_lm_head_component/artifacts/final-staged-audit-20260717T063633Z.json`.
- Final benchmark SHA-256 `de7f843a07e10322446a5e173ef60df7dc14763f0924102a2a612e34bdf0ab71`; remote wrapper SHA-256 `e7a947f9124541e387af448c4a11653f7040b45c78c2ebe9e036fd94f91ec255`.
- Economic comparators: 358 decode steps and total request service budgets of 1.394581 seconds planning and 0.86329 seconds conservative.

Reuse the predecessor's staged benchmark and wrapper byte-for-byte unless a final audit proves a change is scientifically necessary. Do not add another representation, endpoint, checkpoint, or quality claim.

## Mandatory `$0` controller terminal

Starting from shared controller SHA-256 `1c7448d956d9c65eaf64494bf3bbd16afcf813e30f57604a36affc873d23af2b`, make only the narrow reusable change needed to retain a redacted `provider-create-diagnostic.json` immediately after every create subprocess. Reuse the established redaction and named-instance reconciliation semantics in `vllm_smoke_control.py`; do not create a project-local provider wrapper.

Focused deterministic tests must prove:

1. a nonzero create with no created instance writes return code, stdout/stderr hashes, and redacted bounded tails before the typed error;
2. a successful create writes the same diagnostic and resolves the returned instance;
3. a nonzero response that nevertheless created the named instance is reconciled and bound to cleanup ownership before watchdog/startup work;
4. representative token, authorization, password, secret, and private-key fixtures never survive in retained tails;
5. exception paths still emit a terminal summary and verified empty cleanup evidence.

Emit `artifacts/CONTROLLER_TERMINAL.json` with pass/fail, exact before/after hashes, test command/results, fixture hashes, authenticated empty initial inventory, and an explicit `provider_mutation_occurred: false`. Provider creation is forbidden unless this typed terminal passes. If deterministic work outlives a response, use one project-local no-provider user-systemd owner with a 25-minute absolute deadline, 10-GiB temporary cap, and terminal path above; do not kill or restart correct work for turn cadence.

## One paid measurement

After the controller terminal passes, rerun the exact-image final staged audit against the actual post-patch controller bytes, verify authenticated empty inventory, and launch the shared `mla_microbench_control.py` under one bounded durable systemd owner plus its independent cleanup watchdog. One allocation only.

Run the actual BF16 consumer with deterministic activations and zero BF16 `[262144, 5376]` weights at M=1/2/4/8/16/32. Require every row, finite zero oracle, output consumption, CUDA-event and wall p50/p95, memory, GPU telemetry, useful-GPU/setup seconds, concrete classes/sources, and typed archive/manifest hashes. Translate each row through 358 decode steps to per-batch and per-request head service time. Classify whether the head alone falsifies neither, only the conservative, or both request envelopes; missing attention, MLP, KV, scheduler, sampling, queueing, reliability, and quality remain explicit.

Any create response is now classifiable evidence. A second pre-GPU operational failure, missing row, false consumer, oracle/telemetry failure, or both-envelope miss closes this project without repair. Always retrieve typed artifacts and verify authenticated zero instances/disks.

## Adjacent-session disposition

The ranked conditional packets were reviewed before launch: native MTP binds a distinct H100/image, SGLang binds a different engine, prefix-cache/window/quality arms require a resident full checkpoint, and the FP8/W4 consumer lineages are closed or lack a final-audited ten-minute program. None is compatible with this checkpoint-free resident image and runtime. Therefore no retained follow-up is authorized: tear down immediately after the head terminal. A researcher may record a changed compatibility fact, but may not invent a substitute arm or retain the allocation.

## Budgets and artifacts

- Wall clock: 80 minutes, including controller work and cleanup.
- Provider exposure: 20 minutes maximum under one sequential owner.
- Compute: 0.34 L40S GPU-hours and 3 local CPU-hours.
- Storage: one 100-GiB provider boot disk; 10 GiB project-local temporary and 4 GiB retained artifacts; no shared `/tmp`.
- Spend: `$0.50` maximum including disk; one allocation.

Write `artifacts/CONTROLLER_TERMINAL.json`, the refreshed final audit, raw provider diagnostic, stage archive, `artifacts/SUMMARY.json`, concise `RESEARCH_LOG.md`, and terminal `STATUS.json`.
