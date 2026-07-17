# AMD AWQ multi-replica screen

## Question

Can the exact current GLM-4.7-Flash AWQ checkpoint run through a supported ROCm engine on one currently rentable high-memory AMD GPU in a replica/topology geometry whose sustainable output cost plausibly beats both the measured L40S c16 point and the strict provider hurdle?

## Why it matters

The L40S c16 point is now saturated: 535.286 output tok/s, $0.445308/M productive output, 98.36% mean GPU utilization, and 44,103/46,068 MiB peak memory. More sequences cannot clear the 5% gate. The 20.2 GB AWQ checkpoint may instead benefit from a high-memory AMD device carrying multiple replicas or a different engine, but Wafer's MI355X results are for GLM-5.2 and cannot be transferred to this checkpoint, representation, workload, or topology.

## Relevant evidence

- Current checkpoint `cyankiwi/GLM-4.7-Flash-AWQ-4bit@ab31d120fbe79988fe2a0259993cf3c222aa8881`, compressed-tensors AWQ, approximately 20.2 GB.
- `nebius_current_awq_c16_direct` measured cache-off 8,192-input/1,024-output c16 on vLLM 0.15.0/L40S; `current_awq_saturation_bound` closes c24/c32 on that geometry.
- The strict retained market hurdle is $0.568889/M output; the current productive-hour self-hosted denominator is $0.445308/M before lifecycle overhead.
- `research/sol/docs/WAFER_AI_FULL_STACK_DEEP_DIVE_2026-07-15.md` supplies a cross-layer AMD method and explicit transfer limits.

## Scope

Run one zero-provider, current-source falsifier across at most three AMD GPU-plus-venue candidates. For each candidate, bind current orderability and all-in hourly rate, memory capacity, exact compressed-tensors AWQ support in a specific pinned ROCm engine/runtime, GLM-4.7 architecture support, and a feasible one-GPU replica or topology geometry. Prefer official runtime documentation/source, provider catalogs, and reproducible exact-model artifacts; label vendor performance as a prior.

Use the measured L40S c16 telemetry and exact workload to derive, not assume, conservative bandwidth/compute/replica throughput intervals. Calculate the output-token throughput required to beat $0.568889/M and $0.445308/M at each rate, then include explicit utilization, setup/reload, interruption, storage, and orchestration sensitivity. Treat aggregate replicas as sharing one device's bandwidth/compute; do not multiply single-replica throughput without a resource bound. Separate a safe benchmark venue from a credible production placement.

Nominate at most one later exact-load measurement only if checkpoint load, engine support, current capacity/rate, memory geometry, and a conservative economic path all survive. State the exact image/runtime, hardware, replica/topology geometry, measurement venue, production venue, and minimum aggregate throughput. Otherwise close AMD for this GLM-4.7 AWQ campaign. Do not invoke a provider, build a controller, convert or mutate the checkpoint, import GLM-5.2/MXFP4 results, or start kernel work.

## Available resources

Use the Wafer full-stack review, current AWQ/c16 artifacts, `campaign_100` economics and telemetry, official vLLM/SGLang/ROCm sources, provider catalogs, and shared factory analysis tools. Produce a machine-readable candidate matrix, reproducible calculations, and a concise research-log decision.

## Portfolio-changing result

One fully bound AMD candidate with a conservative path below $0.445308/M earns a single later exact-load and matched-workload benchmark after quality releases provider ownership. A candidate that can beat only $0.568889/M remains a production alternative, not the new frontier. Missing exact AWQ support, live capacity, or economic headroom closes the branch without implementation work.
