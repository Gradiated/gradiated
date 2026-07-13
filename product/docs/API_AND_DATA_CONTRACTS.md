# API, data, and contract design

## Public inference APIs

Seed endpoints:

| Method | Path | Protocol authority | Notes |
| --- | --- | --- | --- |
| `GET` | `/v1/models` | OpenAI-shaped schema | Models allowed by the authenticated organization/workspace/key policy. |
| `POST` | `/v1/chat/completions` | OpenAI Chat Completions | Stream and non-stream; unsupported fields fail explicitly. |
| `POST` | `/v1/messages` | Anthropic Messages | Required Anthropic headers plus stream and non-stream. |
| `GET` | `/healthz` | Internal | Liveness only. |
| `GET` | `/readyz` | Internal | Redis/script/config readiness; no provider call. |

Authentication is `Authorization: Bearer <workspace-api-key>`. Anthropic clients may send their standard API-key header; normalize it only at the authentication edge. Reject credentials in query strings. Return `x-request-id`, `x-route-id`, and `x-config-version`; reveal upstream identity only if workspace policy allows it.

OpenAPI/JSON Schema plus recorded conformance fixtures are authoritative for public JSON and streams. Implement an explicit support matrix per field/event. Preserve unknown response metadata only where safe; never silently accept a request feature that will be dropped.

Stable gateway errors have JSON fields `error.type`, `error.code`, `error.message`, `error.param`, and `request_id`, translated to protocol-native envelopes when required. Billing status examples:

- `402 insufficient_credits` with no balance amount disclosure beyond the authenticated organization;
- `429 low_balance_concurrency_limit` with a bounded `Retry-After`;
- `403 organization_suspended`, `organization_reconciling`, or `workspace_suspended`;
- `503 admission_unavailable` when Redis cannot guarantee reservation.

## First-party control API

The Vite application calls tRPC routers under `/trpc`:

- `session`: current user, active organization, and active workspace;
- `organizations`: create, list, update, switch, organization settings;
- `organizationMembers`: list, invite, accept, role, remove;
- `workspaces`: create, list, update, switch, members, limits, delete request;
- `apiKeys`: list, create, revoke, rotate;
- `credits`: organization balance, top-up intent, history, receipt link, warning settings;
- `usage`: aggregate and paginated requests;
- `models` and `routes`: catalog and workspace policy;
- `audit`: paginated administrative events.

Every protected procedure derives the user from the server session and loads organization membership plus workspace membership when workspace scope is required. Never trust a client-provided role. Domain methods receive `{ actorUserId, organizationId, organizationMembershipId, workspaceId?, workspaceMembershipId?, requestId }`.

Stripe webhook routes and any future public management API are Hono REST handlers, not tRPC. REST mutations require an idempotency key and publish OpenAPI definitions.

## Relational model

All IDs are UUIDv7/ULID-style sortable opaque identifiers unless a library decision establishes otherwise. Timestamps are UTC. Money columns are signed 64-bit micro-USD with database constraints.

| Entity | Required shape/invariants |
| --- | --- |
| `users` | Product user keyed to Better Auth identity; status and profile metadata only. |
| `organizations` | customer/billing identity, slug, status, risk/billing mode, credit epoch/version, low-credit concurrency policy. |
| `organization_memberships` | unique organization/user, org role/status; the last owner cannot be removed. |
| `organization_invitations` | organization, email policy, org role, token digest, expiry, inviter; acceptance also creates Default-workspace access. |
| `workspaces` | organization, name/slug, exactly-one Default flag, status, concurrency/output/reserve/privacy/model policy and config version. |
| `workspace_memberships` | unique workspace/user, workspace role/status; user must also have active organization membership. |
| `api_keys` | organization, workspace, optional creator/owner kind, public prefix, keyed digest, scopes, status, expiry, last-used; raw secret never stored. |
| `models` | canonical model ID, capabilities, lifecycle, public metadata. |
| `provider_targets` | provider kind, encrypted secret reference, region, capabilities, status. |
| `workspace_routes` | organization/workspace, exposed model/alias, ordered targets, constraints, config version. |
| `workspace_budgets` | organization/workspace, interval (`daily/weekly/monthly/lifetime`), integer limit; not a wallet. |
| `api_key_budgets` | organization/workspace/key, interval and integer limit. |
| `price_books` | immutable version, effective time, model/unit sell prices and reservation buffer. |
| `topup_intents` | organization, amount, currency, Stripe IDs, idempotency key, state. |
| `payment_events` | unique provider event ID, type, object ID, verification/processing metadata. |
| `ledger_accounts` | organization asset/liability/revenue/clearing account and currency. |
| `ledger_transactions` | unique business/idempotency key, type, effective time, evidence link. |
| `ledger_entries` | transaction, account, signed micro-USD amount; entries sum to zero per currency. |
| `usage_charges` | unique event ID/request/attempt, organization/workspace/key, price version, units, sell, buy evidence. |
| `outbox_events` | aggregate, version, typed Protobuf payload, state/attempt/lease. |
| `audit_events` | actor, organization, optional workspace, action, target, request, safe before/after metadata. |

