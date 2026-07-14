# ADR-0002: Opinionated managed inference product

- status: partially superseded by ADR-0003, ADR-0008 and the 2026-07-14 simplicity review; curated-not-marketplace, strict capability, fixed-price release, prepaid and distribution decisions remain accepted
- GitHub issue: https://github.com/joshsny/gradiated/issues/3
- owner: product architecture
- date: 2026-07-13

## Decision

> Current implementation uses concrete curated provider IDs plus qualified `grad/<effort>/<speed>` aliases. The seed protocol surface is Models, OpenAI Responses and Anthropic Messages only. The five named products, Chat Completions, Embeddings and Hugging Face native channel below are historical proposal detail, not seed scope. See [the system manual](../SYSTEM_MANUAL.md).

Build a curated inference product rather than an OpenRouter feature-for-feature marketplace.

The default public catalog contains five managed products—`grad/auto`, `grad/fast`, `grad/smart`, `grad/code`, and `grad/open`—plus a small qualified set of concrete model IDs. A managed product resolves through an immutable, fixed-sell-price route release with explicit capability/privacy eligibility, deterministic canary assignment, session stickiness, bounded pre-output fallback, actual-model disclosure, and a rollback target. A concrete pin may retry the same model on another qualified endpoint but never changes model family.

Owned inference is strategically preferred only when its exact model/endpoint/runtime scope passes the same capability, quality, privacy, region, SLO, capacity, and margin gates as external supply. Grad inference remains independently OpenAI-compatible and can sit behind customer-configured third-party gateways using the customer's workspace key. OpenRouter is the first native downstream distribution channel and Hugging Face is the second planned native channel for owned/differentiated supply; each uses separate channel credentials and receivable accounting. OpenRouter-upstream access is operator-only fallback/benchmark supply, not the default breadth strategy.

The seed console has five primary screens: Overview, API keys, Models, Usage, and Billing. The Default workspace, providers, route weights, fallbacks, variants, and health machinery are hidden from first use. The seed inference API supports model listing, Chat Completions, Anthropic Messages, a stateless Responses subset, and Embeddings. Unsupported semantics fail explicitly.

## Context and constraints

OpenRouter's current public documentation describes a broad marketplace and programmable substrate: many protocols and modalities, provider/model routing variants, workspaces/budgets, BYOK, privacy/logging controls, plugins, hosted tools, agent SDKs, caching, observability exports, and provider onboarding. Breadth is useful, but presenting that machinery directly conflicts with the desired “Apple-like” experience: a fast, predictable path to reliable frontier and open-model inference and our differentiated supply.

The existing architecture also requires prepaid organization credit, hard workspace/key limits, PostgreSQL financial authority, Redis as the gateway's only synchronous internal state/control dependency, fixed/reproducible charges, TS/Rust generated contracts, and property-based verification. Managed routing must preserve those invariants and cannot make cost or privacy depend on an opaque model-provider choice.

## Alternatives considered

1. **Chosen: curated managed products plus concrete pins.** Preserves common outcomes, hides operational choices, and gives us a controlled route-release/evaluation loop.
2. **OpenRouter clone.** Rejected because marketplace breadth, provider controls, plugins and agent/runtime features create support/privacy/billing surfaces before differentiated revenue is proven.
3. **Provider integration only.** Rejected because external acceptance is controlled by others and it forfeits direct revenue, product learning and the customer relationship.
4. **Broad direct gateway backed by OpenRouter upstream.** Rejected as the default because it introduces an extra marketplace hop, variable behavior and circular resale without strengthening our inference advantage.
5. **Owned inference only.** Rejected for seed because selected frontier providers improve capability coverage and reliability while owned models qualify.

## Consequences

- positive: five-minute onboarding; small explainable surface; stable fixed prices; explicit behavioral/privacy guarantees; differentiated owned-inference path; auditable releases and rollbacks.
- positive: the gateway still retains the hard engineering needed for production—capability filtering, health routing, retries, caching awareness, metering, billing, privacy and failure credits—without exposing it as setup.
- positive: customers may call Grad directly or through their existing OpenAI-compatible gateway; native marketplace listings add reach without creating another inference runtime or forcing adoption of Grad's first-party gateway.
- negative: fewer models/modalities at launch; ModelOps qualification and route-release tooling become critical-path product infrastructure; we absorb provider buy-price variance and route-quality risk.
- negative: customers needing arbitrary provider order, BYOK, deep guardrails, hosted plugins/tools, media generation, or regional guarantees wait for evidence-gated follow-ons.
- migration or rollback: managed aliases are additive to concrete model IDs. A release rolls back by atomically repointing its head while in-flight requests retain their admitted release/price. The product strategy can broaden the advanced catalog or routes without changing organization billing or the gateway's Redis state/control boundary.

## Evidence

- [OpenRouter feature decisions](../../product/docs/OPENROUTER_FEATURE_DECISIONS.md): vendor-reported feature inventory and analytical keep/simplify/defer/reject decisions.
- [Product specification](../../product/docs/PRODUCT_SPEC.md): analytical customer and UX contract.
- [Architecture](../../product/docs/ARCHITECTURE.md): derived managed-route/control-data-plane architecture.
- [Billing and Redis](../../product/docs/BILLING_AND_REDIS.md): derived fixed-price reservation and correction invariants.
- [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers): vendor-reported, time-sensitive downstream requirements.
- [Open distribution and gateway integration plan](../../product/docs/DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md): source-backed target, principal, package and harness decision.

No live provider request, authenticated OpenRouter UI inspection, or paid experiment informed this decision.

## Reversal trigger

Revisit the five-product/default-surface decision when at least ten funded organizations show repeated failure to map workloads to the products, materially prefer concrete pins, or require one omitted capability for retained revenue. Revisit fixed route pricing if measured workload replay cannot maintain the launch margin envelope. Revisit provider-only sequencing if a distribution partner offers accepted, economically material volume before the direct gateway is launch-ready. Any reversal must retain explicit capability/privacy behavior, concrete-pin fidelity, auditable pricing, and prepaid admission unless a separate ADR replaces those guarantees.
