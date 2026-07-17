# Final Gemma 4 tied ParallelLMHead measurement

## Decision question

Does the actual pinned-image BF16 `ParallelLMHead` for the exact Gemma 4 31B tied `5376→262144` projection leave enough service time for an economical L40S endpoint at background batches?

The two predecessor owners produced no GPU result. The first exposed missing create diagnostics; the second repaired that shared boundary and retained a deterministic `spec.hostname` rejection because its generated name contained uppercase `T`/`Z`. Authenticated inventory is empty. Earlier successful campaign L40S creates used lowercase names, including `gemma-l40s-fp8-corr-20260717t000000z`. This project changes only that provider request value and makes one final direct attempt; it is not another controller or readiness project.

## Immutable execution packet

- Target: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, text-only non-reasoning, TP=1.
- Image: `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`; observed vLLM `0.19.1.dev6+g6d4a8e6d2`.
- Shared controller: `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py`, SHA-256 `b29ab7bddf8022cf4ca0ec9ff9d6fbbb4b0dbed2311f7e8489571e37df594cad`.
- Scientific program: `../gemma_l40s_parallel_lm_head_component/vllm_parallel_lm_head_bench.py`, SHA-256 `de7f843a07e10322446a5e173ef60df7dc14763f0924102a2a612e34bdf0ab71`.
- Remote wrapper: `../gemma_l40s_parallel_lm_head_component/remote_parallel_lm_head_stage.sh`, SHA-256 `e7a947f9124541e387af448c4a11653f7040b45c78c2ebe9e036fd94f91ec255`.
- Passed final audit: `../gemma_l40s_parallel_lm_head_measurement_v2/artifacts/final-staged-audit-post-controller-20260717T064759Z.json`.
- Economic mapping: 358 decode steps; total request budgets 1.394581 seconds planning and 0.86329 seconds conservative.
- Provider shape/rate: `gpu-l40s-a`, `1gpu-8vcpu-32gb`, 100-GiB disk, preemptible VM `$0.7492/hour` plus disk `$0.0097222/hour`; production planning `$1.10/GPU-hour` with `$1.00–$1.25` range.

Exact-match these bytes before launch. Do not edit the shared controller, benchmark, wrapper, runtime identity, or science contract.

## One immediate provider owner

Generate a lowercase RFC-1123 instance/disk name such as `gemma-l40s-head-final-20260717t070000z`. Before create, mechanically inspect the final `build_create_command` argv and emit one compact pre-create artifact proving both `--name` and `--hostname` are identical, lowercase, at most 63 characters, and match `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$`; also verify authenticated empty inventory and the immutable hashes above. This is a same-project request check, not a new gate or owner.

Immediately launch the existing shared controller under one durable user-systemd owner plus its independent cleanup watchdog. Run the actual BF16 `ParallelLMHead` with deterministic activations and zero BF16 `[262144, 5376]` weights at M=1/2/4/8/16/32. Require all six rows, finite zero oracle, output consumption, CUDA-event and wall p50/p95, peak allocated/reserved memory, GPU telemetry, useful-GPU/setup seconds, concrete consumer/method sources, typed archive/manifest hashes, and provider create diagnostic.

Translate every row through 358 decode steps to per-batch and per-request head service time. Classify whether the head alone falsifies neither, only the conservative, or both economic envelopes. Attention, MLP, KV, scheduler, sampling, queueing, failures, reliability, and quality remain missing; this component cannot become an endpoint or quality claim.

Any terminal closes the project. There is no repair, second create, new controller, or project-local wrapper. Retrieve available typed artifacts and verify authenticated zero instances/disks.

## Adjacent-session disposition

Ranked follow-ups were rechecked: SGLang uses a different engine/image and H100, MTP uses a distinct H100/image, prefix/window/quality arms need a resident full checkpoint, and FP8/W4 consumer lines are closed or lack a ten-minute final-audited program. None can truthfully reuse this checkpoint-free vLLM/L40S session. Therefore no retained follow-up is authorized and cleanup begins immediately after the head terminal.

## Budgets

- Wall clock: 45 minutes.
- Provider exposure: 20 minutes maximum under one sequential owner.
- Compute: 0.34 L40S GPU-hours and 1 local CPU-hour.
- Storage: one 100-GiB provider disk; 4 GiB project-local retained artifacts and 2 GiB temporary; no shared `/tmp`.
- Spend: `$0.50` maximum including disk; exactly one create attempt.

Write the lowercase pre-create artifact, raw provider/stage artifacts, `artifacts/SUMMARY.json`, concise `RESEARCH_LOG.md`, and terminal `STATUS.json`.
