# H100 W4-Machete plus FP8-KV c32 residual falsifier

## Decision question

Does the actual pinned-vLLM H100 paged FP8-E4M3 KV producer/attention consumer at concurrency 32 fit the `0.0738631898962037 s/request` residual left after the measured W4-Machete transformer-linear floor and actual BF16 tied head?

The fixed additive evidence is content-bound and scope-matched:

- Actual Machete W4 c32 linears: `0.463242803462781 s/request`, `../h100_w4_marlin_direct_falsifier/artifacts/RECONCILED_MACHETE_TERMINAL.json`, sha256 `65f103eb84a94d8f985d7df072b24597cdb36532bd8f9b95b08860748f15beff`.
- Actual BF16 `ParallelLMHead` c32: `0.010869238160550593 s/request`, `../h100_parallel_lm_head_single_stage/artifacts/gemma-h100-head-dev-20260717t1953z/RECONCILED_TERMINAL.json`, sha256 `02948d57a0ced4a1215a0de38c42f7fda1bebd23fe540320371efe4d67624c56`.
- Planning ceiling: `0.5479752315195353 s/request`.
- Exact-geometry FP8-KV contract/prior: `../h100_hybrid_attention_kernel_mechanism/MECHANISM.json`, sha256 `3960c453e88b1a12e01351d2062dbaa7f8a800e63fe6674e997ddbbcfeebdda1`. Its optimistic FP8 HBM floor is `0.06404964107462686 s/request`, leaving very little room for attention work and remaining service costs; achieved measurement is required.

## Direct experiment

Use the exact campaign image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79` on one full H100 SXM, TP=1, no checkpoint. At c32, invoke deterministic nonzero K/V through the installed `unified_kv_cache_update`, then the actual selected paged attention backend with real `block_table`, `slot_mapping`, and sequence-length metadata. A dense-varlen stand-in, direct kernel fixture without the cache producer, or scalar metadata that bypasses the selected backend fails.

Measure paired BF16 and FP8-E4M3 paged KV for all exact Gemma attention geometry needed by the 4,214-prompt/358-output workload: 50 local layers with 32 query heads, 16 KV heads, head dim 256 and 1,024-token window; 10 global layers with 32 query heads, 4 KV heads, head dim 512 and decode contexts 4,214/4,393/4,571. Record selected backend classes and installed source hashes. Consume every timed output; require finite nontrivial BF16 output and FP8-vs-BF16 cosine >=0.99, normalized RMSE <=0.05. Randomize paired order, use 20 warmups and 100 timed repetitions, CUDA events plus synchronized wall, allocator state, interval-union kernel time, launch count, and durable NVML telemetry. Attempt DRAM/L2/active-warp counters when available; missing ncu counters limits mechanism interpretation but does not erase valid timed rows.

Aggregate the actual c32 attention/KV residual across 50 local and 10 global layers and all 358 steps without double-counting prefill. If it is `>=0.0738631898962037 s/request`, the measured W4+head+FP8-KV lower bound falsifies H100 c32 economics before norms, sampling, scheduler, service, reliability, and quality. If below, report component plausibility only and promote exact-revision W4 production, representative quality, and a complete-request endpoint; do not claim deployability here.

## Execution contract and budgets

This is an execution-profile direct GPU project, not a readiness or audit project. Bind the three authoritative artifact digests mechanically, then use one retained H100 development session through the proven lifecycle. Set `STATUS.json.active_session.mode=development` after create and opt into `repair_window_seconds=600`. The first exact-runtime producer/backend call is the discovery audit; repair ordinary import, signature, context, metadata, benchmark, profiler, telemetry, and packaging defects in place under the same owner. Do not create repair/audit/successor projects.

Budgets: 45 wall minutes; 30 provider minutes; 0.50 H100 GPU-hours plus 2 local CPU-hours; one 100-GiB disk; 2 GiB retained plus 1 GiB temporary; `$1.80` maximum. Stop for a typed residual decision, unsafe/unintelligible state, hardware/image change, exhausted limit, or a clearly faster route. Always authenticate zero-resource cleanup and separate setup from scored CUDA time and actual spend.

## 2026-07-17 redirect after the global semantic-oracle failure

The first retained session reached the actual producer and selected Triton consumer, and its local-attention row passed, but all three global geometries returned finite zero BF16 and FP8 outputs. Quarantine the reported `0.05875024725993476 s/request` aggregate. This is neither an FP8-KV performance result nor evidence that the combined candidate survives.

Keep the same scientific project and switch its next work to `researcher_profile: deep`. Before another create, trace the pinned global-attention call from Gemma geometry through the exact vLLM metadata builder, forward context, cache layout/page table, producer write, and selected consumer. Produce `GLOBAL_ROUTE_PACKET.json` with content hashes, the causal explanation for the zero-output path, the corrected source-bound metadata construction, and mechanical invariants that distinguish populated global pages from a semantically empty call. This is a pre-create route predicate, not a substitute for CUDA semantics; correct local audit defects in this project.

Once that packet passes, use the proven launcher for one new H100 retained development session in this project. The first scientific call is an M1 global-4214 BF16 nonzero sentinel through `unified_kv_cache_update` and `unified_attention_with_output`; then run paired BF16/FP8-E4M3 c32 rows at 4,214/4,393/4,571 with the existing finite/nontrivial/cosine/NRMSE gates. Ordinary context, metadata, API, profiler, and packaging defects are repaired in place under the same owner and a 600-second repair window. Only valid global rows may be aggregated against `0.0738631898962037 s/request`.

Redirect budget: 40 wall minutes total; at most 25 provider minutes and 0.42 H100-hours after the local packet passes; 3 local CPU-hours; one 100-GiB disk; 2 GiB retained plus 1 GiB temporary; `$1.50` maximum new spend. Stop on a valid residual decision, failure to establish a nonzero global BF16 sentinel within the repair/deadline budget, unsafe state, hardware/image change, or exhausted limits. Authenticate zero-resource cleanup. No successor, audit, or repair project is authorized.
