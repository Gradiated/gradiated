# L40S FP8 projection-oracle failure mechanism

## Decision question

Do the five failed exact-shape output/down-projection oracle checks in the completed single-rank L40S run reflect expected online-FP8 quantization error, a producer/scaling/layout defect, or an invalid oracle construction—and does any answer justify keeping online FP8 ahead of the direct-kernel/W4 alternatives?

This is an independent `$0` offline interpretation project. It must not query or mutate a provider, service, allocation, or the completed paid project. The paid rows remain descriptive and quarantined under the independent program audit; this project cannot promote them to admission evidence.

## Why it matters

The run initialized real TP/PP/DP=1 context and executed all 17 actual consumers. Five projection rows failed the preregistered 0.08 absolute/relative tolerance: sliding output M3679 (0.12890625), global output M12 (0.12890625), global output M3679 (0.34765625), down M12 (0.1796875), and down M3679 (0.5). The same terminal reports a descriptive c12 component of 3.112121484428023 s/request, above both the 1.229949102 planning and 0.698661566 conservative maxima. Distinguishing expected numeric loss from a harness mistake determines whether the next paid direct-kernel packet should retain online FP8, pivot to W4, or close this representation.

## Scope

Inspect the immutable staged program, producer/consumer source identities, deterministic weight/input construction, scale derivation, dtype/layout transformations, BF16 reference, and per-shape errors. Recompute analytical expectations from retained artifacts and source only; no CUDA, image pull, compilation, checkpoint, or synthetic performance claim. Trace one concrete causal chain from observed failures through the exact producer/scaling/source path to the output error. Check whether passing rows and the M12/M3679 pattern falsify likely explanations. Return one typed verdict:

- `genuine_online_fp8_numeric_failure`;
- `producer_or_layout_defect` with one exact future discriminating check;
- `oracle_invalid` with a corrected content-bound oracle contract; or
- `indeterminate_close_on_economics` if the descriptive timing is robust enough to retire the line regardless.

If a correction is warranted, specify only the smallest exact-shape sentinel change for the already-independent direct-kernel packet; do not create another readiness chain or edit that packet while it is owned by another researcher.

## Budgets

- Wall clock: 20 minutes.
- Compute: 2 local CPU-hours; no GPU.
- Storage: 256 MiB retained plus 256 MiB temporary.
- Spend: `$0`; no provider, image pull, checkpoint, compilation, or external mutation.

Write a concise content-addressed `MECHANISM.json`, update `RESEARCH_LOG.md`, and terminalize `STATUS.json`.
