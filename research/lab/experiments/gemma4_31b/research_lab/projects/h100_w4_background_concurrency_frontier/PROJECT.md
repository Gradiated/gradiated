# H100 W4-Machete background-concurrency frontier

## Decision question

Can higher background concurrency amortize the exact Gemma 4 31B H100 W4-Machete transformer linears and actual tied head enough to reopen a credible service-time margin below `0.5479752315195353 s/request`, despite c32 being closed by measured local attention?

This is a materially different scheduling/load-shape hypothesis, not a repair of the c32 global-attention harness. The campaign explicitly permits latency-for-cost tradeoffs for background-agent traffic. Measure c48/c64/c96/c128 rather than inheriting c32 as a fixed operating point.

## Bound evidence and scope

- Exact model/workload: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, 4,214 prompt tokens, 358 output tokens, 12.7% prompt cache reads.
- Exact image: `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`.
- Actual H100 Machete W4 c8/c16/c32 terminal: `../h100_w4_marlin_direct_falsifier/artifacts/RECONCILED_MACHETE_TERMINAL.json`.
- Actual H100 `ParallelLMHead` terminal: `../h100_parallel_lm_head_single_stage/artifacts/gemma-h100-head-dev-20260717t1953z/RECONCILED_TERMINAL.json`.
- c32 economic closure: `../h100_w4_machete_fp8kv_residual_falsifier/artifacts/C32_ECONOMIC_CLOSURE.json`. Its valid local row is a c32 result only and must not be transferred to higher concurrency.

`BINDINGS.json` mechanically binds these identities. This is a checkpoint-free execution proxy: it may decide component economics and the next attention arm, but it cannot establish checkpoint quality, full-request throughput, memory residency, reliability, or endpoint eligibility.

## Direct experiment

Use one H100 SXM, TP=1, and the proven retained Nebius development lifecycle. Reuse `../h100_w4_marlin_direct_falsifier/h100_w4_marlin_tp_single_rank.py` and its actual `MacheteLinearKernel.apply_weights` path, extending only the tested M values to 48/64/96/128. Run paired W4/BF16 exact Gemma linear shapes with the existing finite and dual-reference oracles. The first exact M48 consumer call is the discovery audit; repair ordinary API, allocation, profiler, telemetry, or packaging defects in place.

While the W4 owner bootstraps, prepare the compatible actual-head follow-up offline from `../gemma_l40s_parallel_lm_head_component/vllm_parallel_lm_head_bench.py`. If ready without delaying the primary, run it sequentially in the same pinned image/resource at M48/64/96/128. Record CUDA-event and synchronized-wall distributions, allocator peak, NVML, useful-GPU/provider time, and raw batch-duration proxies. Do not retain an idle GPU waiting for the follow-up.

For each M, compute W4-linear plus actual-head seconds/request and its residual to the `0.5479752315195353` ceiling. A point at or above the ceiling is closed before attention. A point below it is component-plausible only; rank surviving points by residual, memory feasibility, and batch completion-time proxy. No c32 attention timing may be extrapolated. A later attention or endpoint experiment is justified only for a measured survivor with material margin.

## Budgets and stopping

Execution profile. One retained H100 development owner with `repair_window_seconds=600`; 35 wall minutes, 22 provider minutes, 0.37 H100-hours plus 2 local CPU-hours, one 100-GiB disk, 1 GiB retained plus 2 GiB temporary, and `$1.25` maximum. Stop after valid rows and authenticated cleanup, if every point is component-closed, if memory makes the remaining points infeasible, on unsafe/unintelligible state or hardware/image change, or when any limit is exhausted. No checkpoint transfer, c32 global retry, quality run, or separate audit/repair project is authorized.
