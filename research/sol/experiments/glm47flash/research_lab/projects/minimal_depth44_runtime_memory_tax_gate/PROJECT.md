# Minimal-depth-44 runtime-memory-tax gate

## Question

Can one semantics-preserving pinned-vLLM memory intervention remove at least `622.871 MiB` from the exact c32 serving envelope, enough to admit a nested 44-layer proxy with 1,536 MiB headroom while retaining a conservative path to `606.355` output tok/s?

## Why this matters

Depth43 is the smallest currently admitted proxy and is measuring under a live owner. Its exact projection is `44,512.935 MiB`, only `19.065 MiB` inside the campaign's robust boundary. Restoring one further ordinary MoE block would add approximately `353.935 MiB` of payload and `288 MiB` of mandatory c32 BF16 KV, projecting `45,154.871 MiB`; therefore at least `622.871 MiB` of nonessential runtime memory must be removed to keep peak at or below `44,532 MiB`. If pinned vLLM has no such memory tax with tolerable performance, 43 layers is the robust L40S boundary and another depth materialization is wasted work.

## Fixed evidence

- Measured parent: `../minimal_depth42_v2_l40s_direct/`, c32 `686.910494` output tok/s, peak `43,871 MiB`, archive `ee0f3f3b3d3abfa2f9610320a5be44934be8493a61f52a0d339e83ca4b3d8541`.
- Admitted depth43: `../minimal_depth43_v2_l40s_direct/ADMISSION.json`, exact projection `44,512.935379 MiB`, restored payload `353.935379 MiB`, restored c32 KV `288 MiB`, and safety limit `44,532 MiB`. Its live experiment is excluded.
- Candidate geometry only: a nested 44-layer proxy would restore one of `[6,15,24,33]`; all model selection and materialization are out of scope. Use the exact ordinary-block payload/KV geometry only to calculate the required memory saving.
- Runtime: pinned vLLM `0.15.0`, Transformers `1618d44b9295361607ec74d7be860ba886aac039`, SM89 L40S, BF16 KV, W4A16 compressed-tensors, `max_num_seqs=32`, `max_num_batched_tokens=65536`, capture sizes `[1,2,4,8,16,24,32]`, and exact 8,192/1,024 cache-off workload.
- Prior boundaries: `../near_stock_c32_memory_frontier/`, `../l40s_mla_full_graph_gate/`, `../full_model_fp8_kv_c32_corrected/`, and `../decode_packing_source_falsifier/`. Do not reopen FP8 KV, full-graph MLA, higher concurrency, speculative decoding, or scheduler packing.
- Economics: planning `$1.10/hour`, absolute gate `594.466`, robustness marker `606.355`, 300-second background envelope.

## Execution contract

Work offline for at most 900 seconds, 6 GiB RSS, 24 MiB of new artifacts, and `$0`. Bind the exact server command, pinned source, memory logs, capture policy, and depth42 telemetry. Reconstruct the c32 envelope into mandatory model payload, mandatory 32-sequence 8K BF16 KV, graph/capture allocations, allocator/workspaces, sampler/logit buffers, and unidentifiable residual. Use exact source allocation sizes where available and bounded measurements otherwise; do not count device free memory or lower `gpu_memory_utilization` as a saving.

Screen existing configuration first and at most one minimal source-supported intervention. It must preserve c32 request concurrency, 8K/1K geometry, cache-off semantics, model tensors, BF16 KV, exact outputs, and request completeness. Eager mode, capture-size changes, allocator settings, or workspace reductions are admissible only when their saved bytes are exact or conservatively bounded and their performance penalty has a scope-matched non-overlap bound. A fit that plausibly falls below `606.355` is closed.

Return exactly one terminal result:

- `NOMINATE_MEMORY_GATE`: one exact configuration or minimal source-bound intervention conservatively saves `>=622.871 MiB`, keeps projected c32 `<=44,532 MiB`, and retains `>=606.355` tok/s with a single bounded future falsifier; or
- `MEMORY_TAX_CLOSE`: savings are insufficient, mandatory, unidentifiable, or carry an unbounded/sub-gate performance penalty.

Do not use CUDA, network/provider resources, mutate shared code, materialize a 44-layer checkpoint, build a controller, prepare a paid invocation, train, or nominate a second mechanism. Produce one compact machine-readable decision artifact, an optional focused calculator/source audit, and a concise research-log update. No successor.

## Available resources

Use the fixed local projects above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.
