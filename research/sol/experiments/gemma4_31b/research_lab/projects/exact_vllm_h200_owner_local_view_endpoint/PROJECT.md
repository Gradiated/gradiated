# Exact Gemma 4 vLLM H200 with owner-local transfer view

## Decision question

Can pinned vLLM serve the exact Gemma 4 31B campaign workload on one H200 at the 2.094181–2.118591 planning-base market gate when the durable owner constructs and validates its own transfer view immediately before provider creation?

The previous direct owner passed its corrected lower-program audit, user watchdog, H200 create, SSH, and remote session ownership, but a validated transfer view stored under a different closed project disappeared before staging and later reappeared during a bulk workspace rewrite. That mutable cross-project dependency is closed. This project uses the same corrected scientific program and shared provider lifecycle, but constructs a storage-free hardlink view under `/root/workspace/.agents/runtime/gemma4-31b/<owner-name>/checkpoint` inside the sole durable user owner. It does not create a controller framework or depend on another project's mutable artifacts.

## Mechanically bound inputs

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning.
- Source checkpoint and passing terminal: `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint` and its `CHECKPOINT_TERMINAL.json`.
- Runtime: `vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`.
- Exact trace: `../gemma_exact_cache_trace_contract/TRACE_PACKET.json`; 4,214/358 primary c1/c4/c8/c16, exact 535-token common prefix with at most 528 cacheable tokens/live counters, and separate 10,000/358 c1.
- Corrected program sources: `../exact_vllm_h200_transfer_view_endpoint/launch_transfer_view.py` (its rendered `corrected_remote`) and `../exact_vllm_h200_fixed_session_endpoint/trace_endpoint_runner.py` plus `vllm_fixed_session_owner.py`.
- Hardware: Nebius `gpu-h200-sxm`, `1gpu-16vcpu-200gb`, one 250-GiB disk. Experiment rate is refreshed at launch; production planning remains `$3.25/hour`, market cost `$0.000614287–$0.000621447`.
- Conditional SGLang image: `docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427`.

The director-generated `artifacts/DIRECTOR_IDENTITY_ASSERTION.json` must pass before delegation.

## One durable owner and pre-create contract

Use one user-systemd owner for local view construction, all provider mutation/spend, the remote retained session, and cleanup. The owner creates a unique run-local view under `.agents/runtime`, hardlinks every checkpoint-terminal file from the raw checkpoint, writes `model-files.sha256` from the terminal rows, proves same device/inode and exact sizes, runs shared `session_staging.checkpoint_files()` plus `validate_local_files_cached()`, and atomically writes `artifacts/RUN_LOCAL_VIEW_TERMINAL.json`. Correct full hashing may outlive a response. Do not stop or restart it for turn cadence.

Provider creation is inside that same owner and remains mechanically gated until the run-local terminal passes, the corrected rendered lower program passes a behavioral audit, and current authenticated empty inventory/rate/placement pass. Recheck `model-files.sha256`, hardlink identity, and the cached-integrity marker immediately before calling create and again immediately before `transfer_checkpoint`. Do not use any cross-project transfer view. Local runtime hardlinks add zero weight-storage bytes and are removed only after remote transfer or terminal cleanup; retain their typed manifest in project artifacts.

The rendered audit must inspect actual behavior: proven Docker/NVIDIA-container bootstrap; diagnostic `--entrypoint nvidia-smi`; server `--entrypoint vllm IMAGE serve`; immediate container-exit readiness failure; one semantic c1 merged into the scored ladder rather than replayed; exact c4/c8/c16 and 10K; EXIT-trapped logs/metrics; stopped telemetry before atomic tar/checksum retrieval; per-token/ITL, queue/prefill/decode, provider/useful/cost accounting; user owner/watchdog; authenticated cleanup; and a real sequential conditional SGLang branch.

## Scientific execution

Run semantic c1 first and require exact 4,214 prompt/358 output counts, served identity, terminal stream, raw SSE/output IDs, and no parser/stop/reload failure. Then run c4/c8/c16 and separate 10K/358, retaining exact request arrays/hashes, raw responses, complete requests, failures/reloads, TTFT/ITL/queue/prefill/decode/wall time, cache query/hit deltas, HBM/allocator, continuous GPU utilization/power, provider/useful seconds, and actual cost.

Prepare SGLang while vLLM runs. `VLLM_MARKET_TRIGGER` requires semantic/raw validity, zero failures/reloads, stable c8 or c16 throughput `>=2.094181` rps, SGLang start-ready within ten minutes, and deadline headroom. Only then run it sequentially on the same checkpoint/allocation/watchdog; otherwise persist false and clean up immediately. Keep primary and 10K economics separate. No production-quality, vision, reasoning, or full OpenRouter claim is authorized.

## Budgets and terminal

- Wall clock: 130 minutes including local hashing, provider work, retrieval, and cleanup.
- Provider exposure: 90 minutes; one allocation and no paid repair.
- Compute: 1.5 H200 GPU-hours and 3 local CPU-hours.
- Storage: zero-new-weight-byte run-local hardlinks, one 250-GiB provider disk, at most 12 GiB project artifacts; no shared `/tmp`.
- Spend: `$4.00` including compute, disk, and other metered charges.

Write the run-local view terminal, corrected final audit, provider preflight, owner/watchdog snapshot, endpoint bundle, `VLLM_MARKET_TRIGGER`, conditional bundle if run, `artifacts/SUMMARY.json`, concise log/status, and authenticated zero-resource cleanup or explicit live-owner handoff. Any new typed pre-create failure or paid pre-semantic failure closes.
