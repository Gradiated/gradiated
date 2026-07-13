# Product specification

## Product thesis

The seed is a premium, opinionated inference product—not a model marketplace. Customers receive one familiar base URL and workspace key with two model lanes: a curated set of provider-qualified OpenAI, Anthropic and Google models for easy workload migration, and first-party `grad/<effort>/<speed>` products served on our inference. Every lane has explicit identity, prepaid pricing and request-level transparency; no arbitrary provider catalog or routing array is exposed.

The experience target is a successful production-shaped request within five minutes. An existing workload changes its base URL/key and can keep an unambiguous upstream model ID or use the canonical `provider/model` ID. A new workload starts with `grad/medium/standard`. Usage reads a content-free ClickHouse analytical projection, opens authorized encrypted payload detail from S3, groups Product Intelligence traces into workloads, and suggests evidence-backed Grad effort/speed candidates; the customer controls every replay, canary and final switch.

The same serving endpoint can later be listed behind OpenRouter and other gateways, creating distribution without duplicating serving or metering. OpenRouter is a distribution partner and operator-only contingency—not the product template or a customer-selectable direct provider. The detailed model and migration contract is in [Model lanes and migration](MODEL_LANES_AND_MIGRATION.md); OpenRouter decisions remain in [OpenRouter feature decisions](OPENROUTER_FEATURE_DECISIONS.md).

The direct gateway is successful when teams activate quickly, retain paid usage, and produce positive contribution margin. The provider-distribution path is successful when externally sourced traffic is incremental, quality-competitive, and reconcilable to the same usage/ledger system.

## Seed customer

Initial customers are developers and small AI teams that want one of:

- move an existing OpenAI, Anthropic or Google workload by changing only credentials/base URL where model identity is unambiguous;
- explicitly pin a curated provider/model without hidden cross-provider fallback;
- use our differentiated inference through a simple effort × speed product grammar;
- see which workloads are strong candidates for a cheaper/faster Grad product and verify that migration safely;
- organization billing plus optional workspace isolation, hard budgets, usage visibility, and receipts.

Large-enterprise SSO, private networking, deeper hierarchy, and invoiced credit are later capabilities. The seed hierarchy stops at organization -> workspace -> key.

## Core user journey

1. A user signs in and creates an organization; the transaction also creates its Default workspace and owner memberships.
2. The owner tops up a small organization credit amount through Stripe Checkout.
3. The owner creates an API key and sees the raw secret once; the Default workspace is implicit.
4. A verified webhook posts the credit and the UI shows it after Redis projection.
5. The quickstart offers “Bring an existing model” and “Start with Grad.” The first accepts an unambiguous bare upstream ID or canonical `openai/...`, `anthropic/...`, or `google/...`; the second uses `grad/medium/standard`.
6. The customer makes a streamed or non-streamed request without selecting endpoints or fallback arrays.
7. A direct request remains pinned to that provider/model. A Grad request resolves an immutable owned-inference effort/speed RouteRelease. Both reserve fixed sell exposure, dispatch, meter and settle.
8. Product Intelligence mode retains a bounded encrypted trace by default. Usage shows the trace, actual provider/release, units, latency, price, cache behavior and remaining credit.
9. Once sufficient evidence exists, Usage suggests a Grad effort/speed candidate and offers customer-approved replay, shadow and canary steps—never an automatic switch.
10. Only when needed, the organization adds members/workspaces, Private/No Retention, budgets or advanced controls.

## Seed scope

### Dashboard and control plane

