# Exact Gemma 4 vLLM H200 endpoint after shared-session fix

## Question and evidence

Can the pinned exact Gemma 4 31B BF16 checkpoint serve the campaign workload through pinned vLLM on one H200 at or above the 2.094181–2.118591 planning-base market gate, with valid raw outputs and complete endpoint telemetry?

Prior exact-vLLM H200 work transferred all 62,578,655,922 checkpoint bytes in 946.696 seconds, then failed before image pull because the remote session parent was root-owned. Shared `session_staging.py` now establishes the dedicated `glmrunner` parent/target before transfer. The immediately preceding SGLang allocation failed before SSH because a system-scope owner tried to launch a user-scope watchdog. Neither failure is model science. This direct project reuses the prior exact rendered vLLM runner and the proven user-systemd owner/watchdog scope; it does not build another controller framework.

Authoritative identities are mechanically asserted in `artifacts/DIRECTOR_IDENTITY_ASSERTION.json`:

- `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4` and read-only checkpoint `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint`.
- `vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`.
- `../gemma_exact_cache_trace_contract/TRACE_PACKET.json`: exact 4,214/358 token-ID c1/c4/c8/c16 groups, 535-token common prefix with at most 528 cacheable tokens and live counter deltas, plus separate 10,000/358 c1.
- Nebius `gpu-h200-sxm`, `1gpu-16vcpu-200gb`, one 250-GiB disk; production planning `$3.25/hour`, experiment preemptible rate measured separately.
- Prior exact program: `../exact_h200_vllm_baseline_shared_runner/gemma_exact_vllm_runner.py` and `vllm_h200_owner.py`. Consume its exact trace/telemetry logic and the shared lifecycle/session-staging fixes; do not reopen its old project or repeat its raw-SCP/root-owned paths.

## Required execution

Use one user-systemd durable owner and one independent user-systemd watchdog for all provider mutation, spend, retained content state, and cleanup. Local response cadence does not bound checkpoint transfer, image pull, compilation, model load, or scoring. The owner may outlive a response under its absolute deadline. Provider create requires a passing final-program audit, current authenticated empty inventory and H200 rate/placement, the passing director identity assertion, a fresh owner-created output directory under the existing project `artifacts/` parent, and a confirmed user-manager environment that can launch and observe the watchdog. Any paid pre-semantic failure closes after cleanup; no paid repair or second allocation.

The actual lower program/argv audit must prove: user-scope owner/watchdog and their typed health snapshot; lowercase RFC-1123 names; shared diagnostic create reconciliation and SSH/session staging; `sudo install -d -o glmrunner -g glmrunner` session parents before transfer; explicit Docker `--entrypoint` override for `nvidia-smi`/diagnostic commands; pinned image/checkpoint; exact trace token arrays and true simultaneous barriers; semantic-first stop; atomic vLLM persistence/retrieval; continuous telemetry; budgets; and authenticated cleanup.

Run one exact primary c1 semantic request first. Require served-model identity, stream terminal, exactly 4,214 prompt and 358 output tokens, raw SSE and returned output IDs where exposed, and no parser/stop/reload failure. On pass, run c1/c4/c8/c16 and the separate 10K/358 c1 view. Retain raw submitted token arrays/body hashes, raw responses/output IDs, complete requests, failures/reloads, prefill/decode/request wall time, TTFT, ITL, queueing, live cache query/hit deltas, HBM/allocator state, continuous GPU utilization/power, provider-active/useful-GPU seconds, and actual GPU/disk/other cost.

Because measured checkpoint/bootstrap setup dominates scoring, prepare a packet-bound SGLang BF16+FP8-E5M2-KV comparator locally while the vLLM owner runs. Its immutable image is `docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427`. `VLLM_MARKET_TRIGGER` passes only if semantic/raw telemetry gates pass, there are no failures/reloads, a stable c8 or c16 point reaches 2.094181 completed requests/s, the exact SGLang image/program can start within ten minutes on the same resident checkpoint/allocation, and the owner deadline remains sufficient. Only then run SGLang sequentially on the same allocation and watchdog; otherwise persist the failed trigger and clean up immediately. Do not retain for any other arm. This conditional arm uses `../sglang_gemma4_exact_precreate_binding/START_PACKET.json` and is not required to establish the vLLM endpoint result.

Report the primary campaign mix against the strict market request-cost range `$0.000614287–$0.000621447` using completed requests and measured all-in factors. Keep the 10K single stream separate. Raw-output validity is required, but no production-quality, vision, reasoning, or full OpenRouter eligibility claim is authorized.

## Budgets and terminal

- Wall clock: 130 minutes including rendering, retained owner, retrieval, and cleanup.
- Provider exposure: 90 minutes; one allocation, 1.5 H200 GPU-hours.
- Local compute: 3 CPU-hours.
- Storage: reuse verified checkpoint read-only; one 250-GiB provider disk; at most 12 GiB retained project artifacts; no shared `/tmp`.
- Spend: `$4.00` including compute, disk, and other metered charges.

Write the final audit, owner/watchdog snapshot, atomic vLLM bundle, `VLLM_MARKET_TRIGGER`, conditional SGLang bundle only if run, `artifacts/SUMMARY.json`, concise log, and terminal status. Terminal cleanup requires authenticated zero named instances/disks or an explicit still-live owner/watchdog handoff.
