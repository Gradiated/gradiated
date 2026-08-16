# Exact routed-expert geometry recovery

## Decision question

Do existing valid full-model/depth c16/c32 artifacts contain exact per-token, per-layer top-4 expert IDs or active-expert histograms that can replace uniform-routing assumptions for SM89 scheduling and clustered-trunk decisions?

The current MoE kernel and architecture lines rely on 64/128 assignment counts and worst-case four-cluster charging. Exact workload routing would reveal expert-M skew, empty groups, reuse, and cluster co-occurrence without another GPU run. Absence is also decisive: it keeps clustered execution unidentifiable and prevents another observer project.

## `$0` contract

Within 600 seconds, inspect only retained valid current-AWQ/depth42/depth43 archives, their manifests, raw telemetry, and existing analysis scripts. Do not run the model, reconstruct hidden states, install tools, change provider state, or design a new observer.

- Bind every inspected archive by path and SHA-256 and distinguish output-token histograms from routed-expert IDs.
- If exact route IDs exist, emit layer/token/batch expert-M distributions, empty-expert fraction, active experts, skew, top-4 co-occurrence, and the number of distinct trunks/token under deterministic 4- and 8-cluster assignments. Keep c16/c32 and model identities separate.
- If only aggregate kernel names/times, output vocabulary IDs, or synthetic uniform assignments exist, return `ROUTER_GEOMETRY_UNIDENTIFIABLE`; do not infer route distributions.
- A positive result changes the trunk/delta clustered-cost charge and the expert-sorted scheduler's work descriptors. A negative result freezes worst-case four-trunk accounting and prohibits a follow-up observer/provider arm.

## Starting evidence

- `../nebius_current_awq_c16_direct/`
- `../minimal_depth42_v2_l40s_direct/`
- `../minimal_depth43_v2_l40s_direct/`
- retained L40S V24R2/V25R1 trace analysis
- `../expert_count_geometry/`
