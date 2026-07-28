# Research log

## 2026-07-18 — candidate-only fused QK-normalization/RoPE c32 terminal

Question: does the pinned fused path improve the retained dynamic-chunked c32 exact mix?

Action: claimed `h200-attention-endpoint-e00vbbb709tzxscaan`, stopped only the stock-c48 restart, and launched the pinned BF16 / FP8-E5M2 server with dynamic chunking at 2048 and `--enable-fused-qk-norm-rope`. Container arguments and `ServerArgs(enable_fused_qk_norm_rope=True)` verify the path. The first launcher returned while CUDA graphs were still capturing; one ordinary repair retained that same healthy server and removed its root-owned partial output before the sole exact-mix invocation.

Evidence (measured): all 32 rows completed with the frozen runner (`143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`), 4,214 prompt and 358 completion tokens each. It reported 0.373280326250 s/request, 99.0% mean GPU utilization, 540.293 W mean power, and 123267.227 MiB mean memory. However `/flush_cache` returned HTTP 400, so cache accounting was 134,816 cached / 32 fresh prompt tokens rather than the bound 17,120 / 117,728. Raw responses, request rows, metrics, GPU samples, path arguments, and server logs are in `artifacts/fused-qk-norm-rope-c32-20260718t1806z/`.

Interpretation: terminal `negative`, not an efficiency result. The cache mismatch invalidates the frozen exact-mix comparison, so the apparent 59.89% service-time reduction cannot be promoted or retained. No rerun is allowed by the admission contract. Claimed exposure was 335 seconds at $2.46/hour ($0.229 conservatively recorded); the fused server remains healthy for bench reuse.

## 2026-07-18 — canonical consumer-only capture

Action: reused the already-loaded fused c32 server without restart or reload. Before the only consumer invocation, the recorded `/metrics` boundary showed zero running and queued requests; an empty-body `POST /flush_cache` returned HTTP 200 with `Cache flushed.` The remote resident runner hash matched the frozen `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7` identity.

Evidence (measured): one 32-request exact mix produced 32/32 valid rows, 17,120 cached and 117,728 fresh prompt tokens exactly, and verified `enable_fused_qk_norm_rope=True`. Service time was 0.919457394125 s/request versus the frozen 0.930607045500 baseline: a 1.198105% improvement. Mean GPU utilization, memory, and power were 99.284%, 122765.211 MiB, and 629.709 W across 109 samples. Raw rows, SSE responses, metrics, GPU samples, path identity, server log, and preflight boundary are in `artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/`.

Interpretation: `retain_incremental`. The result is valid and positive but does not meet the 5% promotion threshold; retain the fused flag on the dynamic-2048 c32 baseline without further tuning or replay.
