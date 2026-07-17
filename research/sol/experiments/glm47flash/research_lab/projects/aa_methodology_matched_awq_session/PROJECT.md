# Artificial Analysis methodology-matched current-AWQ session

## Question

What performance and cost does the measured current GLM-4.7-Flash AWQ/vLLM L40S stack achieve under an Artificial Analysis–methodology-matched single-request workload and the public System Load Test, and can one retained allocation produce the complete multi-arm graduation artifact?

## Why it matters

Current AWQ c16 is the campaign's measured productive frontier at 535.286 output tok/s and $0.445308/M output tokens, but it uses the internal 8,192-input/1,024-output workload. Campaign graduation separately requires an Artificial Analysis–methodology-matched performance/cost report and one retained-allocation session containing several scientific arms with complete telemetry and cleanup. Those are independent missing gates even while absolute quality remains unresolved.

## Experiment

Reuse the proven Nebius lifecycle in `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py` and its remote script; do not create another controller, wrapper, service lineage, checkpoint, or runtime. Bind current AWQ revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, model-manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`, the already content-addressed tokenizer/template inputs, vLLM 0.15.0, thinking disabled, streaming, and cache-off accounting. Preserve the launcher's diagnostic retention, exact-name create reconciliation, watchdog, GPU/server telemetry, artifact retrieval, and two-view cleanup.

Add one bounded methodology mode to that proven launcher/remote workload and exercise it in the same researcher turn. Local tests may cover parsing and terminal behavior, but a preparation-only handoff is not admissible. The retained allocation must run:

1. At least seven unique, diverse, content-addressed single-request prompts, each approximately 10,000 input tokens and at least 1,500 generated tokens. Count with OpenAI `o200k_base`, report streaming TTFT and post-first-token output speed per request, and summarize medians. Label this methodology-matched rather than an exact replay because Artificial Analysis's live prompts are private.
2. The public System Load Test geometry: unique/diverse 1,000-input/1,000-output requests, streaming, three-minute phases at concurrency 1, 2, 4, 8, 16, 32, 64, then higher powers of two only while admitted and until the preregistered plateau rule fires. Define plateau before launch as two adjacent steps with less than 5% aggregate-throughput gain; report any memory/admission ceiling as a measured boundary, not a plateau.
3. One exact internal 8,192-input/1,024-output c16 control using the prior content binding. Require full completion, semantic and paired-diagnostic pass, and a result within 10% of 535.286 output tok/s; a miss prevents cross-session economic transfer but does not erase the methodology measurements.

Increase sequence admission only as required for the 1K load ladder; do not change representation, runtime version, kernels, or reasoning mode. Retain raw request rows, prompt identities, OpenAI-token counts, per-phase telemetry, server metrics, GPU samples, TTFT/output-speed/aggregate-throughput summaries, cost accounting, model/runtime manifests, typed errors, and terminal cleanup evidence. Keep all scientific arms on one allocation; do not tear down between them.

Before create, group the mutable checks: direct empty instance/disk inventory, L40S orderability, exact local model/tokenizer bytes, pinned container availability, and projected session cost. First paid arms after identity/model readiness are one methodology single request and the c1 load phase, so an incompatibility fails cheaply. Absolute provider deadline is 3,900 seconds and all-in spend cap is $1.00 including cleanup. This project is the sole provider-mutating owner. Any provider, identity, semantic, artifact, timeout, or cleanup failure stops without a second allocation.

## Analysis and decision contract

Report Artificial Analysis's current exact non-reasoning cache/input/output retail components and 7:2:1 blend, its campaign-token-mix retail cost, and this stack's productive plus sustainable all-in COGS under the same token mix. Separate single-request output speed from aggregate load throughput. Include measured allocation setup/recovery and state the batches or retained duration needed to amortize it; do not call productive-arm cost sustainable. Refresh the exact comparator page before the final report.

Use the fresh shared `research/factory/data/gpu_prices.json` L40S medium-term committed planning rate for the headline production COGS and its range for sensitivity. Keep the actual Nebius allocation rate only in experimental spend and measured-arm accounting; do not substitute on-demand, preemptible, or the observed experimental rate into the production base case.

Quality remains an explicit blocker: this session cannot make a quality-eligible or final provider-beating claim because the V35 BF16 route closed without a result. A complete session satisfies only graduation gates 2 and 3 and leaves gate 1 open. A valid report plus multi-arm retained bundle closes this project; do not continue into another GLM-4.7 optimization.

## Portfolio-changing result

A complete bundle supplies two of the campaign's three explicit graduation gates and makes the remaining blocker unambiguous. A methodology-matched result that loses to the exact non-reasoning comparator redirects the economic claim despite the internal c16 win. An operational failure closes this one-session route and must not trigger another controller or allocation lineage.

## Director live-recovery correction — Cycle 31

The launch handoff was stale. At `2026-07-15T13:27:17Z`, the named instance and disk were running but the remote host had no checkpoint directory, transfer process, vLLM server, workload, or GPU use; locally only the independent cleanup watchdog survived. The scientific controller did not outlive the researcher turn. This is setup-only exposure, not a methodology result.

Recover only the existing `computeinstance-e00mw8xa9r3agk1awx` / `glm47-aa-methodology-awq-20260715-boot` allocation before its fixed `2026-07-15T14:24:22Z` watchdog deadline. Do not call provider create or extend the deadline/budget. Start the already-tested transfer, server, methodology arms, archive, and cleanup either while attached through terminal completion or under a verified remote durable service whose exact process and artifact path are observable. Reuse the original spec and immutable inputs. If the remaining time cannot fit all required arms, if the existing resource disappears, or if any arm/artifact fails, allow verified watchdog cleanup and close without another allocation. Report useful GPU seconds separately from total provider exposure.
