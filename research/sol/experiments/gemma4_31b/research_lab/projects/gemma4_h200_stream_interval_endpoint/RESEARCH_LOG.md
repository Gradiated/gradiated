# Research log

## 2026-07-18 — director admission

- Measured context: the retained canonical endpoint is `0.9194573941250042` service seconds/request; continuous decode steps 4, mixed chunking, and Triton KV splits 4 are closed regressions.
- Source-backed hypothesis: pinned SGLang defaults `stream_interval=1` and documents that a larger token buffer raises throughput while reducing streaming smoothness. The exact background workload streams all 358 generated tokens for 32 simultaneous requests, so interval 8 may amortize serialization and SSE delivery without changing model computation.
- Scope: one candidate-only exact c32 arm at interval 8 on the fully restored canonical runtime; no sweep or comparator replay.
- Gates: 32/32 valid 4,214/358 rows, exact 17,120 cached / 117,728 fresh prompt-token accounting, frozen request hashes, complete output sanity, and service time below `0.9194573941250042` to retain or at most `0.8734845244187539` to promote.
- Budget: 45 wall minutes, 35 H200 compute minutes, 3 GiB temporary storage, `$2.25` maximum project exposure, claim complete by `21:20Z`.
- Lifecycle: the director atomically replaced the watchdog with `gemma-stream-interval-h200-202607182033z-watchdog.service`, verified it active through `21:30Z`, updated pool inventory, then stopped the old watchdog. Incremental retained-bench exposure from the prior `20:55Z` deadline is about `$1.44`.
- Artifact contract: immutable project-local runner snapshot; resolved launch identity; idle and HTTP-200 flush proof; raw SSE rows; exact request hashes; metrics and GPU telemetry; typed `TERMINAL.json`; retrieved artifacts; released bench without teardown.

## 2026-07-18 — canonical interval-8 result

- Action (measured): atomically snapshotted `inputs/exact_mix_runner.py` at SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`, claimed the resident H200, stopped only `gemma-triton-kv-split4-c32`, and ran the immutable exact-mix consumer once against the restored c32 endpoint with only `--stream-interval 8` changed.
- Evidence (measured): the resolved server log proves interval 8, KV splits 8, BF16/FP8-E5M2, dynamic chunking 2048, fused QK/RoPE, Triton prefill/decode, page size 1, one continuous decode step, mixed chunk disabled, and CUDA graphs through 32. Idle metrics and an HTTP-200 flush preceded consumption. All 32 rows were finite/nonempty with exact 4,214/358 use and exact 17,120 cached / 117,728 fresh prompt tokens. Raw SSE, rows, request hashes, metrics, GPU samples, and logs are in `artifacts/stream-interval8-c32-20260718t2040z/`.
- Result (measured): 1,536 SSE data events, `0.930380506594` service s/request, versus `0.919457394125` control: a `-1.1879955%` change. Terminal SHA-256 is `513adb238c3046edbbc3158734c0409ebdc46e6fc02ac18785719287b5f3dd3f`.
- Decision: `negative`. Coarser delivery reduced event count but did not overcome service cost at this exact workload. Do not tune, replay, or compound interval 8. The healthy interval-8 server remains resident and the bench is released ready without teardown.
