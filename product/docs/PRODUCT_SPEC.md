# Grad product specification

## Promise

Grad should feel like the curated, reliable inference option: one key, a small understandable catalog, explicit behavior and smooth migration from provider SDKs and existing gateways. It makes revenue immediately as a prepaid gateway, then uses observed workloads and owned research to move suitable traffic to better Grad releases.

## Seed users

- A developer who wants one OpenAI-compatible endpoint and clear prepaid spend control.
- A small team that needs workspaces, keys, usage/traces and reliable direct-provider access.
- A platform team already using LiteLLM, Cloudflare AI Gateway, Portkey, Helicone or similar and willing to add Grad as a provider/base URL.
- An OpenRouter user who wants a listed Grad-owned model without adopting the Grad gateway directly.

## Organization model

Signup creates an organization, owner membership and Default workspace atomically. Billing/top-ups/credit live only at organization level. Workspaces isolate API keys, members, data policy, allowed models, monthly limit and concurrency. Workspace keys cannot spend beyond organization credit or their workspace/key limits.

Organization deletion is self-service for owners with recent reauthentication and explicit confirmation. It immediately stops new spend, then drains usage, refunds refundable unused credit, destroys trace keys/objects, revokes access and pseudonymizes legally required financial evidence. A fixed seven-day cancellation window is shown in the UI; deletion status is visible without support intervention.

Seed roles are `owner`, `admin`, `member`, `billing` at organization level and `admin`, `developer`, `viewer` at workspace level. Add finer grants only with a customer workflow that cannot be expressed by these roles.

## Onboarding journey

1. Sign up; land in Default workspace.
2. Add a USD credit top-up through Stripe.
3. Create/copy a workspace key once.
4. Copy an OpenAI SDK snippet with Grad base URL.
5. Send the first request to one curated direct model.
6. See status, tokens, cost and retained encrypted trace.
7. Optionally set monthly/concurrency limits or no-retention.
8. Try a published `grad/<effort>/<speed>` model when eligible.

Target time to first successful request is under five minutes for a funded account. The UI never exposes internal releases, endpoints, provider routing weights or infrastructure concepts in the default path.

## Catalog

Keep a small set of high-demand, qualified providers and models. Seed providers are selected from OpenAI, Anthropic and Google based on customer demand and commercial/API readiness; one provider/model is sufficient for the first paid vertical. Each direct ID identifies one provider and upstream model exactly.

Owned Grad IDs express customer intent:

- effort: `low`, `medium`, `high`, `max` (publish only validated values);
- speed: `flex`, `standard`, `fast`, `turbo` (publish only validated values).

The stable alias resolves to immutable qualified releases. Start with `grad/medium/standard`; do not publish a full matrix merely because the grammar permits it. Optional release pins are an advanced API feature after a real reproducibility customer asks for them.

## API behavior

Public surface:

- `GET /v1/models`;
- OpenAI Responses Create and Anthropic Messages from launch;
- streaming and non-streaming;
- explicit request IDs, rate/admission headers and normalized errors;
- idempotency only on management/payment operations where meaningful.

Compatibility means requests work through official clients and common gateway provider integrations. Unsupported model features return clear errors before spend. Grad does not silently switch a direct model/provider, change effort/speed, truncate to fit, drop parameters or retain content against policy.

The management surface is a documented Hono REST API under `/api/v1`, not tRPC. Described Zod schemas generate OpenAPI 3.1, interactive Scalar docs, agent-readable Markdown, the Vite TypeScript client and an allowlisted OAuth MCP server. Every public field and operation must include an agent-usable description. Destructive/sensitive operations such as organization deletion, checkout, key-secret creation and trace plaintext are not MCP tools at launch.

## Billing and limits

- USD prepaid credit at organization level.
- Fixed-chart immutable double-entry ledger.
- Verified Stripe webhooks are the only top-up authority.
- Worst-case reservation before provider spend; exact settlement/refund afterward.
- Optional monthly workspace and key limits.
- Workspace/key concurrency plus stricter atomic low-balance concurrency.
- Clear insufficient-credit, limit and concurrency errors.
- Usage export and transaction history.

No subscriptions, postpaid credit, coupons, multiple currencies, arbitrary daily/weekly/lifetime periods or workspace wallets at seed. These are product expansions, not generic fields.

## Console

Use Vite, React, TanStack Router/Query, the generated REST client, Tailwind and shadcn/ui. Primary pages:

- Home/quickstart: balance, first-request snippet and recent failures.
- Models: curated direct/Grad cards with capabilities and price.
- Workspaces: members, keys, allowed models, monthly/concurrency and data mode.
- Usage/traces: bounded filters, token/cost/latency charts, request list and authorized encrypted detail.
- Billing: balance, top-up, ledger transactions and usage export.
- Recommendations: evidence and explicit replay/canary actions, never automatic switching.
- Research/operator pages: internal program/run/evidence/bundle/qualification/release views.
- Organization deletion: owner-only danger zone with reauthentication, balance/refund impact, cancellation deadline and deletion progress.

Use progressive disclosure: most users see base URL, key, model, balance and results. Advanced release/channel/fleet/research data is role-gated.

## Data policy

Product Intelligence is default and stores encrypted request/response trace payloads for the selected retention period. It powers trace debugging, workload summaries and migration recommendations. Retention is not model-training consent; training/use consent is a separate future agreement.

No-retention can be set at workspace or tightened per request. It prevents payload emission to the trace stream/S3. Financial/usage metadata remains. KV/prefix cache remains enabled and ephemeral, isolated by opaque tenant/channel/release/retention-class scope.

Deletion revokes access and destroys key material first, then removes objects. Exports and trace detail are authorized/audited. PostgreSQL supplies seed analytics; ClickHouse is not a hidden launch dependency.

## Reliability contract

- Fail closed when credit reservation state is unavailable or uncertain.
- Preserve exact direct-model identity.
- Retry only under published pre-output/idempotent rules.
- Never double charge duplicate/reordered attempts/events.
- Existing serving continues from versioned Valkey snapshots during control-plane outage.
- Provider/cell health removes unhealthy endpoints without changing the requested product.
- Multi-node cells are one exact-release routing unit; loss of any required rank fences the cell and follows the same pre/post-output settlement rules.
- Customer-visible errors identify authentication, credit, limit, capability, provider and internal failure classes consistently.

Initial SLOs are hypotheses to validate: multi-AZ gateway, p95 admission overhead, stream first-token overhead, billing posting lag, trace availability and supportable error rate. The delivery gate records measured values before promises are published.

## Distribution

Adoption paths, in order:

1. Direct Grad base URL/API key.
2. Generic OpenAI-compatible setup recipes for existing gateways/harnesses.
3. Native OpenRouter listing of selected Grad-owned releases.
4. Additional native router listings only when customer reach justifies the integration.

OpenRouter calls the public Grad gateway with a channel credential. The gateway performs channel authentication, limits, exact release selection, usage and trace policy, then calls owned inference. It does not use customer prepaid credit; channel receivables/payables use the same fixed ledger chart with isolated accounts and reconciliation.

## Success and kill criteria

Track activation (funded first request), retained weekly usage, gross margin, request success, billing drift, trace use, recommendation-to-trial conversion and owned-Grad share. Avoid vanity catalog/provider counts.

Pause expansion if the first paid direct slice cannot prove correct reservation/settlement, supportable reliability or positive contribution margin. Pause owned rollout if qualification cannot reproduce quality/runtime/cache/failure behavior. Pause a channel if usage statements cannot reconcile exactly or its economics/support burden fail the recorded gate.
