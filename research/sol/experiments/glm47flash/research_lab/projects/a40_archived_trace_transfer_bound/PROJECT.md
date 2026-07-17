# A40 archived-trace throughput transfer bound

## Question

Does retained exact-current-AWQ L40S telemetry establish a conservative A40 c8 throughput region that clears 166.819 output tok/s for the campaign's 5% cost gate or 176.968 tok/s for $0.60/M, strongly enough to justify seeking the currently missing TensorDock authority?

## Why it matters

The exact memory study admits A40 c8/c16 with 10.551/6.833 GiB of conservative headroom, but an actual TensorDock load is blocked on account, funding, authenticated delete, and direct-instance authority. The retained V24R1/V24R2 exact `ab31d120...` AWQ c8 controls measured 364.105/364.871 output tok/s on L40S at the same 8,192/1,024 geometry. At TensorDock's conservative $0.38225/hour screen, A40 therefore needs only 45.82% of the lower retained L40S result for the 5% gate and 48.60% for $0.60/M. A model- and trace-specific transfer bound can decide whether asking for external authority is rational without another provider-controller lineage.

## Scope

Run one $0 archived-evidence falsifier. Bind the exact identities and extract the V24R1/V24R2 stock c8 request rows, trace regions, GPU telemetry, runtime configuration, kernel families, and any retained profiler evidence that can separate compute-, HBM-, launch-, and host-limited time. Reconcile V26R1/V27R1/V28R1 only as sensitivity checks and exclude changed split arms from the stock denominator.

Construct explicit optimistic, central, and conservative A40 transfer bands using official A40 and L40S compute, memory-bandwidth, memory-capacity, and interconnect specifications. Apply component-wise roofline/scaling rather than a single peak ratio, avoid summing overlapping kernel time, and include prefill/decode separately. Account for A40 architecture/runtime compatibility, AWQ kernel support, clocks/power, and the retained workload's observed host/queue contribution. Report the exact fraction of L40S throughput that each bottleneck model implies and the assumptions needed to remain above both economic gates.

This is a direct scientific falsifier, not a throughput prediction or delivered-cost claim. If archived evidence cannot identify enough of the serving wall, return a conservative partial-identification interval and name the single A40 telemetry signal that would collapse it. Do not write a provider adapter, request credentials, mutate a provider, load a model, or repair Nebius. Budget is $0 and provider ownership is prohibited.

## Evidence and artifacts

- Current checkpoint revision: `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- Retained stock c8 controls: V24R1 364.105 tok/s, V24R2 364.871 tok/s; V26R1/V27R1/V28R1 are sensitivity evidence.
- Retained V24R2 trace/telemetry/archive and the campaign's observer artifacts.
- `a40_exact_memory_admission/A40_ADMISSION_RESULT.json` and the TensorDock venue screen.

Produce a deterministic analysis script, a machine-readable result binding all input hashes, and a concise research-log decision. Label measured, vendor-reported, derived, and inferred evidence separately.

## Portfolio-changing result

A conservative upper bound below 166.819 tok/s closes A40 without external authority. A conservative lower bound above 176.968 tok/s promotes exactly one future authenticated A40 c8/c16 load. An interval crossing either gate keeps A40 conditional but must identify only the cheapest decisive on-device signal; it does not authorize more controller preparation.
