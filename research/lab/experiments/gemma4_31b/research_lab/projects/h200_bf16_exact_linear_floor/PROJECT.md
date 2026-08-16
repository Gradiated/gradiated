# H200 exact BF16 transformer-linear economic floor

## Decision question

Does the architecture-weighted decode cost of the exact Gemma 4 31B BF16 transformer linears alone falsify one-H200 economics for the campaign workload, before attention, KV, scheduling, sampling, prefill, and the tied vocabulary head are added?

Several consecutive checkpoint-backed endpoint owners ended before model science because of staging and launcher defects. This project is the shortest target-GPU falsifier that preserves the exact model geometry and H200 economic question while eliminating checkpoint transfer entirely. It is component evidence, not an endpoint, quality, or complete latency claim.

## Mechanically bound identity and geometry

- Target: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning, TP=1.
- Primary workload: 4,214 input / 358 output with 12.7% prompt cache; batch/concurrency points M=1/4/8/16/32.
- Runtime image: `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, observed vLLM `0.19.1.dev6+g6d4a8e6d2`.
- Hardware: one Nebius `gpu-h200-sxm`, `1gpu-16vcpu-200gb`; current experiment reference `$2.45/GPU-hour`, production planning `$3.25/GPU-hour` with `$2.925-$3.60` range.
- Source geometry: 60 layers, 50 sliding and 10 global, hidden 5,376, intermediate 21,504. Measure exact BF16 activation/weight linears:
  - 50 sliding QKV: `5376 -> 16384`
  - 10 global QKV: `5376 -> 20480`
  - 60 gate/up: `5376 -> 43008`
  - 50 sliding output: `8192 -> 5376`
  - 10 global output: `16384 -> 5376`
  - 60 down: `21504 -> 5376`
- Market gate: strict request cost `$0.000614287-$0.000621447`; planning-base H200 threshold `2.094181-2.118591 completed requests/s`, hence at most `0.477514-0.471012 seconds/request` for the entire service.

The director-generated `artifacts/DIRECTOR_IDENTITY_ASSERTION.json` must pass before delegation. Authoritative inputs are `../exact_geometry_runtime_opportunities/GEOMETRY.json`, `../gemma_l40s_w4_c16_economic_bound/W4_COMPONENT_PACKET.json`, `../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json`, and `../gemma_l40s_parallel_lm_head_measurement_final/artifacts/gemma-l40s-head-final-20260717t065653z/summary.json` plus its provider request.

## Immediate H200 experiment

Use the proven shared Nebius lifecycle in `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py` and `placement_control.py`; do not create another provider framework. One bounded user-systemd owner exclusively controls create, spend, the sequential remote session, retrieval, and cleanup, with an independent absolute watchdog. Provider creation is gated on one final staged-program behavioral audit, a lowercase RFC-1123 request, authenticated empty inventory, current H200 placement/rate, and diagnostic Docker/NVIDIA runtime bootstrap. Local program preparation may outlive a model response; do not kill correct work for turn cadence.

Within the pinned image, allocate deterministic BF16 tensors and run the actual CUDA `torch.matmul`/linear consumer for all six shapes at M=1/4/8/16/32. Use bounded warmup and repeated trials, CUDA events plus synchronized wall time, deterministic consumed outputs, finite/numerical checks, allocator peaks, and continuous `nvidia-smi` utilization/power/memory telemetry. Record exact torch/CUDA/GPU identity and the called consumer. A synthetic zero/random weight tensor is permitted because this tests cost mechanism only; no quality inference is allowed. Avoid timing allocation, random generation, or host-device construction as kernel service.

For each M, compute the decode-step wall floor:

`50*t(sliding_qkv) + 10*t(global_qkv) + 60*t(gate_up) + 50*t(sliding_out) + 10*t(global_out) + 60*t(down)`.

Translate it to request seconds as `358 * step_seconds / M`. Report CUDA-event and wall formulations separately, with wall as the primary floor. Compare with both planning-base frontier endpoints. Because linears can execute serially and this omits other service work, a miss falsifies BF16 H200 economics; a pass only preserves the candidate.

## Preregistered adjacent same-session arm

Prepare, while the primary owner runs, the already proven actual vLLM `ParallelLMHead` program from `../gemma_l40s_parallel_lm_head_component/vllm_parallel_lm_head_bench.py` for M=1/2/4/8/16/32. It must reuse the same live H200 allocation, pinned image, sequential owner/watchdog, and only content-bound runtime state. Do not create another allocation or download a checkpoint.

`H200_HEAD_TRIGGER` is true only if all primary rows are valid, the architecture-weighted transformer-linear wall floor at M=16 or M=32 is at most 120% of the stricter `0.471012 s/request` ceiling and the H200 head result could change the economic classification, the existing head program is start-ready within ten minutes, and wall/provider deadlines leave room. If true, run the actual `vllm.model_executor.layers.vocab_parallel_embedding.ParallelLMHead` sweep sequentially, retain its raw rows, and add the measured head time to the transformer floor. If false, persist the typed trigger and clean up immediately. This arm inherits no L40S latency value; only its exact consumer/program identity transfers.

## Budgets and terminal contract

- Wall clock: 70 minutes including program audit, create, measurement, optional head, retrieval, and cleanup.
- Provider exposure: 30 minutes maximum; one allocation, no paid repair.
- Compute: 0.5 H200 GPU-hours and 3 local CPU-hours.
- Storage: one 100-GiB provider disk; at most 6 GiB retained project artifacts and 2 GiB project-local temporary; no shared `/tmp` and no checkpoint weights.
- Spend: `$1.50` maximum including GPU, disk, and other metered charges.

Any pre-GPU terminal or malformed/zero-row science closes the project without another create. Retrieve atomically hashed raw measurement, telemetry, program/source, environment, trigger, cost/exposure, and cleanup artifacts. Write `artifacts/SUMMARY.json`, concise `RESEARCH_LOG.md`, terminal `STATUS.json`, and authenticated zero-resource cleanup or an explicit live-owner handoff.
