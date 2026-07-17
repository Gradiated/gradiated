# Minimal-depth-42 background-concurrency frontier gate

## Question

Does the checksum-closed 42-layer proxy have enough robust L40S memory headroom for a later c40 or c48 exact 8K/1K background arm, and what measured c32 endpoint would make that higher-concurrency arm decision-relevant against `594.466` output tok/s and the 300-second envelope?

## Why this matters

The live direct project measures c16 and c32 only. The campaign explicitly allows latency to be traded for cost, and the 42-layer proxy projects `2,401.977 MiB` of c32 headroom—possibly enough for one higher-concurrency step even though the full 47-layer model cannot use it. A bounded offline capacity and decision-threshold gate can prevent either missing a useful background operating point or reflexively launching c40 after c32 when memory, saturation, or required uplift makes it low value.

## Fixed evidence

- Candidate: `/root/.cache/glm47flash-awq-minimal-depth42-v2-5dbf26dc16a1`, contract SHA-256 `5dbf26dc16a1cabbdb36eb256a996a11cf44c71c702b72686806a68a3bb1a290`, 42 serving layers, four shards, and `16,658,558,680` shard bytes.
- Exact materialization and geometry: `../minimal_depth42_clean_materialization/`, `../minimal_change_c32_codesign/`, and `../student42_measured_depth_transfer_falsifier/`. Their c32 projection is `43,666.023 MiB` against the measured `46,068-MiB` envelope.
- Historical matched telemetry only: full47 r3 c16 and student39 c16/c24/c32 artifacts referenced by `../student42_measured_depth_transfer_falsifier/`. Preserve their runtime, `num_kv_splits=4`, max-sequence, model-depth, and request-count differences; do not transfer student39 throughput as a depth42 measurement.
- Current economics and workload: L40S planning `$1.10/hour`, `594.466` output tok/s absolute gate, `606.355` robustness gate, exact 8,192 input/1,024 output, cache off, and 300-second background-arm envelope.
- Live project `../minimal_depth42_v2_l40s_direct/` is excluded. Do not inspect, wait for, poll, alter, or consume any live or newly terminal artifact from its current owner.

## Execution contract

Work offline for at most 600 seconds, 4 GiB RSS, 16 MiB of new artifacts, and `$0`. Bind the exact model and workload geometry. Reconstruct the per-sequence KV/block reservation, graph/capture and scheduler reservation, fixed model/runtime footprint, and observed fragmentation allowance from the fixed historical artifacts and pinned vLLM source. Project c32, c40, c48, and c64 peak memory; show nominal and adverse bounds rather than a single linear point. Use the campaign's existing `1,536-MiB` robust-headroom convention unless exact allocation evidence supports a stricter bound.

For every concurrency that survives memory, derive a decision table keyed to a future measured depth42 c32 result: minimum c32 throughput, peak memory, marginal batch efficiency, completion time, and incremental output needed for one later higher-concurrency arm to have a conservative path to `606.355`. Treat student39 scaling only as sensitivity. Do not infer a depth42 endpoint, and do not nominate an arm merely because it fits.

Return exactly one terminal result:

- `MEMORY_CLOSE`: no concurrency above c32 retains robust headroom;
- `SATURATION_CLOSE`: a higher concurrency may fit, but no conservative decision region reaches `606.355` inside 300 seconds; or
- `CONDITIONAL_FRONTIER`: exactly one next concurrency has robust admission and a concrete future-c32 trigger that would make one later direct arm informative.

Do not use CUDA, network/provider resources, mutate checkpoints or shared launchers, build a controller, run the live owner, train, or prepare a paid invocation. Produce one compact machine-readable frontier artifact, an optional focused calculator, and a concise research-log update. No successor project.

## Available resources

Use the fixed local projects above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.
