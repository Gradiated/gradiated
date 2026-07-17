# Exact-revision W4 producer and quality route

## Decision question

Is there one content-addressed W4 producer/checkpoint route for exactly `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4` that can feed the pinned vLLM Marlin consumer without transferring quality claims, and what is the cheapest later raw-output/feature gate that could falsify it?

## Scope

This is independent `$0` evidence while the paid component owner runs. Start from `../gemma_l40s_w4_c16_economic_bound/W4_COMPONENT_PACKET.json` and the exact identities in the paid project's brief. Audit first-party producer/loader source, content-addressed public metadata, revision provenance, quantization recipe/calibration requirements, tied-head handling, file sizes, licenses, and claimed runtime compatibility. Search for an already-produced checkpoint only when its base revision and representation are provable; otherwise specify at most one deterministic producer route from the exact base. Do not download full weights, run CUDA, mutate a provider, compile kernels, or execute quality evaluation.

The output must distinguish measured metadata, first-party source, vendor/community claims, derived facts, and inference. Reject a route whose base revision, calibration data/recipe, group size, zero-point layout, tied-head behavior, or runtime consumer cannot be bound. Do not accept model-name similarity as provenance.

If a credible route exists, emit one conditional packet with immutable source/checkpoint identities, expected bytes and staging time, exact producer/loader commands or APIs, and a later quality falsifier. The quality gate must preserve raw outputs and cover text-only non-reasoning instruction behavior, chat-template/stop behavior, long 10K context, local/global attention behavior, and logits/features against the exact BF16 base before endpoint promotion. Define tolerances or a calibration procedure without claiming they pass. If no route satisfies provenance, emit typed `none` and identify the cheapest missing fact; do not create another preparation project.

## Budgets

- Wall clock: 60 minutes.
- Compute: at most 2 local CPU-hours; no GPU.
- Storage: 2 GiB project-local total and at most 256 MiB bounded metadata/source probes; shared `/tmp` is forbidden.
- Spend: `$0`; provider mutation, full-weight download, CUDA, and quality execution are forbidden.

Write `ROUTE_DECISION.json`, a concise `DECISION.md`, `RESEARCH_LOG.md`, and terminal `STATUS.json`.
