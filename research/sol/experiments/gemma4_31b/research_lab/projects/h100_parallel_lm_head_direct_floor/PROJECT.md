# H100 actual ParallelLMHead direct component floor

## Decision question

Does the actual pinned-vLLM BF16 `ParallelLMHead` for Gemma 4 31B's tied 262,144×5,376 vocabulary projection already falsify H100 economics at c8/c16/c32, and if it leaves points open, do exact BF16 transformer linears close them on the same retained session?

This is a materially different compulsory tied-head primary, not a retry of FP8, W4, paged KV, or the closed linears-first project. Reuse the actual consumer program proven on H200/L40S, the exact pinned image, and the proven H100 user-systemd lifecycle. No checkpoint, endpoint, or quality claim.

## Identity and primary

`assert_identity.py` mechanically binds campaign bytes, the reconciled H200 actual-head result and program, the H100 economic ceiling, prior H100 cleanup, and this brief. Exact identity is `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, vLLM `0.19.1.dev6+g6d4a8e6d2`, `NVIDIA H100 80GB HBM3` capability 9.0, 4,214 prompt / 358 output / 12.7% cache, and `0.5479752315195353 s/request`.

Primary constructs the actual `vllm.model_executor.layers.vocab_parallel_embedding.ParallelLMHead` with vocab 262,144 and hidden 5,376; deterministic varied-sign nonzero BF16 weight/input; output consumption and finite/nontrivial oracle; M8 sentinel atomically retrieved before M16/M32 rows; repeated CUDA-event p50/p95 plus synchronized wall diagnostics; allocator and interval-scoped telemetry. Head floor is `cuda_event_p50_ms / 1000 * 358 / M` and is compared directly with the H100 ceiling. Any identity, source, consumer, oracle, timing, telemetry, or sentinel failure stops and cleans.

## Adjacent same-session arm

Before create, stage the already rendered exact BF16 six-shape M8/M16/M32/M3679 program from `h100_bf16_exact_linear_head_floor`. The controller's second and final stage first runs M16/M32 head rows and atomically persists their typed head artifact; only then may that same stage execute linears under `H100_HEAD_SURVIVES_AND_HISTORICAL_SETUP_DOMINATES_AND_LINEAR_READY`: all head rows pass; at least one c8/c16/c32 head floor is below the ceiling; authenticated prior H100 terminals prove >500 seconds allocation/setup-dominated exposure while scored component CUDA is <5 seconds; final linears bytes pass the same independent pre-create audit; and at least seven provider minutes remain. Retrieve exactly 24 rows and combine matching head/linear floors. A false trigger preserves the head artifact and cleans immediately; a later linear failure cannot erase the already persisted head rows. No other arm.

## Audit and lifecycle

Render all head, conditional-linear, wrapper, owner, trigger, telemetry, accounting, archive, and cleanup bytes once. A separate independent audit of those immutable bytes is mandatory before provider create; its terminal must be consumed by the director. The launch researcher may not create while that audit is pending or planned. After audit pass, reuse one sequential `VerifiedRetainedOwner` and one user-systemd owner/watchdog, with one allocation and no repair/restart.

## Budgets

- Wall clock: 35 minutes total, including render and audit.
- Provider exposure: 20 minutes.
- Compute: 0.34 H100 GPU-hours plus 2 local CPU-hours.
- Storage: one 100-GiB provider disk; 1 GiB retained plus 512 MiB temporary.
- Spend: `$1.30` maximum at actual provider-metered rates.
- One allocation; zero repair/restart.

Terminal must separate setup, scored CUDA, provider exposure, derived cost, and authenticated zero-instance/zero-disk cleanup.
