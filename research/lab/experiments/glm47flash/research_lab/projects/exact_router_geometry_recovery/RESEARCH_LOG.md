# Research log

## 2026-07-16 — Director opening handoff

Use the free `$0` slot after FP8 implementation close to resolve a shared MoE uncertainty from existing evidence. Recover exact per-layer top-4 IDs/M only if the valid archives actually retained them. Output-token histograms and kernel-time aggregates are not routing evidence. If routes are absent, close within 600 seconds, preserve worst-case four-trunk accounting, and do not propose another observer/provider run.

## 2026-07-16 — Terminal archive audit: ROUTER_GEOMETRY_UNIDENTIFIABLE

Hash-bound the retained current-AWQ c16, depth42 c16/c32, and depth43 c16/c32 archives and inspected manifests, JSON payloads, request rows, telemetry, and logs for actual routed-expert IDs. The audit artifact records the archive and summary SHA-256 identities. Current-AWQ has 156 request rows and no histogram; depth42 and depth43 have 288 request rows each and 290 complete `output_token_histogram` rows each. No archive member contains route IDs, expert IDs, layer/token route tensors, top-4 assignments, or co-occurrence data. The prior expert-count artifact is explicitly a derived/synthetic uniform-routing proxy, not an observation.

Output vocabulary IDs, kernel names/times, and synthetic uniform assignments cannot identify exact MoE routing. Exact per-layer `M`, skew, empty experts, active experts, top-4 co-occurrence, and 4/8-cluster trunk counts remain null for both c16 and c32. Decision: `ROUTER_GEOMETRY_UNIDENTIFIABLE`; freeze worst-case four-trunk accounting and prohibit an observer/provider successor.
