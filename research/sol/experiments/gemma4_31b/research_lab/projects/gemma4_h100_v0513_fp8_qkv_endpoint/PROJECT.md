# Exact v0.5.13 FP8+QKV H100 economic endpoint

## Question

Can the proven Gemma 4 31B v0.5.13 dynamic-FP8 plus QKV-epilogue endpoint run the exact c32 campaign workload on one H100 SXM at `<=0.741 s/request`, the direct `$0.14/M` total-token economic ceiling at the committed `$2.80/GPU-hour` rate and 90% utilization?

## Why this matters

The H200 stack reaches `0.6928421805 s/request` but misses sustainable economics after utilization and operating headroom. H100 is 13.85% cheaper at the current committed planning rate and may be modestly slower while still winning. This is a fresh matched v0.5.13 dynamic-FP8 placement question, not the closed H100 W4/vLLM route.

## Bound evidence and scope

- Exact model: `google/gemma-4-31B-it` at revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, image `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Representation: dynamic in-memory `fp8_e4m3fn` linears, `fp8_e5m2` KV, TP=1, dynamic chunking with chunk size 2048, and the exact persisted QKV epilogue bytes in `BINDINGS.json`.
- Workload: 32 concurrent requests, each 4,214 prompt and 358 completion tokens, with the same exact-mix cache accounting used by the reconciled H200 terminal.
- Historical H200 result is a placement prior only. Do not transfer its throughput to H100.

## Immediate experiment

After the harness durably reserves this project and the director registers one H100 bench, use one bounded durable owner to stage the exact checkpoint and pinned image, bind the QKV patch and runner bytes, and run one exact c32 endpoint arm. The first real model load and request are the discovery audit; repair ordinary integration defects in place before an unconsumed timing arm. Require 32/32 valid rows, exact prompt/completion/cache accounting, 240 target FP8 module and consumer rows, observed real FP8 GEMM use, exact QKV-epilogue invocation proof, idle queue boundaries, and provider-spend accounting. No BF16 arm, W4 arm, generic sweep, quality replay, or H200 claim is authorized.

## Decision rule

- Promote H100 placement if service time is `<=0.741 s/request` and all semantic/accounting/consumer gates pass.
- Close H100 placement if the valid result is slower than `0.741 s/request` or cannot fit/run within the bounded exact representation.
- A pre-invocation operational defect is not scientific evidence; repair it in the same claimed environment within the absolute deadline.

## Budgets and resources

- Researcher profile: `execution`.
- Wall clock: 150 minutes.
- H100 claim: at most 100 minutes, plus 15 minutes reserved for retrieval and release.
- Compute: at most 1.67 H100 GPU-hours and 4 local CPU-hours.
- Storage: one 250-GiB boot disk; at most 4 GiB retained project artifacts.
- Authorized spend: `$6.50`, including actual provider exposure; one allocation only.
- Provider creation is forbidden until the reservation is durable and a director-registered bench exists.

## Director continuation — replacement staging after watchdog cleanup

The first registered H100 attempt is operationally terminal but scientifically unconsumed. Its repaired owner verified six small checkpoint files and began the first 49.8-GB shard, then reached candidate CUDA setup without starting the c32 scientific arm before the absolute repair deadline. The owner exited, its lease expired, the watchdog cleaned both provider resources, and the director verified the exact instance and disk absent before retiring inventory. Do not infer H100 performance from this attempt.

Before another allocation, replace sequential guest-side HTTP download with the proven content-addressed transfer used by the H200 residual owner. Bind the existing read-only `62,578,655,208`-byte snapshot at `../gemma4_h200_v0513_fp8_qkv_residual_profile/inputs/checkpoint`; do not duplicate it. Transfer the two weight shards concurrently or through equivalent bounded resumable controller-to-guest streams, preserve partial files across owner restarts, verify every size and SHA-256 before atomic finalization, and record a size-derived deadline plus measured throughput. Emit one typed `STAGING_READY.json` and compiled durable owner. This is the only pre-create gate.

After the increased reservation is durable and that terminal passes, the director may create one replacement H100 with a watchdog sized for cold staging, model load, the sole exact c32 arm, retrieval, and cleanup. The scientific contract and `<=0.741 s/request` gate are unchanged. Cumulative authority is `$11.50`, at most 240 H100 exposure minutes across both allocations, one replacement resource, and one still-unconsumed arm.
