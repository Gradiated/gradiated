# L40S MLA full-CUDA-graph gate

## Question

Does the r3 runtime's measured downgrade from full-plus-piecewise CUDA graphs to piecewise-only execution expose an exact SM89 MLA backend or compilation path whose conservative launch/graph savings can reach the `594.466`-tok/s economic target?

## Why this matters

The valid r3 server requested `FULL_AND_PIECEWISE`, captured sizes `[1,2,4,8,16,24,32]`, and then emitted a source-typed warning that `TritonMLABackend` has `AttentionCGSupport.NEVER`, forcing `PIECEWISE`. The target trace also contains 6,096 `cudaGraphLaunch` calls and a large compiled-graph boundary. Split-MLA tuning is closed after a 33.43% component reduction transferred to only about 1.05% endpoint gain; full graph replay is a distinct launch/synchronization mechanism and must be decided by exact backend support plus interval evidence, not another split sweep.

## Fixed evidence

- R3 archive: `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/vllm-awq-batch.tar.gz`; summary SHA-256 `23bce62e7a9f10c4d5708630a5351146f0c785ef2bc1281c6757459fb31c8218`.
- R3 server identity: exact AWQ revision, vLLM 0.15.0-derived runtime, cache-off 8,192/1,024, c16, `num_kv_splits=4`, 32 complete requests, `552.1710554232396` tok/s.
- Measured warning: full graphs are unsupported with selected Triton MLA and are reduced to piecewise because attention is compiled piecewise.
- Existing diagnostic profiler is fixed 8K/128 c8, not the target c16/1K endpoint. Use interval unions and CPU/GPU flow only within its scope; never turn summed kernel or launch durations into target wall share.
- Consume `../moe_dense_residual/`, `../l40s_model_chip_codesign/`, and `../vllm_release_delta_screen/` as fixed prior evidence. Do not reopen split count, rank, broad release, or generic profiling work.
- Economic thresholds: `$1.10/hour`, `$0.514/M`, ordinary `594.466` tok/s and robust nomination `606.355` tok/s.

## Scope and stop rule

Within 900 seconds, 8 GiB RSS, 64 MiB new artifacts, and `$0`, bind the exact r3 graph mode, capture sizes, selected MLA backend, compile partitions, and relevant source hashes. Audit the pinned runtime and at most one already-cached current stable source tree for one unchanged MLA backend/compilation configuration that simultaneously:

1. supports the exact GLM MLA head/rank/value geometry on SM89;
2. supports full CUDA graph capture for the target mixed prefill/decode path;
3. preserves compressed-tensors W4A16, cache-off semantics, c16 admission, and request correctness; and
4. avoids eager, dense/dequantized, SM90+, source-patch, or custom-kernel fallback.

Use the retained trace only to produce an honest partial-identification bound on removable graph/launch/partition overhead. Stress CPU/GPU overlap, c8/128 versus c16/1K scope, capture-copy overhead, dynamic-shape guards, prefill dilution, and the possibility that full replay merely hides already-overlapped launches. Do not infer gain from call counts alone.

Return exactly one terminal result:

- `NOMINATE_FULL_GRAPH_AB`: one exact unchanged SM89 path exists and a conservative stress bound reaches at least `606.355` tok/s, with one later matched A/B stated but not prepared;
- `RUNTIME_CLOSE`: no exact SM89 full-graph MLA path exists in the audited stacks;
- `ECONOMIC_CLOSE`: a valid path exists but conservative savings miss the gate; or
- `UNIDENTIFIABLE`: source admission survives but retained intervals cannot establish a conservative economic path; state the sole resolving measurement without preparing it.

Do not use CUDA/network/provider resources, edit shared code, build a backend, collect a new trace, or prepare a controller. Produce one compact JSON, any project-local source/trace audit, and a concise research-log result.

## Available resources

Use the named archives/projects, `hardware/L40S.md`, local runtime/source caches, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

