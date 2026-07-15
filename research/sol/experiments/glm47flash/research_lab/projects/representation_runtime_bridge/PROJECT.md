# One-factor representation and runtime bridge

## Question

Is there a feasible, causally interpretable one-factor bridge that separates representation, runtime, or hardware effects in the bundled AWQ/vLLM/L40S versus BF16/SGLang/H100 endpoint difference, and is it valuable enough to measure?

## Why it matters

The best retained endpoints are AWQ/vLLM/L40S at 355.772 output tok/s and a derived $0.670/M output tokens versus BF16/SGLang/H100 at 305.045 output tok/s and $3.528/M. That difference is economically large but changes representation, runtime, checkpoint implementation, hardware, and price together. The campaign cannot call it model-specific co-optimization or identify the next mechanism without a bridge. This project supplies a materially different hypothesis from quality calibration, batching, and prefix reuse.

## Relevant evidence

- Opportunity `OPP-005` in `campaign_100/analysis/OPPORTUNITY_REGISTER_2026-07-14.json`.
- `campaign_100/allocations/nebius_h100_complete_stock_v13/` and `campaign_100/allocations/nebius_l40s_vllm_awq_prefill65k_v21/`.
- V21's measured 355.772 output tok/s, exact geometry and SLO pass, and derived $0.670/M endpoint.
- V13's measured 305.045 output tok/s and derived $3.528/M endpoint.
- Both endpoints fail the current absolute quality screen, so they support mechanism design and paired diagnostics only.

## Scope

Start with a zero-cost feasibility matrix over exact checkpoint availability, runtime model support, activation/weight memory, target GPU placement, workload compatibility, and retained artifact comparability. Reconstruct the narrowest arms that would change exactly one of representation, runtime, or hardware while holding model semantics, fixed c1/c8 geometry, generation, quality diagnostic, cache state, scheduling intent, and SLO accounting fixed. Quantify expected discrimination, cost, and the cheapest falsifier; prefer artifact reanalysis, source/capability inspection, analytical bounds, or a deterministic simulation before proposing hardware.

Do not run a provider experiment in the first stage, alter the quality suite, tune batching or prefix caching, revive observer instrumentation, modify kernels, or study MTP. Reject a bridge that silently changes checkpoint implementation or cannot preserve a defensible semantic identity. Leave room for the researcher to choose the most informative feasibility method.

## Available resources

Use the shared factory tools, retained V13/V21 artifacts, campaign model manifests and runtime sources, provider capability controls, and the OPP-005 contract. No provider mutation or paid allocation is authorized in the first stage.

## Portfolio-changing result

A single feasible one-factor arm with strong discrimination and a bounded path to a repeated >=5% serving effect may be preregistered for one later session after quality and provider-lifecycle gates permit it. If no exact one-factor bridge is feasible, close causal attribution for these endpoints and report the 81% cost difference only as a bundled stack result. Neither outcome repairs the absolute quality failure or creates a provider-comparative claim.
