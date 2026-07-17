# Current AWQ background frontier V2

## Question

On a fresh content-addressed GLM-4.7-Flash AWQ/vLLM/L40S identity, does cache-off c16 or c32 lower sustainable dollars per output token by at least 5% versus an adjacent c8 control under a reliable background-job envelope?

## Why it matters

The first control-rebase project stopped at an existence audit before provider creation. That audit verified all 20.17 GB of current AWQ weights, the actual tokenizer hashes, empty Nebius inventory, and the durable external controller, but treated a missing globally installed `transformers` module and absent fresh wrapper as terminal. Director inspection found a much shorter path: `campaign_100/nebius/vllm_batched_runner.py` already constructs an exact 8,192-token prompt inside the pinned runtime, calls vLLM `/v1/completions` with `prompt_logprobs`, captures semantic/quality evidence, and has focused unit tests. The historical `remote_vllm_awq_smoke.sh` wrapper—not the mechanism—hard-binds the invalid V21 hashes and old quality bundle.

No current GLM workload arm has run despite $0.813535908 of V31/V32 setup spend. A project-local wrapper and runner amendment followed immediately by one retained L40S session is now the shortest path to decision-relevant evidence.

## Relevant evidence

- `runnable_control_rebase/artifacts/PRECREATE_GATE_V1.json`: current AWQ revision `ab31d120...`, all 12 files and tokenizer bytes verified, fake external terminal passed, Nebius instance/disk inventories zero, no spend.
- `campaign_100/nebius/vllm_batched_runner.py`: working tokenizer-based 8K prompt construction, streaming 1K output measurement, vLLM prompt-logprob extraction, semantic checks, telemetry, and raw artifacts.
- `campaign_100/tests/test_nebius_vllm_batched_runner.py`: focused tests for prompt-logprob evidence and fixed-geometry frontier behavior.
- V21's throughput/cost and KV capacity are non-transferable historical priors. The new c8 arm is the only denominator.
- At the current $0.8581222/hour L40S-plus-disk rate, 397.279 output tok/s reaches the $0.60/M strong gate; Cloudflare's $0.88/M exact-model listing is an unmatched directional anchor.

## Scope

Implement and execute in one researcher turn. Do not repeat an audit asking whether a fresh adapter already exists. Create project-local V2 copies or thin wrappers around the retained vLLM controller, remote script, and batch runner; leave historical campaign artifacts unchanged. Remove the frozen V21 tokenizer/hash and old artifact bindings, bind the verified current AWQ/tokenizer files, and extend the runner to an adjacent c8/c16/c32 ladder. The missing global `transformers` package is not a terminal gate: use an isolated pinned environment or the already pinned runtime container to render and content-address the workload.

Before create, require only bounded executable checks that the researcher implements in this turn: current file/tokenizer hashes match `PRECREATE_GATE_V1`; the current tokenizer deterministically renders exactly 8,192 input tokens and a 1,024-token maximum output; c8/c16/c32 parsing and cost/reliability calculations pass focused tests; the existing vLLM prompt-logprob parser passes its fixtures; the project-local wrapper reaches a typed fake terminal; and authenticated Nebius inventory is empty. Retain the sources, tests, manifest, rendered prompt/token IDs, and their hashes. A genuine unsupported tokenizer/runtime or controller-test failure stops before spend; the absence of a pre-existing wrapper does not.

If those checks pass, create exactly one Nebius L40S under the proven independent systemd controller/watchdog, load the verified current AWQ checkpoint once, and run cache-disabled c8, c16, and c32 on the same server. Hold model/checkpoint/tokenizer/runtime, dtype, 65,536-token scheduler budget, generation, seed, prompt corpus, prefix-cache state, and server configuration fixed. Use a warm-up and at least two full batches per admitted concurrency. Admit c32 only after the live allocator/KV check; retain an OOM or admission rejection as its result rather than retrying.

Latency is a tradeoff. Require every admitted request to succeed without truncation or semantic error and each arm to terminate within 300 seconds; report TTFT, TPOT, queueing, and makespan without applying the historical interactive gate. Run the current 36-case development packet once through the existing chat and vLLM prompt-logprob route, retaining raw responses, token IDs, logprobs, category scores, and measured NLL. Do not import a historical BF16 threshold or inspect/generate a holdout. Because batching does not change weights or runtime, also require deterministic semantic/output equivalence across matched arm probes. If absolute quality is not yet calibrated, label all economics quality-conditional rather than suppressing the performance result.

Retain request rows, token counts, success/truncation state, throughput, latency distributions, scheduler/KV metrics, VRAM, utilization, power/energy, server logs, development-quality evidence, allocation/setup/load/useful/teardown time, effective provider rate, lifecycle overhead, and terminal cleanup. Report steady-state and full-session-amortized dollars per million output tokens separately.

Do not repair V21, use its hashes as gates, enable prefix caching, change kernels/weights/representation/runtime between arms, run H100, open a second allocation, or overlap another provider mutation. This project is sole provider owner for at most $1.00 all-in and 3,600 seconds. Arm cleanup before create and verify instance and disk absent through both direct-resource and inventory views.

## Available resources

Use the shared factory tools, `campaign_100`, current AWQ cache, `PRECREATE_GATE_V1.json`, the retained vLLM runner/tests, executable 36-case development packet, and durable Nebius lifecycle machinery. The external scan independently supports a fresh AWQ replay as its only promoted current candidate.

## Portfolio-changing result

Promote c16 or c32 as the current operating point only if it is reliable, development-quality-equivalent, and lowers matched steady-state cost by at least 5% versus the new c8 control. Report <=$0.60/M separately. A valid c8 with no winning candidate closes batching scientifically and becomes the content-addressed control for a later mechanism. Any comparison to V21 is prohibited; being below Cloudflare's $0.88/M listing is directional until a matched provider/quality comparison exists. A genuine runtime/load/workload falsifier completes the project, but another missing-wrapper or missing-global-package report does not.

## Cycle 18 continuation

The adapter, current tokenizer, exact 8K/1K workload, and four focused tests now pass. The first bounded attempt created no resource and cost a derived $0.00018174, but left two distinct untyped controller observations: the retained outer `controller.stderr.log` invokes nonexistent `/root/research/.../frontier_v2.py`, while the inner events record `instance create failed with exit 3` and discard provider stdout/stderr. Neither is a provider or scientific result.

Use one final researcher turn to fix observability and, if safe, execute. First correct the external systemd launch target to the actual project path and bind the launched source hash. In the project-local controller, retain bounded credential-redacted create command diagnostics—stage, return code, stdout, and stderr—before raising. Prove both layers with a no-create failing fixture. Then reconcile fresh direct instance/disk inventory.

If the fixture passes and inventory is empty, make exactly one final create attempt under at most $0.65 incremental exposure and 2,700 seconds, still inside the $1.00 project cap. A successful create proceeds immediately through the already admitted c8/c16/c32 experiment and cleanup. A typed capacity, quota, permission, request, or provider failure closes this Nebius attempt without retry or repair. Any nonzero command must name its retained diagnostic artifact; another missing diagnostic is terminal for this project. No other project may mutate a provider concurrently.
