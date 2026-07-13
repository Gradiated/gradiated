# Product specification

## Product thesis

The seed is a prepaid inference gateway that makes our inference endpoint easy to buy and easy to adopt. Customers receive one familiar base URL, fund an organization, create workspace API keys, call models through OpenAI or Anthropic clients, and inspect usage. The same serving endpoint can later be listed behind OpenRouter and other gateways, creating distribution without duplicating serving or metering.

The direct gateway is successful when teams activate quickly, retain paid usage, and produce positive contribution margin. The provider-distribution path is successful when externally sourced traffic is incremental, quality-competitive, and reconcilable to the same usage/ledger system.

## Seed customer

Initial customers are developers and small AI teams that want one of:

- access to our differentiated inference or models through familiar SDKs;
- one prepaid account across selected upstream providers;
- simple routing/fallback without operating gateway infrastructure;
- organization billing plus workspace-level keys, budgets, model controls, usage visibility, and receipts.

Large-enterprise SSO, private networking, deeper hierarchy, and invoiced credit are later capabilities. The seed hierarchy stops at organization -> workspace -> key.

## Core user journey

1. A user signs in and creates an organization; the transaction also creates its Default workspace and owner memberships.
2. The owner tops up a small organization credit amount through Stripe Checkout.
3. The owner creates an API key in the Default workspace and sees the raw secret once.
4. A verified webhook posts the credit and the UI shows it after Redis projection.
5. The quickstart supplies OpenAI and Anthropic client snippets with our base URL.
6. The customer makes a streamed or non-streamed request.
7. The gateway reserves estimated maximum cost, dispatches, meters actual usage, settles, and returns the response.
8. The dashboard shows request status, model, units, latency, sell amount, and remaining credit without exposing sensitive payloads.
9. The organization can add members and top up again; admins can create workspaces with independent keys, members, budgets, routes, model/provider policy, and concurrency limits.

## Seed scope

### Dashboard and control plane

- Vite React TypeScript SPA with Tailwind and shadcn/ui only for base components.
- Hono Node API with Better Auth sessions and tRPC for first-party application calls.
- Product-owned `users`, `organizations`, `organization_memberships`, `workspaces`, and `workspace_memberships`; Better Auth owns identity/session records, not tenant policy.
- Organization roles: owner, admin, billing, member. Workspace roles: admin, developer, viewer.
- Organization creation/switching, automatic Default workspace, workspace creation/switching, invitations, membership lifecycle, and audit trail.
- API-key creation, display-once secret, prefix, scopes, expiry, revoke, and last-used metadata.
- Organization credit balance, top-up history, receipts, low-credit warning, and optional automatic top-up after manual top-up is stable.
- Workspace daily/weekly/monthly/lifetime budgets, normal/low-credit concurrency, maximum request reserve/output, and model/provider allowlists. API-key limits use the same interval model.
- Usage/request list, request detail without raw payload by default, model catalog, route policy, and workspace settings.
- Versioned public REST/OpenAPI management API only when an external customer use case exists; first-party screens use tRPC.

### Rust gateway

- `GET /v1/models`.
- `POST /v1/chat/completions`, including SSE streaming.
- `POST /v1/messages`, including Anthropic event-stream semantics.
- Bearer-key authentication, workspace policy, request IDs, model aliases, routing, bounded fallback, and normalized errors.
- OpenAI, Anthropic, OpenRouter, and a generic compatible upstream adapter; owned inference uses the same target interface.
- Atomic organization prepaid admission, nested organization/workspace/key budget and concurrency control, reservation leases, actual settlement, and idempotent billing events in Redis.
- No internal dependency other than Redis; outbound HTTPS to selected inference providers is expected.

### Billing

- Manual prepaid Stripe top-ups in fixed safe denominations plus a constrained custom amount.
- PostgreSQL organization-level double-entry ledger in integer micro-USD; workspace/key usage is attribution and limit state, not a separate funded wallet.
- Verified webhook idempotency, refunds/chargebacks as compensating entries, and a transactional outbox.
- Redis projection and Redis Streams usage transport.
- Continuous and scheduled reconciliation with automatic fail-closed organization states on unexplained financial deltas and workspace/key closure on policy-specific faults.

### Developer experience

- OpenAI and Anthropic quickstarts; copyable environment and base-URL configuration.
- Deterministic fake providers for every pull request.
- Protected real-provider smoke tests using official clients and minimal token limits.
- One-command deterministic tests plus replayable PBT for TypeScript and Rust.

