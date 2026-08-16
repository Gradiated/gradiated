# Student42 measured-depth transfer falsifier

## Question

Do the scope-matched measured L40S endpoints for the full 47-layer current-AWQ model and physical 39-layer student support a conservative 42-layer throughput interval above the campaign's `594.466` output-tok/s / `$0.514/M` gate, or does the candidate's marginal analytical case disappear once measured fixed, depth-scaled, concurrency, and workload effects are respected?

## Why it matters

The clean 42-layer proxy is the nearest executable model divergence after full-model FP8 c32, but its inherited `597.529`-tok/s work bound clears the gate by only `0.515%`. The same exact L40S workload measured `535.286` tok/s for 47 layers and `674.424 / 661.661 / 734.557` tok/s for the 39-layer c16/c24/c32 frontier. No project has used their raw request, metrics, and telemetry rows to calibrate the 42-layer decision. A bounded measured transfer can either strengthen the next direct GPU falsifier or prevent a marginal allocation while r3 remains independently owned.

## Fixed evidence

- Full 47-layer c16 result and raw archive:
  - `../nebius_current_awq_c16_direct/artifacts/nebius_current_awq_c16_direct_2026-07-15-r2/summary.json`
  - `../nebius_current_awq_c16_direct/artifacts/nebius_current_awq_c16_direct_2026-07-15-r2/vllm-awq-batch.tar.gz`
  - `535.2861037029285` output tok/s, exact cache-off 8,192-input/1,024-output background workload.
- Physical 39-layer result and raw archive:
  - `../distilled_depth_student_architecture/artifacts/nebius_l40s_student39_c16_c24_c32_2026-07-15-r2-repair02/summary.json`
  - `../distilled_depth_student_architecture/artifacts/nebius_l40s_student39_c16_c24_c32_2026-07-15-r2-repair02/vllm-awq-batch.tar.gz`
  - `674.424 / 661.661 / 734.557` output tok/s at c16/c24/c32; all 144 requests complete; terminal archive SHA-256 `f9f3f77da53d30e87604d8a0f8c1ddd81e8bed65bab100896b06b5c6a7b35383`.
- Student42 exact accounting and clean identity:
  - `../minimal_change_c32_codesign/CANDIDATE_COMPARISON.json`
  - `../minimal_depth42_clean_materialization/CLEAN_MATERIALIZATION_RESULT.json`
  - 42 serving layers with skipped source layers `[6,15,24,33,42]`, projected c32 headroom `2,401.977` MiB, and derived work bound `597.529` tok/s.
- Authoritative economics: `$1.10/L40S-hour`, `$0.514/M` output tokens, `594.466` output tok/s. All background arms must complete within 300 seconds; latency below that envelope is secondary.

## Scope

At `$0`, consume the existing summaries and raw archives once. First bind comparability: exact workload geometry, cache policy, runtime/model representation, `num_kv_splits`, request completion, and any material server/launcher differences. If these identities cannot support a depth transfer, return `UNIDENTIFIABLE` rather than manufacturing a bound.

Use the smallest defensible measured model. The researcher may choose a monotone or affine time decomposition, constrained bootstrap, or another transparent interval method, but must:

1. distinguish fixed from depth-scaled work only where the artifacts support it;
2. preserve prefill/decode, queueing, and complete-background effects rather than scaling nominal layer count alone;
3. treat student39's c24/c32 behavior as concurrency evidence, not automatically transferable uplift;
4. report c16 and c32 separately, with a zero-c32-uplift stress case and adverse fixed-cost/measurement assumptions;
5. show sensitivity to both endpoint sampling uncertainty and model-form uncertainty; and
6. label interpolation, inference, and measured inputs explicitly.

Do not inspect or modify the active r3 service, query or mutate a provider, use CUDA/network access, edit launchers or checkpoints, perform runtime/loader preparation, train, evaluate quality, or open a successor analysis. This project does not authorize student42 spend.

## Decision, budget, and stop rule

Maximum wall time is 600 seconds, maximum new artifact size is 32 MiB, and provider spend is zero. Produce one result and stop.

- `NOMINATE`: an explicitly conservative lower bound clears `594.466` tok/s by at least 2% (`606.355` tok/s), preserves complete requests inside 300 seconds, and remains above the gate under zero c32 uplift or another clearly conservative operating point. Student42 then remains the sole model-divergent paid fallback after r3.
- `PARK`: the conservative interval misses `606.355` tok/s or materially crosses the economic gate. Do not spend a GPU merely to resolve the marginal analytical bound.
- `UNIDENTIFIABLE`: the two measured identities cannot support the required interval. Do not open another transfer/preflight project; only a later director may decide whether the direct measurement's information value justifies it.

Regardless of this result, a valid full-model FP8 c32 arm at or above `594.466` tok/s supersedes student42. A valid r3 OOM, invalid FP8 mechanism, or sub-gate result can activate a `NOMINATE` decision after verified cleanup. An operationally null r3 must first be classified under the near-stock stop rule.

## Artifact contract

Produce one compact JSON with input hashes and identity checks, measured rows used, method and assumptions, c16/c32 point intervals and stress cases, the `606.355`-tok/s robust-margin test, latency/completion treatment, and the typed decision; add only a concise `RESEARCH_LOG.md` update and any focused analysis script needed for reproduction.
