# MTP acceptance and overhead bound

## Question

Can GLM-4.7-Flash's native MTP path plausibly improve fixed-workload c8 SLO-goodput by at least 5%, and what measured acceptance/overhead threshold would be required?

## Why it matters

MTP is a model-architecture serving lever independent of caching, batching, hardware, and custom kernels. It has zero valid campaign measurements because earlier H100 lineages stopped before the arm ran. A cheap deterministic bound can either kill another expensive delivery attempt or define the exact counters and threshold for one later matched off/on experiment.

## Relevant evidence

- Opportunity `OPP-006` in `campaign_100/analysis/OPPORTUNITY_REGISTER_2026-07-14.json`.
- Retained complete-BF16 H100 V13 request/service artifacts and pinned SGLang runtime source.
- The campaign materiality gate is repeated >=5% c8 SLO-goodput with exact semantic identity.
- No acceptance rate, draft overhead, verification work, or valid MTP performance result exists.

## Scope

Perform a zero-provider source/capability audit and deterministic acceptance-overhead simulation. Recover the native draft width/configuration and runtime accounting if supported; derive the minimum accepted draft tokens or acceptance fraction needed to clear 5% over measured c8 behavior across explicit draft/verify overhead scenarios. Separate prefill, decode, and non-draftable work where retained evidence permits, and label missing phase data rather than importing another model's rates. Falsify unsupported runtime/checkpoint combinations immediately.

Do not launch a provider resource, repair checkpoint delivery, modify runtime code, study prefix caching/batching/hardware, or claim speedup from the simulation. Produce one compact reproducible artifact and stop after the promote/kill decision.

## Available resources

Use V13 artifacts, campaign reports/configs, pinned SGLang sources, and shared analysis tools. Budget is $0 and the result should fit one researcher turn.

## Portfolio-changing result

A supported native path with a realistic threshold and a conservative >=5% predicted c8 effect promotes one later matched MTP off/on preregistration after quality admission. Unsupported execution, an implausible acceptance requirement, or an upper bound below 5% closes MTP for this campaign.
