# Product seed decision — 2026-07-13

> Superseded for implementation planning by [`product/docs/PRODUCT_SPEC.md`](../../../product/docs/PRODUCT_SPEC.md). The revised decision builds a revenue-first owned gateway and an external provider surface on the same Rust data plane while preserving the research claim gates below.

## Question and decision

Question: if the model-specific inference co-design thesis survives measured validation, what should the company build first? Should the seed be a gateway with OpenRouter and other provider integrations?

Decision: build a model-specific inference product with a thin compatibility and policy edge, not a generic gateway. The first product should expose one optimized model/workload endpoint behind an OpenAI-compatible API and include the measurement, quality, SLO, cost, rollout, and fallback controls needed to prove that it beats the incumbent on the customer's trace.

OpenRouter should be an adapter and distribution/fallback channel. Direct provider adapters should exist for the benchmark controls and for customers that need transparent billing, residency, or SLO ownership. Neither OpenRouter nor a broad provider catalog should be the product center of gravity.

## Claim scope

In scope:

- A single validated model-specific serving path, initially for the first model and agentic workload where the research produces a scope-matched advantage.
- An OpenAI-compatible request surface with streaming, tool calls, usage accounting, request IDs, and model/version pinning.
- A policy layer that can send eligible traffic to the optimized endpoint, preserve a control path, and fall back on explicit SLO or availability failure.
- Replay, paired quality checks, TTFT/TPOT/E2E SLOs, failure rates, utilization, and fully loaded cost per successful token.
- A small number of provider adapters, including OpenRouter and the direct incumbent providers used for comparison.

Out of scope for the seed:

- A model marketplace or universal model catalog.
- A general-purpose cheapest-provider router.
- Owning every provider integration before a customer or control requires it.
- Custom silicon, hardware leasing, or a broad inference cloud before the software path has repeatable demand and economics.

## Evidence and thesis status

The local research does not yet establish a measured provider advantage or lower delivered dollars per token. The strongest positive result is a component-level architecture-specific kernel speedup; it does not transfer to full-model serving or economics. The current claim-composition gate admits zero joint measured output-cost claims. This makes the seed conditional: product discovery and replay infrastructure are justified now; scaling a production inference fleet is not.

The research thesis becomes product-admissible only when one exact model/intervention/workload/control pair passes all of the following:

1. quality non-inferiority on the frozen task suite;
2. TTFT, TPOT, E2E, concurrency, availability, and failure-rate SLOs;
3. measured goodput and fully loaded cost on the same trace;
4. repeatability across at least two relevant operating regimes; and
5. a positive margin after provider fallback, idle capacity, networking, storage, and operational overhead.

The thesis is falsified for product purposes if the advantage disappears against a tuned incumbent, survives only as a component/bytes/FLOPs result, or requires customer traffic to remain inside a narrow unrepeatable regime.

## Product hypothesis

Customers will pay for a model-specific endpoint when it offers a measurable, quality-preserving improvement on their agent workload and gives them evidence and controls that a generic model router cannot provide: trace-specific routing, cache/prefix policy, model/runtime version identity, quality gates, cost attribution, and rollback.

The key product asset is therefore the validated optimization-and-serving loop. The API gateway is only the delivery boundary.

## Proposed seed architecture

```text
Customer OpenAI-compatible client
                 |
        thin policy / API edge
        |        |          |
 optimized   control     fallback
 endpoint    endpoint    provider(s)
        \        |          /
       trace + quality + SLO + cost ledger
                         |
                replay / rollout evidence
```

### 1. Optimized endpoint

One model, one pinned runtime, one declared workload class, and one reproducible deployment recipe. It should be possible to compare this path with a tuned control without changing the client contract.

### 2. Evidence plane

Capture request geometry, prefix/cache state, model and runtime identity, provider, timing, token usage, errors, quality sample IDs, and cost inputs. Support shadow traffic, deterministic replay, canarying, and automatic rollback. This is the part most directly connected to the research thesis and should be built before a large dashboard.

### 3. Policy edge

Route by workload class and eligibility, not by a generic “cheapest model” heuristic. Examples include long-context agent requests, prefix-heavy sessions, tool-calling requests, and requests requiring a declared data-residency policy. Keep fallback semantics explicit and record every handoff.

### 4. Provider adapters

