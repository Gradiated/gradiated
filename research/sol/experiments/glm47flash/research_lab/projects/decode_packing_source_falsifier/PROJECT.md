# Decode-packing source falsifier

## Question

Does pinned vLLM expose one exact scheduler/admission change—distinct from simply increasing request concurrency from 16 to 32—that can conservatively improve the measured depth42 c32 frontier above `700.649` output tok/s without changing model semantics, memory admission, or the authoritative workload?

## Why this matters

Measured phase attribution correctly identifies continuous decode packing as the source of depth42's `11.398%` c16-to-c32 gain, but its proposed c16 falsifier only retains `606.355` tok/s. That could be slower than measured c16 (`616.602`) and materially worse than measured c32 (`686.910`), so it does not yet advance the campaign's dollars-per-token objective. A fast pinned-source audit should either name a genuinely new, executable packing intervention that compounds with c32 or close this nomination before another L40S allocation.

## Fixed evidence

- Primary result: `../minimal_depth42_v2_l40s_direct/`, c16 `616.602087` tok/s and c32 `686.910494` tok/s on cache-off 8,192/1,024 with `max_num_seqs=32`, `max_num_batched_tokens=65536`, `num_kv_splits=4`, and vLLM `0.15.0`.
- Attribution: `../depth42_c32_phase_attribution/artifacts/DEPTH42_PHASE_ATTRIBUTION_2026-07-16.json`. It identifies more simultaneously live decode sequences but cannot split MLA, MoE, or decode kernels.
- Current frontier: require at least a 2% conservative improvement over c32, `700.649` output tok/s, not merely the campaign floor. Peak memory must remain at or below `44,532 MiB`; the 300-second background envelope remains authoritative.
- Runtime/source: pinned vLLM `0.15.0`, Transformers `1618d44b9295361607ec74d7be860ba886aac039`, and the shared batched runner/launcher under `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/`.
- The live `minimal_depth43_v2_l40s_direct` owner is excluded. Do not inspect, poll, wait for, alter, or consume its live or terminal artifacts.

## Execution contract

Work offline for at most 900 seconds, 6 GiB RSS, 24 MiB of new artifacts, and `$0`. Bind the exact scheduler and runner source used by the depth42 archive. Reconstruct how client concurrency, `max_num_seqs`, prefill admission, decode batching, chunked prefill, scheduling policy, asynchronous scheduling, and any multi-step/lookahead paths determine live decode batch size for this exact request geometry.

Audit existing public configuration first, then at most one minimal pinned-source intervention. Raising client concurrency, relabeling c32, adding speculative decoding, changing output length, enabling prefix caching, or relaxing the workload is not a new mechanism. A candidate must preserve exact target-token verification and request completeness, have no new checkpoint or training requirement, fit the measured c32 memory boundary, and expose an observable counter or deterministic source invariant that proves it changes packing rather than only queue latency.

Quantify the strongest conservative endpoint path using measured c16/c32 evidence. Do not convert theoretical queue overlap or GPU utilization into saved wall time without a non-overlap argument. Return exactly one terminal result:

- `NOMINATE_SCHEDULER_ARM`: one exact knob or minimal patch is source-bound, distinct from higher concurrency, preserves semantics/memory, and has a conservative path to `>=700.649` tok/s with a one-arm falsifier; or
- `MECHANISM_CLOSE`: c32 already realizes the available packing mechanism, or no exact distinct intervention has enough identified wall-time leverage.

Do not use CUDA, network/provider resources, mutate shared runtime/launcher code, build a controller, prepare a provider invocation, or propose a second candidate. Produce one compact machine-readable decision artifact, an optional focused source-audit script, and a concise research-log update. No successor.

## Available resources

Use the fixed local projects above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.