- Vite React TypeScript SPA with Tailwind and shadcn/ui only for base components.
- Hono Node API with Better Auth sessions and tRPC for first-party application calls.
- Product-owned `users`, `organizations`, `organization_memberships`, `workspaces`, and `workspace_memberships`; Better Auth owns identity/session records, not tenant policy.
- Organization roles: owner, admin, billing, member. Workspace roles: admin, developer, viewer.
- Organization creation/switching, automatic Default workspace, workspace creation/switching, invitations, membership lifecycle, and audit trail.
- API-key creation, display-once secret, prefix, scopes, expiry, revoke, and last-used metadata.
- Organization credit balance, top-up history, receipts, low-credit warning, and optional automatic top-up after manual top-up is stable.
- Five-screen default navigation: Overview, API keys, Models, Usage, Billing. Workspace/team/data retention/limits live under progressive Settings and appear only when configured.
- Workspace monthly budget and concurrency in the simple UI; daily/weekly/lifetime windows, key caps, maximum reserve/output and model/data policy in advanced settings.
- Product Intelligence trace/workload list and charts from ClickHouse plus separately authorized encrypted S3 detail: request/response/tool trace, provider/model or Grad effort/speed release, attempts, units, cost, cache, timing, retention deadline and safe error guidance.
- Models UI with a first-party Grad effort × speed selector and a second curated Direct Providers tab containing only qualified OpenAI, Anthropic and Google models. No hundreds-model marketplace/provider-endpoint UI.
- Workload profiles, migration candidates/recommendations, replay/shadow/live-canary experiments, evidence/confidence, customer evaluators, budgets and stop conditions.
- Data settings with Product Intelligence default, bounded retention/export/delete, and Private/No Retention workspace/request controls.
- Versioned public REST/OpenAPI management API only when an external customer use case exists; first-party screens use tRPC.

### Rust gateway

- `GET /v1/models`.
- `POST /v1/chat/completions`, including SSE streaming.
- `POST /v1/messages`, including Anthropic event-stream semantics.
- `POST /v1/responses`, a stateless OpenAI-compatible supported subset with streaming, tools, structured output, reasoning and image input.
- `POST /v1/embeddings`, including batches and qualified text/image embedding models.
- Google-native compatible generate/stream-generate endpoints under a versioned `/google/*` skin, pinned by official `@google/genai` conformance before implementation.
- Tool calling, structured outputs, reasoning controls, common sampling parameters, image input and native-capability file input. Unsupported semantics fail explicitly.
- Bearer-key authentication, workspace policy, request IDs, provider-qualified model IDs, bare-ID compatibility aliases, Grad effort/speed products, concrete pinning, session stickiness, immutable releases, bounded same-provider/same-product fallback, prompt-cache awareness, trace capture and normalized typed errors.
- Curated OpenAI, Anthropic and Google direct adapters plus owned inference. OpenRouter/generic compatibility is operator-only or downstream-distribution infrastructure, not customer provider selection.
- Atomic organization prepaid admission, nested organization/workspace/key budget and concurrency control, reservation leases, actual settlement, and idempotent billing events in Redis.
- No internal dependency other than Redis; outbound HTTPS to selected inference providers is expected.
- Bounded trace ciphertext is emitted to a separate Redis Stream and asynchronously persisted to private object storage; trace failure cannot weaken or block financial admission/settlement.
- Authoritative settled usage/trace registry state is projected asynchronously to content-free ClickHouse request/attempt/evaluation facts and rollups; analytics failure delays the UI but cannot affect serving, ledger posting or S3 payload persistence.

### Billing

- Manual prepaid Stripe top-ups in fixed safe denominations plus a constrained custom amount.
- PostgreSQL organization-level double-entry ledger in integer micro-USD; workspace/key usage is attribution and limit state, not a separate funded wallet.
- Verified webhook idempotency, refunds/chargebacks as compensating entries, and a transactional outbox.
- Redis projection and Redis Streams usage transport.
- Continuous and scheduled reconciliation with automatic fail-closed organization states on unexplained financial deltas and workspace/key closure on policy-specific faults.

### Developer experience

- OpenAI, Anthropic and Google quickstarts; copyable environment and base-URL configuration.
- No custom inference SDK at seed; use official clients and tested integration recipes.
- Deterministic fake providers for every `main` commit and external pull request.
- Protected real-provider smoke tests using official clients and minimal token limits.
- One-command deterministic tests plus replayable PBT for TypeScript and Rust.

## Explicit non-goals for seed