Tenant indexes begin with `organization_id`; workspace access paths then include `workspace_id`. Constraints/triggers or transactional domain checks guarantee exactly one Default workspace per organization, workspace membership implies organization membership, and a key's organization matches its workspace. Authorization tests generate arbitrary organizations/workspaces/users/memberships and verify no cross-boundary query or mutation.

## Protobuf contract system

`product/proto/` is canonical for internal messages shared by TypeScript and Rust:

```text
proto/
  buf.yaml
  buf.lock
  buf.gen.yaml
  gradiated/gateway/v1/
    auth.proto
    billing.proto
    config.proto
    events.proto
    pricing.proto
```

Important messages include `ApiKeyProjection`, `OrganizationBillingProjection`, `WorkspacePolicyProjection`, `LimitWindow`, `PriceBook`, `RouteConfig`, `Reservation`, `ReservationEvent`, `SettlementEvent`, `ProjectionCommand`, and `ReconciliationCheckpoint`.

Rules:

- Protobuf v3 fields use explicit domain enums and wrapper/optional presence where absence differs from zero.
- Never reuse field numbers or enum values; reserve removed fields/names.
- IDs are strings/bytes by declared convention; money is signed `int64` micro-USD with checked boundary conversion to JS `bigint`.
- Timestamps use `google.protobuf.Timestamp`; durations use `Duration`.
- Events carry `event_id`, `organization_id`, `workspace_id`, `api_key_id`, `request_id`, `billing_epoch`, `sequence`, `schema_version`, `occurred_at`, and idempotency/business keys.
- Protobuf payloads in Redis Streams are binary/base64 or a documented binary-safe field; stream envelope fields remain inspectable.

Generation:

- Buf formats, lints, resolves pinned plugins, and generates Protobuf-ES TypeScript into `packages/contracts/src/gen`.
- Prost generates Rust into `services/gateway/crates/gateway-contracts/src/gen` from the same source; toolchain/plugin versions are pinned.
- Generated directories are committed and never hand-edited.
- `pnpm contracts:generate` runs all generation in a pinned container/toolchain.
- `pnpm contracts:check` runs format, lint, breaking comparison to `main`, generation, `git diff --exit-code` on generated paths, and cross-language golden tests.

Golden fixtures contain Protobuf bytes and canonical JSON descriptions generated from valid domain strategies. TypeScript encodes/Rust decodes and the reverse; unknown-field and additive-field compatibility are tested. Public inference JSON does not use these messages as its wire authority.

## Redis key model

All organization-credit and nested-limit keys use the same organization hash tag:

```text
gw:{<organization_id>}:billing                         hash: epoch, version, status, risk, spendable, org policy
gw:{<organization_id>}:inflight                        integer organization-wide in-flight
gw:{<organization_id>}:workspace:<workspace_id>:policy binary versioned policy/routes/models
gw:{<organization_id>}:workspace:<workspace_id>:limits hash: period spent/reserved + concurrency
gw:{<organization_id>}:key:<key_id>:auth               binary auth projection + workspace binding
gw:{<organization_id>}:key:<key_id>:limits             hash: period spent/reserved + concurrency
gw:{<organization_id>}:prices                          binary immutable price projection
gw:{<organization_id>}:reservation:<id>                hash: workspace/key/request/reserve/lease/state
gw:{<organization_id>}:events                          Redis Stream
gw:reservation-leases                sorted-set/sharded advisory index; entries point to organization-tagged keys
```

If a global lease index prevents one atomic cross-slot operation, it is advisory only: the authoritative lease remains in the organization-tagged reservation. Sweepers read the index then invoke the organization-local atomic transition.

Projection writes carry an expected prior version and new version. Stale/reordered commands no-op. Organization billing epochs fence old gateway and worker events. API-key revocation and organization/workspace suspension use high-priority projection commands and readiness/lag alarms.

## Request and usage identity

- `request_id`: one customer request, stable across bounded target attempts.
- `attempt_id`: one upstream attempt.
- `reservation_id`: one organization-funded reservation attributed to one workspace/key, usually one request.
- `event_id`: unique immutable event; redelivery has the same ID.
- `usage_charge_id`: PostgreSQL posting identity derived from settlement event ID.

Usage records include organization, workspace, API key ID, request/attempt, ingress protocol, canonical/exposed model, target/provider, region, start/first-byte/end times, terminal state, input/output/cache/reasoning/tool units when supported, immutable price version, reserve, sell amount, provider buy-cost evidence, and metering evidence class (`provider_reported`, `locally_measured`, `estimated`).

Corrections append compensating usage/ledger events. They do not mutate the original financial fact.
