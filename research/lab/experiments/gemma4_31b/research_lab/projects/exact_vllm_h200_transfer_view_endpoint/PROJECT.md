# Exact Gemma 4 vLLM H200 from verified transfer view

## Question

Can pinned vLLM serve the exact Gemma 4 31B campaign workload on one H200 at the 2.094181–2.118591 planning-base market gate when the already successful, content-bound checkpoint transfer view is used directly?

The preceding fixed-session owner proved user-scope watchdog, H200 create, SSH, and remote workspace ownership, then failed only because it pointed shared staging at the raw checkpoint directory, which lacks `model-files.sha256`. The earlier successful 62,578,655,922-byte transfer left `../exact_h200_vllm_baseline_shared_runner/artifacts/corrected-transfer-view`: every payload file is a storage-free hardlink to the passing exact checkpoint and its manifest is derived from that terminal. Use this view; do not alter the shared controller or create another transfer wrapper.

## Bound inputs and pre-create gate

- Exact model/revision: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Raw checkpoint terminal: `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/CHECKPOINT_TERMINAL.json`.
- Transfer view: `../exact_h200_vllm_baseline_shared_runner/artifacts/corrected-transfer-view`, including `model-files.sha256`.
- Runtime: `vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`.
- Exact trace: `../gemma_exact_cache_trace_contract/TRACE_PACKET.json`, primary 4,214/358 c1/c4/c8/c16 with exact 535-token common prefix/live cache counters, plus separate 10,000/358 c1.
- H200 economics: `../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json`; production planning `$3.25/hour`, strict market cost `$0.000614287–$0.000621447`, required planning-base throughput 2.094181–2.118591 completed requests/s.
- Hardware: Nebius `gpu-h200-sxm`, `1gpu-16vcpu-200gb`, one 250-GiB disk.
- Program/lifecycle: consume `../exact_vllm_h200_fixed_session_endpoint/trace_endpoint_runner.py` and `vllm_fixed_session_owner.py`, changing only the checkpoint source to the bound transfer view. Preserve the passing user-owner/watchdog, entrypoint override, remote ownership, exact trace, telemetry, and cleanup program.

`artifacts/DIRECTOR_IDENTITY_ASSERTION.json` must pass. Before provider create, one bounded local integrity owner may run shared `session_staging.checkpoint_files()` and `validate_local_files_cached()` against the transfer view and checkpoint-terminal rows, emitting `artifacts/TRANSFER_VIEW_TERMINAL.json`. It may outlive a response; do not stop or restart correct hashing. Provider create remains gated until that typed terminal, the actual final-program audit, current authenticated empty inventory, and current H200 rate/placement pass. The final audit must verify the actual lower argv binds the transfer view, user-scope owner/watchdog health, lowercase name, explicit diagnostic entrypoint, semantic-first stop, exact trace/concurrency, atomic retrieval, continuous telemetry, budgets, conditional trigger, and cleanup.

## Execution

Use one durable user-systemd owner, one independent user-systemd watchdog, one allocation, and no paid repair. Run one semantic primary c1 first; require exact 4,214 prompt/358 output counts, served identity, terminal stream, raw SSE/output IDs, and no parser/stop/reload failure. Then run c1/c4/c8/c16 and separate 10K/358. Retain request arrays/hashes, raw outputs, complete requests, failures/reloads, TTFT/ITL/queue/prefill/decode/wall time, live cache query/hit deltas, HBM/allocator, continuous GPU utilization/power, provider/useful seconds, and actual cost.

Prepare the already bound SGLang BF16+FP8-E5M2-KV program offline while vLLM runs. `VLLM_MARKET_TRIGGER` requires valid raw/semantic telemetry, no failures/reloads, stable c8 or c16 throughput `>=2.094181` rps, SGLang start-ready within ten minutes, and deadline headroom. Only then run it sequentially on the same resident checkpoint/allocation/watchdog; otherwise record false and clean up immediately. The conditional image is `docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427`.

Keep primary and 10K economics separate. Raw validity is required; no production quality, vision, reasoning, or full OpenRouter claim is authorized.

## Budgets and terminal

- Wall clock: 130 minutes, including bounded local integrity work and cleanup.
- Compute: 1.5 H200 GPU-hours and 3 local CPU-hours.
- Provider exposure: 90 minutes, one allocation.
- Storage: read-only hardlink transfer view, one 250-GiB provider disk, at most 12 GiB project artifacts, no shared `/tmp`.
- Spend: `$4.00` including compute, disk, and other metered charges.

Write the transfer-view terminal, final audit, owner/watchdog snapshot, endpoint bundle, `VLLM_MARKET_TRIGGER`, conditional bundle if run, `artifacts/SUMMARY.json`, concise log/status, and authenticated zero-resource cleanup or explicit live-owner handoff.
