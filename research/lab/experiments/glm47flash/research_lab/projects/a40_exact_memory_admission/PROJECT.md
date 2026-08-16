# Exact A40 memory and economic admission

## Question

Can the verified current GLM-4.7-Flash AWQ checkpoint and fixed 8,192/1,024 background workload fit an A40 48 GiB with enough KV/workspace headroom for c8 or c16, and is the required TensorDock throughput physically plausible enough to justify seeking external account authority?

## Why it matters

TensorDock currently lists an exact A40 at a conservatively screened $0.38225/hour all-in, requiring 166.819 output tok/s for the 5% gate and 176.968 for $0.60/M. But the historical L40S run reported 46,068 MiB device residence on a nominal 48 GiB GPU, leaving little apparent margin, and that observation is not transferable to the new identity or A40. Before asking for credentials/funding or attempting an exact load, the lab can use exact checkpoint tensor metadata, model geometry, and pinned runtime allocation rules to determine whether c8/c16 is impossible, safely feasible, or genuinely unresolved.

This is a direct falsifier of the leading hardware intervention, independent of the exhausted Nebius controller route.

## Relevant evidence

- Current AWQ revision `ab31d120...`: 20,170,199,928 weight bytes with verified config/index/tokenizer identities.
- Fixed live-token upper bounds are 73,728 at c8, 147,456 at c16, and 294,912 at c32 before runtime reserve/fragmentation.
- TensorDock screen: $0.3475/hour listed minimum, $0.38225/hour with 10% lifecycle allowance, two currently listed A40 hosts, but no authenticated lifecycle authority.
- A40: 48 GiB and 696 GB/s vendor-reported memory bandwidth. Historical L40S values are priors only.
- Current vLLM path pins v0.15.0, BF16 activations/KV, 65,536 batched tokens, 32,768 model context, `gpu_memory_utilization=0.90`, and prefix caching off.

## Scope

Complete one zero-provider, model-specific measurement/simulation turn. Parse the exact current config and safetensors index to account for weights by tensor family/layer/expert and total on-device bytes. From the exact attention/MoE geometry and pinned vLLM source, derive KV bytes per token, allocator block size, CUDA graph or capture pools, activation/workspace bounds, quantization metadata/scales, non-torch reserve, and fragmentation/alignment effects relevant to c1/c8/c16/c32. Reproduce the runtime's memory-budget equations where possible with a small deterministic script and retain all inputs, formulas, source revisions, and a machine-readable result.

Use three evidence bands rather than a false point estimate: hard lower bound, source-derived expected allocation, and conservative upper bound. Treat the historical 46,068 MiB L40S residence only as an external calibration check and explain any difference. Apply the actual 90% A40 allocation ceiling and require explicit headroom for driver/runtime variance. Classify each concurrency as impossible, safely admissible, or exact-load-required.

For every admissible concurrency, calculate the TensorDock rates needed for $0.6365/M and $0.60/M and the fraction of A40 bandwidth/compute implied by the exact per-token traffic/operation lower bounds. This is a plausibility/falsification test, not a throughput prediction. Include lifecycle, local-storage recovery, transfer, and nonproductive-session sensitivity at 10%, 20%, and one measured model-transfer setup interval.

Do not use credentials, mutate a provider, load a GPU model, infer speed from L40S throughput, repair Nebius, or weaken quality. Budget is $0 with no provider ownership.

## Available resources

Use the current AWQ cache and manifest, vLLM 0.15.0 source, `campaign_100` memory/telemetry artifacts, NVIDIA A40 specifications, TensorDock venue artifacts, and shared analysis tools.

## Portfolio-changing result

A hard memory violation at c8 or a physical/economic lower bound above the target closes the A40 candidate without credentials. Safe c8/c16 headroom plus a conservative required-utilization path promotes one future exact-load measurement, but only after explicit TensorDock account/funding and authenticated delete/direct-lookup authority. A bracketed result identifies the single exact-load telemetry needed; it must not become another broad preparation lineage.
