# Top-2/shared robust performance bound

## Question

Does the exact top-2/shared c32 measurement remain a material performance and planning-economic signal under every admissible control bound, despite its missing post-control and terminal typed quality/harness failure?

## Why it matters

The corrected session measured `666.860853` tok/s over 64 exact 8K/1K requests versus a valid `611.764559` tok/s pre-control, but the candidate is not a project pass: quality capture truncated, post-control did not run, and top-3 was not triggered. A conservative `$0` bound can decide whether this architecture mechanism is worth later quality/recovery work without retrying or relabeling the failed endpoint.

## Evidence

- `../full47_top2_shared_c32_direct_corrected/artifacts/l40s_top2_shared_c32_20260716_r2/`
- `../full47_top2_shared_c32_direct/` and `../full47_current_background_knee_direct/`
- Campaign gates: `>=606.355` tok/s, `>=1.03x` bracket anchor, and `<=3%` control drift.

## Scope

Work offline only: no provider mutation, CUDA, model execution, capture repair, retry, or successor packet. Verify checkpoint/runtime/workload/config identity and the candidate's request, semantic, cache, and throughput fields. Build a conservative bound from the current pre-control and every scope-compatible exact c32 control, including the worst post-control consistent with the preregistered 3% drift limit. Report planning-rate `$ / M` sensitivity separately from experiment spend.

Return `ROBUST_SIGNAL_PASS` only if the candidate clears both throughput gates under the worst admissible anchor and all non-quality performance evidence is internally valid. Otherwise close. In either case preserve the paid project's typed failure and make no deployable-quality, formal bracket-pass, or provider-beating claim.

## What changes the portfolio

A robust pass nominates top-2/shared as a future quality/recovery target after this discovery portfolio produces sufficient performance evidence. A failed bound closes the mechanism without further spend.

## Available resources

- `/root/workspace/research/factory/tools`
- `/root/workspace/research/sol/experiments/glm47flash/campaign_100`