## Explicit non-goals for seed

- Becoming a broad model marketplace before our differentiated supply is validated.
- A hierarchy deeper than organization/workspace or independently funded workspace wallets.
- Postpaid credit without underwriting.
- Silent protocol emulation for fields we cannot preserve.
- Cross-region active-active balance mutation in the first release.
- Retaining prompts or responses by default.
- Depending on a customer to run local verification.

## Functional requirements

| ID | Requirement | Acceptance signal |
| --- | --- | --- |
| FR-01 | Tenant isolation | Every tenant record carries organization ID and every inference/config record also carries workspace ID; generated cross-organization/workspace tests fail closed. |
| FR-02 | Safe top-up | Redirects cannot credit an account; duplicate/reordered Stripe events have one financial effect. |
| FR-03 | Prepaid admission | No dispatch occurs without one atomic organization-credit and nested workspace/key-limit reservation plus billing event. |
| FR-04 | Depletion protection | Low-credit organizations have a strict organization-wide in-flight cap, with workspace/key caps layered below; zero credit returns a stable 402. |
| FR-05 | Reconciliation | Every settled gateway event is posted once to PostgreSQL; unexplained divergence transitions the organization to `reconciling` or `suspended`. |
| FR-06 | Client compatibility | Official OpenAI and Anthropic clients pass fake-provider conformance on every PR and minimal real smoke tests in protected CI. |
| FR-07 | Streaming | Chunk order, terminal markers, cancellation, usage, errors, and timeouts match the selected ingress protocol. |
| FR-08 | Contract safety | Protobuf generation is deterministic; lint, breaking-change, drift, and TS/Rust golden roundtrips pass. |
| FR-09 | Testability | Stateful money/auth paths have model-based PBT, deterministic seed replay, shrinking, and CI artifacts. |
| FR-10 | Operability | Operators can freeze an organization/workspace, revoke a key, replay/repair a billing event, rebuild a Redis projection, and audit each action. |

## UX information architecture

The application shell has organization and workspace switchers, API status, docs, and user menu. Organization navigation contains Overview, Credits & billing, Members, Workspaces, Activity, and Settings. Selected workspace navigation contains:

- Overview: organization balance summary, workspace budget usage, quickstart, recent requests, spend, and status.
- API keys: create, copy once, scope, expire, revoke, rotate.
- Models and routes: visible models, aliases, target order, fallback policy.
- Usage: request table, filters, metered units, cost, latency, and safe diagnostics.
- Limits: interval budgets, key limits, max reserve/output, concurrency, and effective model/provider policy.
- Members: workspace assignment and role; organization invitations/roles live at organization level.
- Settings: workspace details, routing/privacy policy, deletion/export; the Default workspace cannot be deleted in seed.

Use optimistic UI only for reversible non-financial changes. Balance, top-up, key creation, and status use server-confirmed state. Accessibility, keyboard flow, narrow-screen behavior, loading/empty/error states, and destructive confirmation are part of acceptance.

## Commercial defaults

- Organization-level prepaid only; no request is knowingly financed by us and workspace budgets do not transfer funds.
- Publish sell prices per model and immutable price-book version.
- Reserve using declared input, maximum output, model price, and a safety buffer; settle measured actual usage.
- Gross margin and provider buy cost are internal; customer-visible charges are independently reproducible.
- Manual top-up first. Automatic top-up is gated behind successful webhook/reconciliation operations and explicit customer limits.

## Success metrics and gates

North-star metrics are time to first successful request, funded organizations, activated workspaces, seven- and thirty-day paid retention, gross inference revenue, contribution margin, request success rate, and reconciliation delta.

Seed launch gates:

- p95 gateway overhead below 25 ms excluding provider time on representative regional load;
- zero unreserved upstream dispatches in fault-injection tests;
- zero double-posted charges across duplicate/reordered event properties;
- balance/reconciliation delta exactly zero in deterministic tests and within defined operational tolerance before automatic repair in staging;
- official-client smoke-test budget below $0.05 per protected run;
- activation funnel records organization/default-workspace creation, funding, key creation, first request, extra-workspace adoption, and second-day return.

## Decision checkpoints

- After 10 funded design partners: continue gateway breadth only if integration/support burden and margin are acceptable.
- After OpenRouter compatibility spike: apply as a provider only if protocol fidelity, uptime, economics, and supply differentiation meet their current requirements.
- After 30 days of paid traffic: prioritize owned-model distribution, routing features, or enterprise controls based on measured retained gross profit—not request count alone.
