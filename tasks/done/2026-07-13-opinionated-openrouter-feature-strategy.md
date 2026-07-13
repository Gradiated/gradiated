# Task: 2026-07-13-opinionated-openrouter-feature-strategy

## Outcome

The repository contains a current official-doc inventory of OpenRouter capabilities, an explicit keep/simplify/defer/reject/operator-only decision for each, and a revised opinionated product/UX/architecture contract optimized for smooth adoption, reliable frontier/open-model access, and routing to qualified owned inference.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/3
- GitHub project: unavailable to the current fine-grained token; human-managed until Project access exists
- owner: Codex
- Codex thread: current product strategy thread
- created: 2026-07-13T17:28:32+00:00
- started: 2026-07-13T17:28:32+00:00
- completed: 2026-07-13T19:45:34+02:00
- scope: `product/docs/**`, `product/README.md`, `product/HANDOFF.md`, `product/AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/decisions/**`, and this packet
- excluded paths: `research/**`, infrastructure implementation, product code, credentials, account-only OpenRouter UI, paid/API requests
- dependencies: product architecture `af06af9`, infrastructure architecture `ebc172a`

## Contract

- hypothesis or user value: a curated product that hides provider/routing machinery behind strong defaults can preserve the capabilities needed for production frontier and open-source models while materially reducing setup and operating burden compared with a marketplace-style gateway.
- acceptance checks: current official-doc source table; comprehensive feature taxonomy; every feature marked keep, simplify, defer, reject, or operator-only with rationale; seed UX and progressive disclosure; public API/model/routing contract; owned-inference preference; reliability/fallback/privacy/cost behavior; data/control/gateway architecture deltas; migration of existing docs/work packages.
- quality gate: source claims are vendor-reported and dated; recommendations are analytical; uncertainties and account-only gaps are explicit; no feature is removed solely for aesthetic simplicity if production reliability needs it; existing billing/Redis invariants remain intact.
- SLO or budget: $0 and no provider/account/commercial mutations or paid requests; ordinary GitHub issue tracking only; five-minute first successful request as the UX target; planning completed in this turn.
- timeout: one planning/research turn, with ordinary official documentation research only.
- artifact locations: `product/docs/OPENROUTER_FEATURE_DECISIONS.md`, revised product spec/architecture/API/integration/delivery documents, `product/README.md`, `product/HANDOFF.md`, `docs/decisions/0002-opinionated-inference-product.md`, and this packet.
- resume command: `python3 tools/devex/start.py && sed -n '1,360p' product/docs/OPENROUTER_FEATURE_DECISIONS.md && sed -n '1,320p' product/docs/DELIVERY_PLAN.md`.
- rollback or cleanup: revert only owned documentation and packet changes; preserve all unrelated `research/**` work and the committed billing/infrastructure decisions.

## Plan

1. Capture the current official OpenRouter feature surface and source identities.
2. Apply the keep/simplify/defer/reject framework and define the opinionated user journey.
3. Revise product/API/data/gateway/UX/integration architecture and work packages.
4. Verify links/consistency, update handoff, release the packet, and report the decision.

## Result

- status: complete
- product decision: five managed products plus a qualified concrete catalog; five-screen/default-workspace-hidden UI; fixed-price immutable route releases; strict capability/privacy behavior; qualified owned inference preference; direct gateway first; OpenRouter downstream for differentiated supply and upstream only as an operator option.
- feature inventory: 107 grouped OpenRouter capability rows classified from current official public docs, with source table, uncertainties and falsifiers.
- architecture: added ModelOps qualification/release domain, RouteRelease data and Redis projections, deterministic canary/session/rollback, concrete-pin fidelity, fixed customer sell pricing, internal retry-cost isolation, strict privacy/capability filtering, failed-request credits, and provider-channel isolation.
- verification: `git diff --check`; `python3 tools/devex/check.py`; local Markdown link resolution across all 22 product/docs Markdown files; all passed. No code or paid provider tests were applicable.
- changed paths: `docs/ARCHITECTURE.md`, `docs/decisions/0002-opinionated-inference-product.md`, `product/AGENTS.md`, `product/HANDOFF.md`, `product/README.md`, `product/docs/API_AND_DATA_CONTRACTS.md`, `product/docs/ARCHITECTURE.md`, `product/docs/BILLING_AND_REDIS.md`, `product/docs/DELIVERY_PLAN.md`, `product/docs/EVIDENCE_AND_DECISIONS.md`, `product/docs/INTEGRATIONS.md`, `product/docs/OPENROUTER_FEATURE_DECISIONS.md`, `product/docs/OPENROUTER_SPIKE.md`, `product/docs/PRODUCT_SPEC.md`, `product/docs/SECURITY_BILLING_OPERATIONS.md`, `product/docs/TESTING_AND_CI.md`, and this packet.
- limitations: authenticated OpenRouter UI behavior and private commercial terms were not inferred; no model/economics benchmark or provider request was run; managed-product names and qualification thresholds remain falsifiable launch hypotheses.
- commit: not requested; changes remain uncommitted and unrelated `research/**` work was preserved.
- next action: delegate WP-00 contract/test substrate, then WP-01/WP-02/WP-04 in parallel; split WP-06 only after the route/qualification Protobuf and Redis contracts are frozen.
