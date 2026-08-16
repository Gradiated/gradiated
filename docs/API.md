# Product API

- status: initial implementation contract
- date: 2026-08-16
- data model: [DATA_MODEL.md](DATA_MODEL.md)
- architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

This document defines the browser-facing control-plane API. It does not define
the Rust inference API, whose OpenAI-compatible contract is owned by the
`gateway` described in [ARCHITECTURE.md](ARCHITECTURE.md).

The contract is intentionally resource-oriented and small. Routes are added
only when a launch workflow needs them. The TypeScript implementation is the
executable authority: every Gradiated-owned route is declared with Zod schemas
and `@hono/zod-openapi` metadata before its handler is implemented.

## Protocol conventions

- Gradiated-owned routes use the `/api/v1` prefix. Better Auth owns
  `/api/auth/*`.
- Request and response bodies use JSON. Timestamps are UTC RFC 3339 strings.
- UUIDs are lowercase canonical strings. Public model IDs are bounded exact
  strings such as `moonshotai/kimi-k3`.
- Integer nano-USD values cross the JSON boundary as base-10 strings because
  JavaScript numbers cannot safely represent every PostgreSQL `bigint`.
- Optional stored values are returned as explicit `null`; omitted fields mean
  the field is not part of that response shape.
- Single-resource responses return the resource directly. Collection responses
  use `{ "data": [...], "next_cursor": string | null }`.
- Collection limits default to 50 and are bounded to 1–100. Cursors are opaque,
  stable only for the documented traversal and never parsed by clients.
- Errors use `application/problem+json` with stable `type` and `code` values,
  an HTTP `status`, a human-readable `title` and `detail`, and a `request_id`.
  Validation problems may also contain bounded field errors.
- Unknown request fields are rejected. Unknown response fields must be ignored
  by clients to permit additive API evolution.
- Cookie-authenticated unsafe requests require Better Auth's origin and CSRF
  protections. API keys are never accepted by this product API.
- Every response carries `X-Request-Id`. Secret-bearing responses additionally
  carry `Cache-Control: no-store`.

The generated application schema is served at `/api/openapi.json`. Once Better
Auth is enabled, its plugin serves its generated schema under
`/api/auth/open-api/` and its reference under `/api/auth/reference`; `/docs`
then presents both sources in one Scalar UI. Generated files are build
artifacts: CI regenerates the OpenAPI documents, browser client and Rust
fixtures and rejects drift.

## Authorization

Every `/api/v1` route except health checks requires a valid human session. The
server derives the user from the session and never accepts an actor ID in a
request body.

Organization IDs remain explicit in URLs. There is no server-side active-
organization state. Access requires an active organization membership, and
distribution-channel organizations are omitted from ordinary customer lists.

| Capability | owner | admin | billing | member |
| --- | --- | --- | --- | --- |
| Read organization, workspaces, models and usage | yes | yes | yes | yes |
| Update organization | yes | yes | no | no |
| Manage invitations and non-owner members | yes | yes | no | no |
| Change an owner's role or remove an owner | yes | no | no | no |
| Create, rename or archive workspaces | yes | yes | no | no |
| Create or revoke API keys | yes | yes | no | no |
| View billing and create top-ups | yes | yes | yes | no |

The last active owner cannot be demoted, suspended or removed. A user cannot
raise their own privileges. Authorization checks and tenant predicates are
performed in the same repository operation; handlers do not load an
unscoped resource and check it afterward.

## Route inventory

### System and session context

| Method | Path | Operation ID | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health/live` | `getLiveness` | Process liveness; no dependency checks |
| `GET` | `/health/ready` | `getReadiness` | Readiness of dependencies required to serve product traffic |
| `GET` | `/api/v1/me` | `getCurrentUser` | Current user and their visible organization summaries |

Better Auth owns sign-up, sign-in, sign-out, email verification, password reset
and session endpoints. Signup creates authentication state only. The
post-registration product flow calls `createOrganization`, which creates one
customer organization, owner membership, default workspace and prepaid billing
account in one PostgreSQL transaction. `getCurrentUser` may therefore return no
organizations until onboarding completes. This boundary is explicit because a
Better Auth after-create hook does not provide our Drizzle domain writes with a
documented shared transaction.

### Organizations and members

| Method | Path | Operation ID | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/v1/organizations` | `listOrganizations` | List the caller's customer organizations |
| `POST` | `/api/v1/organizations` | `createOrganization` | Create an organization with default workspace and billing account |
| `GET` | `/api/v1/organizations/{organization_id}` | `getOrganization` | Get one organization |
| `PATCH` | `/api/v1/organizations/{organization_id}` | `updateOrganization` | Rename an organization |
| `GET` | `/api/v1/organizations/{organization_id}/members` | `listOrganizationMembers` | List members |
| `PATCH` | `/api/v1/organizations/{organization_id}/members/{user_id}` | `updateOrganizationMember` | Change role or active/suspended status |
| `DELETE` | `/api/v1/organizations/{organization_id}/members/{user_id}` | `removeOrganizationMember` | Remove a member |
| `GET` | `/api/v1/organizations/{organization_id}/invitations` | `listInvitations` | List current and recent invitations |
| `POST` | `/api/v1/organizations/{organization_id}/invitations` | `createInvitation` | Create or resend a bounded-lifetime invitation |
| `DELETE` | `/api/v1/organizations/{organization_id}/invitations/{invitation_id}` | `revokeInvitation` | Revoke a pending invitation |
| `POST` | `/api/v1/invitations/accept` | `acceptInvitation` | Accept a raw invitation token for the current user |

