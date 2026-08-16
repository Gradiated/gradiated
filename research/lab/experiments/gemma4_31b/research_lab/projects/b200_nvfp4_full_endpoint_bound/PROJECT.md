# B200 NVFP4 full-endpoint feasibility bound

## Decision question

After the exact W4 H100 endpoint and its decode discriminator, can a full B200 native-NVFP4 serving stack still plausibly beat the campaign's price-normalized market ceiling, or does the measured non-linear/non-kernel residual close B200 before venue spend?

This is a new full-stack transfer question, not a repeat of the completed SM100 linear-kernel mechanism. The prior mechanism established that exact Gemma linear shapes can have enough native-NVFP4 kernel upside in isolation. The new H100 endpoint evidence now supplies the missing complete-request and actual FP8-KV/local-global-attention residual needed to decide whether that isolated upside can matter economically.

## Bound evidence

Consume only the content-bound artifacts needed for this decision:

- `../h100_w4_full_endpoint_background_frontier/RECONCILED_TERMINAL.json` for the valid c128/c96 complete-request rows, queue/prefill/decode decomposition, runtime contract, and H100 target;
- `../h100_w4_decode_residual_mechanism/RECONCILED_TERMINAL.json` for actual c128 FP8-KV update, local/global selected paged-attention, context/launch controls, and the earliest-completion bound;
- `../h100_w4_background_concurrency_frontier/RECONCILED_TERMINAL.json` for the passing W4-linear-plus-actual-head c128 proxy;
- `../b200_exact_gemma_kernel_economic_mechanism/MECHANISM.json` for exact SM100 native-NVFP4 source, geometry, payload, and price-hurdle identities;
- `../b200_nvfp4_exact_shape_direct_falsifier/` only for its staged evaluator identity and typed venue boundary. Do not reopen venue discovery or execute it in this project.

Record SHA-256 identities for every consumed artifact. If a referenced metric cannot be recovered from those artifacts, label it unknown rather than filling it from a log or another model/workload.

## Required causal analysis

Build a reproducible lower/upper-bound model at c128 first. Use c96 only when it changes the decision.

1. Partition the measured H100 batch wall into components that may transfer to SM100 native NVFP4, actual FP8-KV update and local/global attention, prefill, queue/scheduling policy, head, and irreducible service/runtime time. Prevent overlap between the endpoint metrics and the synchronized mechanism loop.
2. Trace the pinned SM100 runtime/source support for the actual Gemma attention/KV path. Do not apply peak-bandwidth, peak-FLOP, or H100-to-B200 ratios to an unsupported backend. Give each component an explicit evidence class: measured, source-derived, analytical, inferred, or unknown.
3. Evaluate an impossible optimistic bound (zero all NVFP4-compressible work), a source-supported optimistic bound, and a conservative executable bound. Include the tied BF16 head and the observed queue/earliest-completion constraints.
4. Use the current content-bound B200/H100 planning prices in the mechanism artifact unless a newer repository-owned authenticated price artifact exists. State the exact B200 seconds/request and batch-time hurdle. Do not browse or perform provider mutation merely to refresh a price.
5. Derive the minimum simultaneous reductions required from linear, attention/KV, and scheduling/service work. Test whether a scheduling change is an independent intervention or merely removes queue delay while leaving the earliest completion above the price hurdle.
6. Compare the surviving upside with the previously staged 24-row component falsifier. A component-only survivor is insufficient if the full-stack lower bound already misses.

## Terminal decision

Emit exactly one:

- `reopen_b200_direct_falsifier`: only if a source-supported full-stack bound beats the price-normalized hurdle with at least 20% batch-time headroom after tied-head, attention/KV, and irreducible service allowances. Name the exact remaining GPU discriminator and retain the existing staged evaluator; do not create a successor readiness project.
- `close_b200_fullstack`: if even the impossible optimistic or source-supported bound misses, or if reaching the hurdle requires an unsupported backend plus another independent intervention. Close without GPU or venue work.
- `typed_unknown`: only when a specific missing source/runtime fact prevents either bound. Name one provider-free artifact that would resolve it; generic uncertainty is not sufficient.

This project makes no kernel performance, endpoint performance, quality, deployability, or provider-availability claim. It may not activate a GPU owner itself.

## Budgets and artifacts

- Researcher profile: `deep`.
- Wall clock: 50 minutes.
- Compute: 2 local CPU-hours; no GPU and no provider mutation.
- Storage: 1 GiB project-local, including at most 256 MiB of source/image probes; do not use shared `/tmp`.
- Spend: `$0`.

Write a reproducible script, `FULLSTACK_BOUND.json`, concise `DECISION.md` and `RESEARCH_LOG.md`, and terminal `STATUS.json`.
