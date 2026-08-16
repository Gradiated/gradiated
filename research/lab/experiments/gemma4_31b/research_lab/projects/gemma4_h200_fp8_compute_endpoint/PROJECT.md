# H200 online-FP8 compute endpoint

## Question

Can pinned SGLang v0.5.12 consume the exact BF16 Gemma 4 31B checkpoint as an online E4M3 compute representation, keep stock attention/scheduling and FP8-E5M2 KV, and reduce exact-mix c32 service seconds per request by at least 5% versus the frozen stock c32 control?

## Why this matters

The exact-shape H200 mixed arm already passed its numerical oracles and measured a 9.6602% component-floor gain from E4M3 linears/head with BF16 attention and state. That is enough prior margin to justify one endpoint consumer. The explicit repeated-KV attention integration was 4.22x slower and is excluded; c48 saturation and dynamic chunking are also terminally negative. This project tests only whether the supported precision representation survives full-runtime integration.

## Bound evidence and identities

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Resident checkpoint: exact eight-file, 62,578,655,208-byte BF16 checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.
- Runtime image: pinned SGLang v0.5.12 `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Warm bench: `h200-attention-endpoint-e00vbbb709tzxscaan`, H200 SXM, protected through `2026-07-18T18:48:52Z`.
- Frozen stock exact-mix c32 comparator: `projects/gemma4_background_serving_frontier/artifacts/exact-mix-c32-20260718t1729z/TERMINAL.json`, SHA-256 `6508e309d09a1ab04daa50c33243062843836bb5259ce107f387603008f65d0f`, `0.969888308813` service seconds/request.
- Exact-mix runner: `projects/gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- E4M3/BF16 component prior: `projects/gemma4_precision_hardware_frontier/artifacts/20260718t1611z-h200-e4m3-compute-bf16-kv/RESULT.json`, SHA-256 `02b833cdaa6878816b350ca7cae6982e203fb91a98bdabde2e604d91f66d624a`, measured margin `9.6602%`.

These identities were mechanically extracted from the resident bench inventory and authoritative artifacts. Do not substitute a checkpoint, image, runner, custom attention mount, workload, or model revision.

## Immediate experiment

Claim the warm bench and stop only the healthy stock c48 container. Inspect the pinned runtime's actual online-FP8 producer/consumer flags, then launch one candidate server that quantizes the resident BF16 weights for E4M3 compute while retaining stock attention, stock scheduling, c32 geometry, and FP8-E5M2 KV. The exact-runtime launch is the compatibility discovery; repair at most one ordinary flag/API defect in place. Do not run a new stock arm.

Run the frozen 32-request 4,214-prompt/358-output exact mix with the same 12.6958% cache-read construction. Retrieve raw rows, runtime/quantization identity, load and compile timing, memory, phase, power, queue, cache, and failure telemetry. Emit a typed `promote`, `negative`, `unsupported`, `quality_sanity_failure`, or `owner_failure` terminal.

## Decision gate and limits

Promote to later quality work only if the server proves the intended FP8 compute path, completes 32/32 rows with exact token counts and finite nonempty/coherent text, and measures at most `0.921393893372` service seconds/request (5% below stock). Treat an unsupported online producer, numerical failure, load/compile failure after one bounded repair, or a miss of the endpoint gate as terminal for this pinned runtime path.

Maximum claim: 25 GPU minutes and `$1.10` at `$2.46/hour`, ending by `2026-07-18T18:17:00Z`; local preparation and retrieval must fit the same wall-clock bound. Reuse resident checkpoint/image/workspace, release without teardown, and do not replay transfer, pull the image, run broad quality, use the rejected attention patch, sweep precision modes, or allocate provider resources.
