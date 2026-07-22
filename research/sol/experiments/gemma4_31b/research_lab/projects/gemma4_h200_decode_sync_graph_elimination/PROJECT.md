# Gemma 4 H200 decode synchronization and graph elimination

## Question

Can one source-level removal, deferral, or graph-safe replacement of the dominant decode synchronization boundary reduce the exact c32 endpoint below the retained `0.689220013 s/request` frontier and materially approach `0.6381105231 s/request`?

## Evidence and hypothesis

The content-bound profile `../gemma4_h200_v0513_fp8_qkv_residual_profile/artifacts/residual-profile-20260720t0821z/ATTRIBUTION.json` (SHA-256 `f841db590dbe6f2e6b4fb91048e8132c3807f0321310e1e0b70a3957ac99ab48`) assigns 36.58% of total wall time and 52.52% of decode to synchronization. Scheduler gaps add 5.00% and launches 1.11%. This is the largest unclosed measured boundary.

Use the existing Nsight SQLite and pinned SGLang source to map the dominant synchronization intervals to exact CUDA API calls, host call sites, stream/event dependencies, and graph-capture state. Form one causal intervention and predict which synchronization count/time or graph-break metric should fall. Do not run a generic flag sweep, replay torch-compile, or treat profiling alone as the result.

## Immutable endpoint

- Binding: `../gemma4_h200_v0513_fp8_qkv_residual_profile/BINDINGS.json`, SHA-256 `cebc435c4eb1e5716c4aa9bd854785a3e7cac4b0665c96ea6a44040b3e96fb62`.
- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Checkpoint index SHA-256: `d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, image `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Representation: TP1 dynamic FP8-E4M3FN linears, FP8-E5M2 KV, dynamic chunking 2048, no MTP.
- Workload: 32 requests at concurrency 32, 4,214 prompt and 358 completion tokens each, with 17,120 cached and 117,728 fresh prompt tokens total.

## Experiment and gate

Prepare the single source patch offline, then await a director-registered H200. Run one contemporaneous control/candidate endpoint pair with 32/32 accounting, exact token/cache totals, sane outputs, and candidate-path proof. Measure profiler-off service time first; collect only the minimum follow-up trace needed to verify the predicted synchronization change. Repair ordinary integration defects in the same retained session.

Success is service time at or below `0.6381105231 s/request`. Preserve an operationally simple smaller gain under the incremental-wins policy, but do not tune variants after a negative pair. Emit a typed terminal with control/candidate timing, synchronization mechanism and delta, output validity, provider exposure, and actual spend.

## Budget

`$20.00` total, one shared H200, at most four claimed GPU-hours and five wall-clock hours from first claim. Researchers may not mutate provider lifecycle.
