# ModelOpt FP8 export and endpoint consumer

## Question

Can the exact Gemma 4 31B checkpoint be converted by the supported offline ModelOpt quantize-then-deploy workflow into a content-addressed E4M3 compute representation that pinned SGLang actually consumes, while preserving bounded numerical/output sanity and improving the retained H200 c32 endpoint enough to justify later 48-GiB L40S placement?

## Why this matters

The online ModelOpt producer is explicitly disabled in pinned SGLang, but its typed error directs users to a separate quantize-then-deploy workflow. Independently, exact-shape H200 measurements show that E4M3 linears and the tied head pass numerical oracles and reduce the component floor by 9.6602% when attention and KV remain BF16. That is enough evidence to test the supported exported representation, not enough to infer an endpoint or L40S result. A successful export could both reduce H200 service cost and make a single-rank 48-GiB placement plausible without deleting model capacity.

The immediately preceding compiler arm is closed: the verified compiled endpoint was 1.885% slower than the retained fused baseline. Do not combine Torch compilation with this experiment.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Source checkpoint: exact eight-file, 62,578,655,208-byte checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
- Runtime image: pinned SGLang v0.5.12 `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Warm bench: `h200-attention-endpoint-e00vbbb709tzxscaan`, H200 SXM, protected by `gemma-modelopt-export-h200-202607181843z-watchdog.service` through `2026-07-18T20:55:00Z`.
- Retained endpoint comparator: `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`, SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`, at `0.9194573941250042` service seconds/request.
- Comparator configuration: c32, BF16 weights, FP8-E5M2 KV, dynamic chunking 2,048, fused QK normalization/RoPE; 17,120 cached and 117,728 fresh prompt tokens.
- Exact runner: `projects/gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Passing E4M3 component evidence: `projects/gemma4_precision_hardware_frontier/artifacts/20260718t1611z-h200-e4m3-compute-bf16-kv/RESULT.json`, SHA-256 `02b833cdaa6878816b350ca7cae6982e203fb91a98bdabde2e604d91f66d624a`.
- Online-producer unsupported boundary: `projects/gemma4_h200_fp8_compute_endpoint/artifacts/20260718t1755z-online-e4m3-c32/TERMINAL.json`, SHA-256 `119d5954c784968bc0dbe9d08936f3600409872936faec1d81e1a3a26cbd8513`.

These identities are frozen. Do not substitute a model revision, checkpoint, image, workload, cache mix, or comparator.

## Immediate experiment

Claim the warm H200 and start one bounded durable owner for the producer, load test, endpoint consumer, retrieval, and release. Stop only the resident fused server to free memory. Inspect the official producer and pinned consumer source sufficiently to bind the supported separate ModelOpt export format, calibration contract, and SGLang load flags. This source/geometry decision is why the project uses the `deep` profile. Do not retry `--quantize-and-serve`, invent a new quantizer, or create a support/audit successor.

Produce one E4M3-compute export from the exact resident checkpoint. Use the smallest source-justified calibration set that satisfies the official workflow and record its identity and hashes. Write the export atomically and persist a manifest containing every file path, byte size, SHA-256, format/version metadata, quantization recipe, scale/accumulator policy, producer package identities, source checkpoint identity, wall time, peak disk use, and a typed producer terminal. The durable owner may outlive a researcher response; do not kill or restart correct materialization for turn cadence.

Only after the export terminal passes, launch that exact exported representation once on the same H200 using the pinned consumer and the retained production-compatible c32 settings: FP8-E5M2 KV, dynamic chunking 2,048, and fused QK normalization/RoPE. Prove from runtime metadata/logs that the exported FP8 compute path—not BF16 fallback or online conversion—was consumed. Run bounded layer/output numerical sanity before the endpoint consumer. Then prove zero running/queued requests, record an HTTP-200 cache flush, invoke the unchanged exact-mix runner once, and retrieve raw rows, responses, cache/phase/power/memory/queue telemetry, producer/consumer logs, export manifest, and a typed terminal. Do not rerun the comparator.

## Decision gate and limits

- `promote_h200_export`: producer and intended consumer identities pass; 32/32 finite, nonempty, coherent rows; bounded numerical sanity passes; exact 17,120 cached/117,728 fresh accounting; service time at most `0.873484524419` seconds/request (at least 5% over the retained fused BF16-weight baseline).
- `retain_incremental`: the same identity, correctness, and cache gates; any service improvement below `0.9194573941250042` without material reliability or operational complexity regression. Retain without recipe or calibration tuning.
- `unsupported`, `producer_failure`, `calibration_failure`, `storage_failure`, `consumer_load_failure`, `precision_path_unproven`, `quality_sanity_failure`, `negative`, `timeout`, or `owner_failure`: emit a typed terminal and close this representation without an export/recipe sweep.

H200 success is only a prerequisite for later L40S nomination. Do not allocate L40S, transfer the export to another provider, or claim 48-GiB fit in this project.

Maximum claim: 122 wall minutes, 105 H200 compute minutes, 120 GiB additional temporary storage, and `$5.50` provider exposure at `$2.46/hour`, ending by `2026-07-18T20:45:00Z` with ten minutes reserved for retrieval and release. Release without teardown. Do not pull the pinned image, replay the BF16 checkpoint transfer or hashes, retry the disabled online producer, sweep quantization recipes/calibration sizes, enable Torch compilation, alter chunk size/concurrency/KV precision, mount the rejected attention patch, run broad GPQA/TauBench quality, create provider resources, or change the watchdog.