- OpenRouter: first adapter for fast catalog access, fallback, and distribution experiments.
- Direct control providers: adapters for the exact providers used in the economic comparison, so the control denominator does not depend on a third-party router's aggregation or markup behavior.
- Self-hosted endpoint: a first-class adapter with the same request and evidence contract.

Adapters should be thin and capability-described. Do not normalize away provider features, cache semantics, tool-call behavior, or errors that affect the SLO and cost claim.

## Why not start with a generic gateway?

OpenRouter already provides a unified API, provider routing, ordering, fallbacks, price/throughput/latency preferences, BYOK, and organizational guardrails. Recreating those features would make the seed compete on breadth and distribution while leaving the model-specific economic claim unproven. OpenRouter's own routing metrics are useful inputs, but they are not a substitute for our exact trace, quality contract, or fully loaded cost ledger.

A generic gateway also creates three early risks:

- it optimizes provider selection before we know which workload/model boundary creates value;
- it makes a thin margin business dependent on pass-through volume and provider pricing; and
- it can hide causal differences behind retries, routing changes, and provider-side cache behavior.

The gateway should exist only as the narrowest surface required to deliver and measure the optimized path.

## Integration order

1. OpenAI-compatible edge plus one self-hosted optimized endpoint.
2. One direct incumbent adapter for a reproducible control.
3. OpenRouter adapter for fallback, catalog discovery, and low-friction customer onboarding.
4. A second direct provider only when it changes the SLO, residency, capacity, or economics decision.
5. Additional providers and BYOK only after a real customer requires them or the evidence loop shows a material benefit.

The initial routing policy should be conservative: optimized endpoint first for eligible traffic, direct control or OpenRouter fallback on explicit failure, and shadow/replay traffic for promotion decisions. Avoid cross-model semantic fallbacks for tool-calling or agent workflows until equivalence is measured.

## Seed acceptance gate

Do not launch the paid inference product on a modeled multiplier. Require one customer-like trace with:

- a pinned model and runtime;
- a tuned control path;
- frozen quality and tool-use checks;
- class-level TTFT/TPOT/E2E and availability SLOs;
- measured successful goodput;
- direct infrastructure and provider cost inputs; and
- an auditable comparison artifact that survives replay.

If the optimized endpoint fails this gate, keep the product as an evaluation/replay tool and do not expand the gateway surface.

## Source table

| Source | Retrieved | Evidence type | Relevant fact |
|---|---:|---|---|
| [OpenRouter API reference](https://openrouter.ai/docs/api/reference/overview) | 2026-07-13 | Vendor-reported | OpenRouter normalizes a schema similar to the OpenAI Chat API. |
| [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection) | 2026-07-13 | Vendor-reported | It supports provider ordering, fallbacks, price/throughput/latency sorting, performance preferences, and provider allow/deny controls. |
| [OpenRouter BYOK](https://openrouter.ai/docs/guides/overview/auth/byok) | 2026-07-13 | Vendor-reported | It supports encrypted BYOK credentials, prioritized/fallback keys, and provider-response inspection. |
| [OpenRouter guardrails](https://openrouter.ai/docs/guides/features/guardrails/overview) | 2026-07-13 | Vendor-reported | It provides budgets, model/provider allowlists, ZDR controls, and sensitive-info policies. |
| `research/sol/README.md`, `CONTEXT_HANDOFF.md`, and `docs/OPTIMIZATION_DECISIONS.md` | 2026-07-13 | Measured, analytical, and derived local evidence | The current research has no admitted joint measured cost advantage; model-specific discovery remains the possible wedge. |

## Uncertainty and competing explanations

- A validated optimized endpoint may be a strong internal capability but not a standalone product if customers cannot supply enough trace volume or if providers quickly replicate the optimization.
- Direct provider integration may improve evidence quality but increase operations, compliance, and support burden.
- OpenRouter may be the fastest route to initial demand, but its routing, fallback, and fee behavior can complicate the cost denominator and data/control story.
- The best first workload may be narrower than “agentic inference”; it should be selected by measured margin and repeatability, not market size alone.

## Next action and kill conditions

Next action: define the first endpoint contract and implement the smallest replayable control/optimized comparison around the first model that clears the research gates. Keep OpenRouter behind an adapter interface and do not build a provider marketplace.

Kill or narrow the product if the first validated intervention cannot sustain a material advantage against a tuned direct control, if quality/SLO parity is not repeatable, or if the margin depends on optimistic provider availability and utilization assumptions.