- Becoming a broad model marketplace before our differentiated supply is validated.
- Exposing provider ordering, arbitrary fallback arrays, model-suffix variants, plugin configuration or a routing DSL in the default product.
- Hosting an agent runtime, MCP tool execution, shell/filesystem tools, prompt library or arbitrary system-prompt presets.
- Silently dropping unsupported parameters, truncating context, healing outputs, bypassing moderation refusals or switching a pinned model family.
- Using retained customer traces for global model training without a separate explicit opt-in and contract.
- Automatically shadowing, canarying or switching customer traffic from a provider model to Grad.
- Exposing arbitrary provider URLs, every inference reseller, customer-defined provider fallback arrays or BYOK at seed.
- Free-model routing as a product tier; promotions use bounded organization credit.
- A hierarchy deeper than organization/workspace or independently funded workspace wallets.
- Postpaid credit without underwriting.
- Silent protocol emulation for fields we cannot preserve.
- Cross-region active-active balance mutation in the first release.
- Depending on a customer to run local verification.

## Functional requirements

| ID | Requirement | Acceptance signal |
| --- | --- | --- |
| FR-01 | Tenant isolation | Every tenant record carries organization ID and every inference/config record also carries workspace ID; generated cross-organization/workspace tests fail closed. |
| FR-02 | Safe top-up | Redirects cannot credit an account; duplicate/reordered Stripe events have one financial effect. |
| FR-03 | Prepaid admission | No dispatch occurs without one atomic organization-credit and nested workspace/key-limit reservation plus billing event. |
| FR-04 | Depletion protection | Low-credit organizations have a strict organization-wide in-flight cap, with workspace/key caps layered below; zero credit returns a stable 402. |
| FR-05 | Reconciliation | Every settled gateway event is posted once to PostgreSQL; unexplained divergence transitions the organization to `reconciling` or `suspended`. |
| FR-06 | Client compatibility | Official OpenAI, Anthropic and Google clients pass fake-provider conformance on every PR and minimal real smoke tests in protected CI. |
| FR-07 | Streaming | Chunk order, terminal markers, cancellation, usage, errors, and timeouts match the selected ingress protocol. |
| FR-08 | Contract safety | Protobuf generation is deterministic; lint, breaking-change, drift, and TS/Rust golden roundtrips pass. |
| FR-09 | Testability | Stateful money/auth paths have model-based PBT, deterministic seed replay, shrinking, and CI artifacts. |
| FR-10 | Operability | Operators can freeze an organization/workspace, revoke a key, replay/repair a billing event, rebuild a Redis projection, and audit each action. |
| FR-11 | Model lanes | Canonical direct IDs hard-pin a curated provider/model; every `grad/<effort>/<speed>` identity resolves to an immutable owned-inference release with fixed prices, evidence and rollback. |
| FR-12 | Route fidelity | Direct requests never cross provider/model/version; Grad requests never fall back to external inference or a slower speed/other effort contract. Actual provider/release is disclosed. |
| FR-13 | Explicit capability | Unsupported tools, structured output, reasoning, modality or parameters fail before dispatch; no silent degradation. |
| FR-14 | Failed-request trust | A request with no usable delivered output receives an automatic sell-charge reversal under the documented anti-abuse policy. |
| FR-15 | Trace control | Product Intelligence captures bounded encrypted payload traces by default; Private/No Retention and per-request tightening prevent payload persistence; credentials are never captured. |
| FR-16 | Migration evidence | Recommendations identify source workload, Grad release, evidence level, sample, compatibility, quality/latency/cost result and uncertainty; traffic changes only after customer action. |
| FR-17 | Effort/speed integrity | Published speed and effort cells pass scope-matched monotonicity/SLO gates and never silently downgrade under capacity pressure. |
| FR-18 | Trace analytics isolation | ClickHouse contains only allowlisted content-free facts; Hono queries are organization/workspace/time bounded; PostgreSQL tombstones/key state immediately deny expired/deleted detail; projection outage never affects serving or money. |

## UX information architecture

The application shell has API status, docs and user menu. Organization/workspace switching is absent until the user belongs to more than one; the Default workspace is never setup work. Default navigation is:

- Overview: balance, “bring existing model” and `grad/medium/standard` quickstarts, first-request progress, status, recent workloads and spend.
- API keys: create, copy once, expire, rotate, revoke and optional cap. Workspace is shown only when multiple exist.
- Models: Grad effort × speed selector first; curated Direct Providers tab second. Each identity shows capability, data policy, fixed price and copyable examples without endpoint/weight controls.
- Usage: workload and trace timeline with provider/model or Grad release, payload according to data mode, units, cost, cache, latency, errors and evidence-backed Migration cards.
- Billing: top up, low-credit warning, history and receipts.

Settings contains organization/team/workspaces, monthly budget, Data mode (`Product Intelligence` default or `Private / No Retention`), retention/export/delete, model access, advanced limits and destructive actions. Provider names are explicit model identities in the direct lane, while provider endpoints/weights remain operator machinery.

Use optimistic UI only for reversible non-financial changes. Balance, top-up, key creation, and status use server-confirmed state. Accessibility, keyboard flow, narrow-screen behavior, loading/empty/error states, and destructive confirmation are part of acceptance.

## Commercial defaults

- Organization-level prepaid only; no request is knowingly financed by us and workspace budgets do not transfer funds.
- Publish sell prices per model and immutable price-book version.
- Each direct provider/model and each Grad effort/speed RouteRelease publishes fixed input/output/cache/reasoning/tool SKUs. Speed premiums and effort compute are explicit.
- Reserve the maximum customer sell charge from declared input/output and route-release prices; settle customer-billable delivered usage. Failed-attempt and provider buy-cost variation are our routing/margin problem, never pass-through surprise charges.
- Gross margin, provider buy cost and internal recommendation replay cost are internal; customer-visible charges are independently reproducible. Customer-approved live canaries are billed normally under an explicit cap.
- If no usable output reaches the customer, append an automatic sell-charge reversal; retain provider-cost evidence and fraud limits internally.
- Manual top-up first. Automatic top-up is gated behind successful webhook/reconciliation operations and explicit customer limits.

## Success metrics and gates

North-star metrics are time to first successful direct/Grad request, funded organizations, retained provider workloads, Grad workload share, recommendation-to-experiment and experiment-to-migration conversion, seven- and thirty-day paid retention, gross inference revenue, contribution margin, request success rate, and reconciliation delta.

Seed launch gates:

- p95 gateway overhead below 25 ms excluding provider time on representative regional load;
- zero unreserved upstream dispatches in fault-injection tests;
- zero double-posted charges across duplicate/reordered event properties;
- balance/reconciliation delta exactly zero in deterministic tests and within defined operational tolerance before automatic repair in staging;
- official-client smoke-test budget below $0.05 per protected run;
- activation funnel records organization/default-workspace creation, funding, key creation, first request, extra-workspace adoption, and second-day return;
- median funded time-to-first-request below five minutes and p90 below fifteen minutes;
- direct-provider pins never cross identity; Grad effort/speed releases meet published capability/quality/latency/capacity/margin envelopes and speed lanes do not silently degrade;
- unsupported capabilities are rejected before provider spend and failed requests receive exactly one eligible credit;
- trace capture honors workspace/request data mode, credential exclusion, retention and deletion; ClickHouse projection is content-free/tenant-isolated/rebuildable; trace or analytics backpressure cannot starve billing events;
- recommendation evidence and canary stop conditions pass deterministic/PBT tests, and no workflow can auto-switch customer traffic.

## Decision checkpoints

- After 10 funded design partners: continue gateway breadth only if integration/support burden and margin are acceptable.
- After 10 funded design partners: keep the four effort × four speed grammar only if customers understand it, qualified cells show meaningful monotonic behavior, and direct workloads convert to our inference without unacceptable quality regression.
- After 10 retained provider workloads: continue each direct provider only if it produces positive margin, low support burden and credible Grad migration evidence.
- After OpenRouter compatibility spike: apply as a provider only if protocol fidelity, uptime, economics, and supply differentiation meet their current requirements.
- After 30 days of paid traffic: prioritize owned-model distribution, routing features, or enterprise controls based on measured retained gross profit—not request count alone.
