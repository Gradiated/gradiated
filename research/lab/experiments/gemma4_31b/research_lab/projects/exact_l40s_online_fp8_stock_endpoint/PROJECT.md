# Exact Gemma online-FP8 L40S stock endpoint

## Question

Can the exact pinned Gemma 4 31B checkpoint serve valid non-reasoning text through vLLM online FP8 on one L40S and sustain the campaign's 4,214/358 background mix above the `0.717061` planning-base market hurdle?

## Why now

The BF16 H200 launcher lineage closed after two pre-science ownership/transfer defects and yielded no endpoint evidence. Online FP8 is a materially different representation and L40S is a materially cheaper production candidate (`$1.10/GPU-hour` planning). The exact BF16 checkpoint is already verified locally; dynamic FP8 preserves exact source-checkpoint provenance while making one 48-GiB placement plausible. Known Gemma 4 online-FP8 corruption reports make raw semantic correctness the first scientific falsifier.

## Immutable inputs

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Verified checkpoint: `../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint`; checkpoint terminal SHA-256 `5f0765fa37f308e21d665571a92c29ba1998b22b5ee67d1edbfac103dafec481`; model-index SHA-256 `d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2`.
- Exact-image runtime: `vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`; use online `--quantization fp8`, BF16 activations, and a text-only max model length of 12,000.
- Workload packet: `../gemma_exact_cache_trace_contract/TRACE_PACKET.json`, SHA-256 `ccc559094ee612d5da11e771c2ebf8ac14046ad03b8ec7bd6ae165be25725d68`. Token IDs use `prompt: list[int]` and `add_special_tokens:false`; constructed block-aligned cacheability is 528/4214, and live hit/query deltas are mandatory.
- Economics: `../l40s_saturation_economic_gate/SATURATION_GATE.json`; strict planning-base hurdle `0.7170614380702235` completed primary requests/s at `$1.10/GPU-hour` planning, with production sensitivity `$1.00-$1.25/hour`.

## Proven execution path

Adapt the shared lifecycle in `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, whose L40S endpoint lineage produced complete PASS sessions and final cleanup in `allocations/nebius_l40s_vllm_awq_splits_ab_v28r1`. Reuse its provider creation, user-owned `/workspace` preparation, resumable `session_staging.transfer_checkpoint`, host/image bootstrap, independent watchdog, typed artifact retrieval, internal-manifest verification, and cleanup. Adapt only the exact Gemma image/model command and exact runner/trace. Do not build a new lifecycle/controller or use the closed H200 project wrapper.

## Scientific execution

1. Before create, mechanically exact-match the brief against the named checkpoint, image, trace, economics, and proven-launcher terminal. Render and audit the final program and a fresh lowercase provider argv; require a nonexistent owner output directory and authenticated empty inventory.
2. Launch one bounded durable user-systemd owner. If local staging, bootstrap, checkpoint transfer, model load, or execution can outlive the researcher response, preserve that correct work under the same owner/deadline; never kill/restart it for turn cadence.
3. After model load, run a small exact-greedy semantic/raw-output falsifier first. Capture raw response bytes, token IDs, finite values, repetition/degeneration indicators, server logs, and reload/failure state. A corrupt, repetitive, non-finite, or incomplete result closes the representation immediately after artifact retrieval and cleanup; it is not an endpoint throughput result.
4. On semantic pass, run the exact 4,214-input/358-output c1/c4/c8/c16 simultaneous ladder; c32 only on measured allocator/deadline headroom. Run the separate 10K/358 single stream. Capture TTFT, ITL/TPOT, queue/prefill/decode/cache metrics, exact request/response hashes, complete/failure/reload counts, continuous HBM/utilization/power, allocator state, provider/useful time, and all-in request-cost surfaces.
5. Compare completed primary request throughput to `0.7170614380702235 rps` planning-base and `1.1583551336753017 rps` conservative. Keep the 10K view separate. No production eligibility claim is allowed without later paired BF16 quality/features/reliability evidence.

## Adjacent retained arm

Checkpoint/image setup is expected to dominate scored time. Prepare the existing prefix-cache on/off packet before the owner ends. Run it sequentially on the same allocation/runtime/checkpoint only if the healthy baseline exposes every required raw metric, measured prefill wall share is at least `0.393755`, and the arm is start-ready within ten minutes without extending the absolute deadline. Otherwise record the trigger false and clean immediately. No other retained arm is authorized.

## Stop rules

- One provider allocation. A pre-science launcher/staging failure closes this project; do not open a repair wrapper or retry the same allocation geometry.
- Semantic corruption closes online FP8 after typed retrieval; do not run the full ladder.
- A valid endpoint below `0.7170614380702235 rps` closes L40S online FP8 for the planning-base market route at this workload.
- Always verify zero matching and total provider instances/disks after cleanup unless the one typed retained arm is actively running under the same owner/watchdog.

## Director amendment after the local owner terminal

The first systemd invocation failed before provider inventory/create because the project-local `artifacts/` parent did not exist. No allocation, provider second, watchdog, transfer, or GPU action occurred, so the one provider allocation remains unconsumed. Admit exactly one in-place no-provider owner-initialization correction under the original wall-clock/CPU/storage/spend limits. Create only the parent, keep the fresh owner output directory nonexistent, and replace the shallow audit with a final-program terminal that mechanically proves the complete semantic-first runner, per-arm atomic persistence, exact trace/API/cache counters, continuous telemetry, economics, same-session prefix trigger/false cleanup, shared lifecycle primitives, user-owned remote workspace, real lowercase create argv, and atomic retrieval/internal manifest. Provider mutation remains gated on that terminal plus fresh authenticated empty inventory. Any later pre-science failure after provider create closes with no repair or wrapper.

## Budgets

- Wall clock: 110 minutes including local audit and cleanup.
- Provider exposure: 80 minutes; compute: 1.34 L40S GPU-hours and 3 local CPU-hours.
- Storage: one 200-GiB provider disk, read-only reuse of the verified local checkpoint, and 12 GiB new project artifacts; no shared `/tmp`.
- Spend: `$2.00` aggregate maximum, one allocation.

## Handoff

Retain the delegation identity terminal, final-program audit, owner snapshot or typed blocker, raw semantic and endpoint artifacts, prefix disposition, cost/exposure, cleanup proof, concise `RESEARCH_LOG.md`, and terminal `STATUS.json`.
