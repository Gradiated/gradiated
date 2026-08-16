# MoE expert-offload cost bound

## Question

Can GLM-4.7-Flash's 30B-A3B MoE structure support a quality-preserving expert-residency/offload policy that makes cheap 24–32 GiB GPUs economically viable for the fixed background workload, or do PCIe traffic and cache-hit requirements rule it out?

## Why it matters

The verified AWQ weights occupy 20.17 GB, which nearly fills a 24 GiB GPU before KV, activations, and workspaces. Yet only a subset of experts is active per token. A model-specific expert cache or CPU-offload policy could trade background latency for much cheaper hardware, a mechanism distinct from batching, kernels, runtime upgrades, and the A40 placement. Conversely, if exact expert bytes and routing imply impossible PCIe traffic or cache-hit rates, the lab should close this attractive-sounding branch without GPU spend.

## Relevant evidence

- Exact current model config and tensor index identify GLM4-MoE-Lite layers, routed/shared experts, top-k routing, quantized tensor sizes, and 20.17 GB total weights.
- The campaign permits slower hardware and longer queues when they materially reduce all-in token cost.
- Dense/MoE custom kernel work was closed because retained serving-wall transfer could not support 5%; this project changes residency/topology rather than individual kernels.
- Current vLLM and other primary runtime sources may expose generic CPU offload or expert-placement hooks, but interface existence is not performance evidence.

## Scope

Run one zero-cost exact-model source/simulation falsifier. Parse the current safetensors index to calculate bytes for shared weights, attention, embeddings/head, each routed expert, shared experts, and per-layer quantization metadata. Derive the minimum always-resident set and the GPU space available for expert caching on representative 24 GiB and 32 GiB devices after exact c1/c8 KV plus conservative runtime/workspace reserves.

Using exact top-k/expert counts, bound per-token PCIe transfer under worst-case, uniform routing, and optimistic stable agent-workload locality. Calculate the cache-hit rate, expert reuse distance, PCIe bandwidth, and transfer/compute overlap required to sustain the output tok/s corresponding to <=$0.6365/M and <=$0.60/M at at most three current, actually listed low-cost device rates. Inspect current primary runtime/source support for layer/expert CPU offload or expert caching, pinning one plausible implementation path; do not infer performance merely from a flag.

Implement a deterministic simulator or analytical artifact with explicit quality invariance: weights remain bit-identical and only residency changes. Include prefill and decode separately, queue/batch sensitivity, host RAM and pinned-memory needs, model-load/recovery cost, and a conservative no-overlap case. Rank at most one prospective implementation/measurement geometry with exact admission/stop rules.

Do not use provider credentials, create hardware, download another checkpoint, run GPU code, redesign weights, prune experts, modify routing, or reopen the closed kernel project. Budget is $0 with no provider ownership.

## Available resources

Use the exact current AWQ config/index, vLLM and other primary runtime sources, `campaign_100` workload/telemetry, official PCIe/hardware specifications, current public provider rates, and shared analysis tools.

## Portfolio-changing result

If even optimistic cache locality or full overlap cannot clear the cost gate, close expert offload for this campaign. A conservative feasible region with an existing implementation path and >=5% economic margin earns one later bounded prototype after a current control or independently measurable venue exists. Keep all external rates and locality assumptions labeled; no simulated result is a delivered-cost claim.

## Director correction — Cycle 22

The first result is not accepted as a capacity decision. It used `kv_bytes_per_token_conservative=2048`, whereas the higher-fidelity pinned vLLM MLA accounting in `a40_exact_memory_admission` derives 54,144 bytes/token across 47 layers. At c8 that is 3.718 GiB, not about 0.141 GiB, and it reverses the claim that 20.17 GB of weights plus a 4 GiB runtime reserve fits a 24 GiB device.

Run exactly one correction turn. Recompute c1/c8 capacity for 24 and 32 GiB from the source-derived MLA page equation, 90% runtime allocation ceiling, exact weights, alignment, and at least the same expected/conservative non-KV bands used by the A40 study. Then recompute the minimum expert bytes that must be absent from GPU, the resulting cache size, PCIe traffic, cache-hit gates, prefill refill cost, and economics for the previously screened device rates. Reconcile every number with the A40 artifact and amend the old result rather than silently replacing it. Nominate a prototype only if the corrected 24/32 GiB geometry actually needs offload and a conservative existing implementation path clears the campaign gate by at least 5%; otherwise close. Budget and provider authority remain $0/none.
