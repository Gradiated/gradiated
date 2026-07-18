# H100 actual head then conditional linears — native two-stage direct floor

## Decision

Measure actual pinned-vLLM BF16 `ParallelLMHead` at Gemma 4 31B geometry on H100, then run exact BF16 transformer linears only if the head leaves H100 economics open and setup amortization warrants the same retained session.

This is a native two-stage scientific design, not a controller extension or repair of FP8/W4/paged KV. Exact identity is `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, vLLM `0.19.1.dev6+g6d4a8e6d2`, H100 capability 9.0, workload 4,214 prompt / 358 output / 12.7% cache, ceiling `0.5479752315195353 s/request`.

Stage 1 uses the actual `ParallelLMHead` with vocab 262,144 and hidden 5,376. Run M8 first, atomically persist its typed row, then M16/M32; any later failure archives the partial typed stage. Require varied-sign nonzero BF16 tensors, actual consumer/source identity, output consumption, finite/nontrivial oracle, CUDA-event p50/p95, synchronized wall diagnostics, allocator, and interval-scoped telemetry. Head floor is `p50_ms / 1000 * 358 / M`.

Stage 2 is the sole adjacent arm, `H100_HEAD_PASS_AND_PRIOR_SETUP_DOMINATES_AND_LINEAR_READY`: all head rows pass; at least one c8/c16/c32 head floor is below the ceiling; authenticated prior H100 terminals show >500 seconds exposure versus <5 scored CUDA seconds; the exact six-shape M8/M16/M32/M3679 linears are staged and content-bound; and at least seven provider minutes remain. Run exactly 24 rows, preserve them atomically, and combine matching head/linear floors. False trigger cleans immediately.

The launch researcher must render and behaviorally audit the final immutable head, linear, wrapper, owner, trigger, telemetry, archive, accounting, and cleanup bytes before create. No separate final-program audit is planned; the launcher's typed behavioral pre-create terminal is the sole audit and must pass. Reuse one sequential `VerifiedRetainedOwner` plus user-systemd owner/watchdog. One H100, one 100-GiB disk, no checkpoint, one allocation, zero repair/restart.

Budgets: 28 wall minutes; 18 provider minutes; 0.31 H100 GPU-hours plus 2 CPU-hours; 1 GiB retained plus 512 MiB temporary; `$1.10` maximum. Terminal separates setup, scored CUDA, exposure, cost, and authenticated zero-resource cleanup.