Raw invitation tokens are accepted in a request body rather than a URL so they
do not enter routine path logs. Creating an invitation returns the resource but
not its raw token; delivery belongs to the application mail integration.

### Workspaces and API keys

| Method | Path | Operation ID | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/v1/organizations/{organization_id}/workspaces` | `listWorkspaces` | List workspaces, including archived ones when requested |
| `POST` | `/api/v1/organizations/{organization_id}/workspaces` | `createWorkspace` | Create a workspace |
| `GET` | `/api/v1/organizations/{organization_id}/workspaces/{workspace_id}` | `getWorkspace` | Get one workspace |
| `PATCH` | `/api/v1/organizations/{organization_id}/workspaces/{workspace_id}` | `updateWorkspace` | Rename a workspace |
| `POST` | `/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/archive` | `archiveWorkspace` | Irreversibly archive a non-default workspace |
| `GET` | `/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/api-keys` | `listApiKeys` | List key metadata |
| `POST` | `/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/api-keys` | `createApiKey` | Create a key and return its raw value once |
| `DELETE` | `/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/api-keys/{api_key_id}` | `revokeApiKey` | Irreversibly revoke a key |

`createApiKey` returns `{ "api_key": <metadata>, "secret": "grad_..." }` and
is the only product response containing raw API-key material. Listing and
revocation never expose a prefix, suffix or digest. Creating a key succeeds only
after PostgreSQL commits and Valkey acknowledges the new credential snapshot.
Revocation first blocks the credential in Valkey and leaves it blocked on any
partial failure.

### Models

| Method | Path | Operation ID | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/v1/models` | `listModels` | List active and currently advertised models |
| `GET` | `/api/v1/models/{model_id}` | `getModel` | Get one advertised exact model |

These routes expose customer-facing PostgreSQL catalog state, not deployment
manifests or private runtime capacity. Model IDs may contain `/`; the route
implementation must use a wildcard or encoded path capture that preserves the
exact decoded ID. Initial model mutation is an authenticated operator command
inside the API codebase, not a public HTTP surface. Add an administrative route
only after its operator-authentication boundary is defined.

### Billing and usage

| Method | Path | Operation ID | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/v1/organizations/{organization_id}/billing` | `getBillingAccount` | Get billing mode and durable posted balance |
| `GET` | `/api/v1/organizations/{organization_id}/balance-transactions` | `listBalanceTransactions` | List durable balance movements |
| `POST` | `/api/v1/organizations/{organization_id}/billing/checkout-sessions` | `createCheckoutSession` | Create a server-priced Stripe top-up Checkout Session |
| `GET` | `/api/v1/organizations/{organization_id}/usage/summary` | `getUsageSummary` | Aggregate ClickHouse usage and charge over a bounded interval |
| `GET` | `/api/v1/organizations/{organization_id}/generations` | `listGenerations` | Cursor-page immutable terminal generations |
| `GET` | `/api/v1/organizations/{organization_id}/generations/{generation_id}` | `getGeneration` | Get one terminal generation |
| `POST` | `/api/stripe/webhooks` | `handleStripeWebhook` | Verify and apply supported Stripe events |

Usage endpoints may lag inference by the Valkey-to-ClickHouse ingestion delay.
The billing response is the durable posted balance and may lag the operational
Valkey balance by one settlement interval; it includes `settled_through` so the
UI can say so precisely. Neither endpoint is used for inference admission.

Generation responses expose the closed properties documented in
[DATA_MODEL.md](DATA_MODEL.md), excluding internal-only runtime details that are
not needed by the customer. They never contain prompts, completions, arbitrary
request bodies, credentials or private service URLs.

Checkout amounts are selected from a small server-side allowlist. The browser
does not submit a price or arbitrary nano-USD amount. The webhook is outside
`/api/v1` because Stripe, not a human session, authenticates it with a signature.

## Mutation semantics

- PostgreSQL transactions own product invariants. There is no generic
  idempotency-record table.
- Serving-sensitive mutations follow the PostgreSQL/Valkey ordering and
  fail-closed rules in [DATA_MODEL.md](DATA_MODEL.md). A returned `503` may mean
  PostgreSQL committed but projection has not converged; retrying the same
  desired-state mutation is safe.
- Create operations that cannot naturally replay, notably API-key creation, do
  not promise idempotency. The UI disables duplicate submission and presents
  each successfully returned secret once.
- `PATCH` bodies contain at least one field and change only named fields. Full
  replacement with `PUT` is not exposed.
- Deletes in this API mean the domain operation named by the model: membership
  removal, invitation revocation or API-key revocation. Organization deletion
  and physical record deletion are not launch features.

## Initial implementation order

1. Protocol schemas, health routes, generated OpenAPI and documentation.
2. Better Auth plus current-user and atomic organization bootstrap.
3. Organization, membership and invitation repositories and routes.
4. Workspaces and one-time API keys with synchronous Valkey projection.
5. Read-only model catalog and operator seed command.
6. Billing views, Stripe top-ups and immutable balance transactions.
7. ClickHouse generation and usage views.

The worker and Rust gateway consume schemas from the same product package where
the boundary is shared, but neither imports API handler or repository code.
