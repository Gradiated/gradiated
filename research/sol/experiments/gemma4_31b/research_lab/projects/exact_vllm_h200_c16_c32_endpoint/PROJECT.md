# Exact vLLM H200 c16/c32 endpoint decision

## Decision question

Can pinned vLLM serve the exact Gemma 4 31B campaign workload on one H200 at c16 or c32 with valid text output, usable background completion latency, and sustainable complete-request throughput above the `2.094181-2.118591 requests/s` planning-base market gate?

The exact H200 CUDA-event component result closes c1/c4/c8: transformer linears plus the actual `ParallelLMHead` require `6.625177/1.691650/0.879517 seconds/request`, already above the whole-service ceiling. It preserves c16 at `0.442462` and c32 at `0.224770 seconds/request`, but omits prefill, attention/KV, scheduling, sampling, failures, and service overhead. This project directly measures those two surviving operating points; it is not another readiness or component successor.

## Mechanically bound inputs

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning, TP=1.
- Verified source checkpoint: `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint`; passing terminal SHA-256 `5f0765fa37f308e21d665571a92c29ba1998b22b5ee67d1edbfac103dafec481`, index SHA-256 `d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2`.
- Runtime: `vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, observed vLLM `0.19.1.dev6+g6d4a8e6d2`.
- Exact trace: `../gemma_exact_cache_trace_contract/TRACE_PACKET.json`, SHA-256 `ccc559094ee612d5da11e771c2ebf8ac14046ad03b8ec7bd6ae165be25725d68`. Use `prompt: list[int]`, `add_special_tokens:false`, 4,214/358, 535-token common prefix with at most 528 block-cacheable tokens plus live counters, and separate 10,000/358 c1.
- H200 gate: `../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json`, SHA-256 `3f4ce08c7e3a6649c18af99f14e0d48dcaf3979ac818462f7cf159cd9dab9afd`; production planning `$3.25/hour`, strict request cost `$0.000614287-$0.000621447`.
- Component terminal: `../h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json`, SHA-256 `9f12b3ae4c8d82176f0ec9b09845c6e97ab1f278a458bd023adcbe433fd004fe`; only c16/c32 survive.
- Shared checkpoint contract: `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/session_staging.py`, SHA-256 `e9c4ab2b5b52646c3ffac2f5c6165fc627adaccc1dc77fd2adc59b6e16318295`. Successful fresh validation returns explicit `pass:true`, `marker_reused:false`, payload count 8, and transfer count 9.
- Reuse the corrected endpoint science from `../exact_vllm_h200_transfer_view_endpoint/launch_transfer_view.py`, `../exact_vllm_h200_fixed_session_endpoint/trace_endpoint_runner.py`, and `vllm_fixed_session_owner.py`, plus the proven provider lifecycle; do not create a new framework.

The director-generated `artifacts/DIRECTOR_IDENTITY_ASSERTION.json` must pass before delegation.

## One durable owner and staging contract

One bounded user-systemd owner exclusively controls local view construction, provider create/spend, checkpoint transfer, the retained remote session, artifact retrieval, and cleanup, with an independent absolute watchdog. It constructs a unique zero-new-weight-byte hardlink view under `/root/workspace/.agents/runtime/gemma4-31b/<owner-name>/checkpoint`, writes the terminal-derived `model-files.sha256`, proves device/inode/size identity, and consumes the fixed shared validator's explicit record. Correct full hashing may outlive a response. Provider creation remains gated on a passing owner-local terminal, exact final-program behavioral audit, fresh authenticated empty inventory/rate/placement, and lowercase RFC-1123 argv. Do not use another project's mutable transfer view.

The final audit must bind all executable owner, lifecycle, runner, image, trace, and staging bytes and behavior: NVIDIA/Docker bootstrap; diagnostic `--entrypoint nvidia-smi`; server `--entrypoint vllm IMAGE serve`; immediate container-exit failure; exact token trace; semantic-first raw SSE/output IDs; continuous telemetry; atomic stopped-telemetry archives and hashes; per-request TTFT/ITL/queue/prefill/decode/wall/cache counters; provider/useful/cost accounting; and authenticated cleanup. Any typed pre-create failure or paid pre-semantic failure closes without another create.

## Scientific execution

Run one deterministic human-readable greedy semantic request first. Require served model identity, valid non-repetitive text, exact requested generation termination, raw response bytes/token IDs, finite metrics, and no reload/parser/stop failure. This is a corruption/smoke boundary, not production quality certification.

On pass, run the exact primary trace at c16. Require simultaneous start semantics, all 16 complete requests, exact 4,214 prompt and 358 output tokens per request, zero failures/reloads, complete raw arrays/hashes, cache query/hit deltas, TTFT/ITL/queue/prefill/decode/wall time, pooling/arrival latency, HBM/allocator, utilization/power, and completed-request throughput. Repeat enough bounded batches to distinguish warmup from stable throughput. Compare measured complete-request throughput and production-accounted cost with both planning-base thresholds.

Run c32 only when the c16 terminal is valid, measured allocator/HBM and queue/deadline headroom are safe, and c32 can improve the cost decision or establish the campaign's allowed latency-for-cost trade. Report completion latency and pooling delay; do not preserve an inherited interactive SLO. Run the separate exact 10K/358 c1 methodology comparator only after one valid primary group, and never apply the campaign-mix cost gate to it.

## Preregistered retained prefix arm

Prepare the existing `../prefix_cache_primary_mix_bound/PREFIX_ARM_PACKET.json` offline while the baseline runs. The baseline uses prefix caching on and the exact trace. `PREFIX_RESCUE_TRIGGER` requires a healthy c16 baseline with every raw cache/timing metric, measured prefill wall share `>=0.393755`, realized cache-hit accounting consistent with the 528-token maximum, a matched prefix-off restart start-ready within ten minutes on the same allocation/image/checkpoint/watchdog, deadline headroom, and either a plausible market-gate crossing or at least 5% sustainable-cost decision. Only then restart sequentially with `--no-enable-prefix-caching`, rerun the identical c16 trace, and compare matched on/off rows. Otherwise persist false and clean immediately. No MTP, SGLang, second allocation, or other retained arm is authorized.

## Budgets and terminal

- Wall clock: 120 minutes including local validation, provider work, retrieval, and cleanup.
- Provider exposure: 85 minutes; one allocation, no paid repair.
- Compute: 1.42 H200 GPU-hours and 4 local CPU-hours.
- Storage: zero-new-weight-byte local hardlinks, one 250-GiB provider disk, at most 14 GiB retained and 4 GiB project-local temporary; no shared `/tmp`.
- Spend: `$4.50` maximum including compute, disk, and other metered charges.

Write identity/view/final-program/preflight terminals, owner/watchdog snapshot, semantic/c16/c32/10K raw bundles, `PREFIX_RESCUE_TRIGGER` and conditional bundle if run, `artifacts/SUMMARY.json`, concise log/status, actual cost/exposure/useful time, and authenticated zero-resource cleanup or explicit live-owner handoff.
