# H100 actual ParallelLMHead single-stage measurement

## Question

What is the actual H100 tied-head component floor for exact Gemma 4 31B, using the already successful pinned-image `ParallelLMHead` program unchanged except accelerator placement?

Reuse byte-for-byte scientific program `../gemma_l40s_parallel_lm_head_component/vllm_parallel_lm_head_bench.py` and wrapper `remote_parallel_lm_head_stage.sh`, proven by `../gemma_l40s_parallel_lm_head_measurement_final`. Change only controller placement to H100. Exact identity: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, vLLM `0.19.1.dev6+g6d4a8e6d2`, H100 capability 9.0, 262,144×5,376 head, 358 output tokens, H100 ceiling `0.5479752315195353 s/request`.

Run the proven six M=1/2/4/8/16/32 rows with actual consumer/source identity, finite output oracle, CUDA/wall timings, allocator and telemetry; translate each as `p50_ms / 1000 * 358 / M`. One single retrieved stage, no conditional.

Adjacent-arm disposition is preregistered before create: none is start-ready within ten minutes. Both exact-linear candidates ended in typed pre-create blockers (`h100_bf16_exact_linear_head_floor/PRECREATE_BLOCKER.json` and `h100_head_two_stage_direct_floor/PRECREATE_BLOCKER.json`), so retention trigger is always false and cleanup follows primary immediately.

The launch researcher's behavioral pre-create audit is sufficient; no separate audit is pending or planned. Its sole prior failure was a local audit-harness false negative: the real rendered argv binds the benchmark as `MICROBENCH_PATH=/input/<benchmark>`, while the predicate required the filename as a standalone argv element. Correct only that predicate in this same project, rerun the local audit, and create immediately if it passes.

Use one user-systemd durable owner, one H100/100-GiB disk, no checkpoint, and one retained mutable development session. After create, set `STATUS.json.active_session.mode` to `development` and keep the same researcher attached as the exclusive provider/spend owner. Repair ordinary import, path, permission, runtime-context, API, benchmark, and telemetry defects in place while the program identity, scientific question, hardware/image, watchdog, deadline, and spend cap remain intact. The exact-runtime first call is the discovery audit. Do not create a repair/audit/successor project for an operational correction, and do not tear down a correct long-running program merely to fit a researcher response boundary. Stop for a scientific endpoint, unsafe or unintelligible state, required hardware/image change, exhausted budget, or a clearly faster route to evidence.

No adjacent arm is currently start-ready. If a decision-relevant, checkpoint-free arm compatible with the resident image/runtime becomes ready within ten minutes while setup materially dominates scored GPU time, preregister it and run it sequentially under the same owner; otherwise clean up after the head result.

Continuation budget from the 2026-07-17 director reopen (prior provider spend/exposure: zero): 30 wall minutes; 20 provider minutes; 0.34 H100 GPU-hours plus 1 CPU-hour; one 100-GiB disk; 1 GiB retained plus 512 MiB temporary; `$1.30` maximum.
