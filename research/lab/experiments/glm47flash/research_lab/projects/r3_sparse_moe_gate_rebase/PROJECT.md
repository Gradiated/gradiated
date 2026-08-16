# R3 sparse-MoE gate rebase

## Question

Does the valid current-AWQ r3 c16 endpoint at `552.171055` output tok/s reopen any sparse-MoE architecture candidate that was closed against the older `535.286104` denominator, without repairing the failed top-2/no-shared forward patch?

## Why this matters

At `$1.10/L40S-hour`, the authoritative `$0.514/M` target still requires `594.466` output tok/s, but the r3 endpoint reduces the required non-overlapped wall-time removal from `9.955%` to `7.1148%`. The old exact-config screen gave fixed top-2 with the shared expert retained only a `6.187%` summed-work ceiling, while the separate 16-expert/top-2 geometry reported a `7.7755%` ideal ceiling. Only the latter even crosses the rebased gate, and then by less than one percentage point. This narrow rebase can either recover one model/chip candidate or prevent a marginal paid arm.

## Fixed evidence

- Current denominator: `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/summary.json`, SHA-256 `23bce62e7a9f10c4d5708630a5351146f0c785ef2bc1281c6757459fb31c8218`, exact cache-off 8,192-input/1,024-output c16, 32/32 complete, `552.1710554232396` output tok/s.
- Sparse proxies: `../adaptive_moe_architecture/artifacts/ADAPTIVE_MOE_C16_PROXY_2026-07-15.json` and `../expert_count_geometry/expert_count_geometry_bound.json`, including their exact checkpoint/config/source bindings and evidence labels.
- Runtime closure: `../config_native_moe_proxy_falsifier/NATIVE_PROXY_FALSIFIER_2026-07-16.json` proves no-shared is not an exact config/checkpoint-native load. The combined patched-forward implementation is closed and must not be repaired or used.
- Endpoint stress: forced exit-35 removed twelve decode layers yet returned only `+1.4123%` contextually; its phase attribution is `UNIDENTIFIABLE`. Do not convert that contrast or overlapping summed kernels into a universal Amdahl coefficient.
- Authoritative decision boundary: `$1.10/hour`, `$0.514/M`, `594.466` output tok/s, exact target workload complete inside 300 seconds. Quality-changing proxies remain architecture-cost evidence only.

## Scope and stop rule

Within 900 seconds, 8 GiB RSS, 64 MiB new artifacts, and `$0`, recompute the exact gate from r3 and adjudicate only:

1. stock-native top-2 with the shared expert retained; and
2. the already-defined 16-expert/top-2 physical geometry.

Reuse the prior exact tensor and source fixtures. Do not broaden to adaptive routing, no-shared execution, expert offload, new expert counts, training, quality evaluation, or another general MoE survey. Bind whether each candidate has a real config/checkpoint representation; for 16 experts, distinguish pruning, merging, and synthetic shape evidence and state the minimum checkpoint materialization/recovery burden. Recalculate ideal endpoint ceilings from the r3 denominator, then stress kernel fragmentation, routed-work transfer, contextual-run uncertainty, and the absence of target-geometry critical-path attribution. An ideal summed-work crossing alone is not a conservative path.

Return exactly one terminal result:

- `NOMINATE_16E_TOP2`: the existing physical geometry plus a conservative transfer bound remains at or above `594.466` with at least a 2% margin (`606.355` tok/s), and one smallest later falsifier is specified without preparing it;
- `ECONOMIC_CLOSE`: every admissible candidate misses `594.466` conservatively or has less than the 2% robustness margin; or
- `REPRESENTATION_CLOSE`: the only numerically surviving candidate lacks an exact materializable checkpoint/runtime representation.

Do not use CUDA, network/provider resources, mutate shared code or checkpoints, repair a closed implementation, or prepare/execute a controller. Produce one compact JSON, any focused project-local analysis script, and a concise research-log handoff.

