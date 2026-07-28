# H200 fused QK-normalization/RoPE endpoint

## Question

Does pinned SGLang's `--enable-fused-qk-norm-rope` path reduce full-request H200 cost for exact Gemma 4 31B traffic when stacked on the retained 2,048-token dynamic-chunking baseline, without changing attention semantics or output validity?

## Why this matters

Gemma 4 performs Q/K normalization and rotary positioning throughout its hybrid local/global attention stack. Fusing those compulsory elementwise transforms can remove intermediate traffic and launches without deleting model capacity or changing the checkpoint. The online-FP8 producer is explicitly disabled in the pinned runtime, while concurrency above c32 causes KV-pool retractions; this flag-visible kernel path is the shortest distinct endpoint falsifier on the warm checkpoint.

The campaign now retains simple compatible gains below a standalone 5% continuation gate. A valid positive result below 5% should therefore be recorded and kept in the working baseline, not tuned further.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Resident checkpoint: exact eight-file, 62,578,655,208-byte checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
- Runtime image: pinned SGLang v0.5.12 `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`; its captured CLI exposes `--enable-fused-qk-norm-rope`.
- Warm bench: `h200-attention-endpoint-e00vbbb709tzxscaan`, H200 SXM, protected through `2026-07-18T18:48:52Z`.
- Working comparator: the `dynamic_chunked` arm inside `projects/gemma4_background_serving_frontier/artifacts/exact-mix-c32-20260718t1729z/TERMINAL.json`, SHA-256 `6508e309d09a1ab04daa50c33243062843836bb5259ce107f387603008f65d0f`, at `0.930607045500` service seconds/request.
- Comparator cache accounting: 17,120 cached and 117,728 fresh prompt tokens, 12.6957759848% cache reads.
- Exact runner: `projects/gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.

These values were mechanically extracted from the authoritative terminal, runner, bench inventory, and pinned-runtime preflight. Do not substitute identities or mount the rejected repeated-KV attention patch.

## Immediate experiment

Claim the warm bench and stop only the current stock c48 restart. Launch one candidate server from the resident image/checkpoint with the retained c32 geometry, BF16 weights, FP8-E5M2 KV, `--enable-dynamic-chunking --chunked-prefill-size 2048`, and `--enable-fused-qk-norm-rope`. Preserve all other bound stock settings. The exact launch is the compatibility discovery: allow one ordinary flag/model-binding repair in the same mutable workspace only when the error is explicit and the intended fused kernel remains verifiable; a missing kernel implementation is a typed unsupported result, not another preparation project.

Run only the candidate 32-request exact mix at 4,214 prompt and 358 output tokens. Retrieve raw rows, the actual fused-path identity, server logs, cache/phase/power/memory/queue telemetry, and a typed terminal. Do not rerun stock or the unfused dynamic comparator.

## Decision gate and limits

- `promote`: 32/32 exact, finite, nonempty/coherent rows; exact comparator cache accounting; verified fused path; service time at most `0.884076693225` seconds/request (at least 5% incremental improvement).
- `retain_incremental`: the same correctness, cache, and path gates; service time improves over `0.930607045500` but by less than 5%, with no material reliability or phase regression. Retain without tuning.
- `negative`, `unsupported`, `quality_sanity_failure`, or `owner_failure`: no improvement, wrong path, invalid outputs/cache accounting, or bounded runtime failure.

Maximum claim: 25 GPU minutes and `$1.10` at `$2.46/hour`, ending by `2026-07-18T18:29:00Z`. Release without teardown. Do not transfer the checkpoint, pull the image, sweep fusion/configuration flags, alter dynamic-chunk size or concurrency, run broad quality, allocate hardware, or extend the watchdog.
