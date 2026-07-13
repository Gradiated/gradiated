# API, data, and contract design

## Public inference APIs

Seed endpoints:

| Method | Path | Protocol authority | Notes |
| --- | --- | --- | --- |
| `GET` | `/v1/models` | OpenAI-shaped schema | Models allowed by the authenticated workspace policy, or the approved catalog projection selected by a native-channel credential. |
| `POST` | `/v1/chat/completions` | OpenAI Chat Completions | Stream and non-stream; unsupported fields fail explicitly. |
| `POST` | `/v1/messages` | Anthropic Messages | Required Anthropic headers plus stream and non-stream. |
| `POST` | `/v1/responses` | OpenAI Responses | Stateless supported subset; text/image/file input, tools, structured output, reasoning, stream and non-stream. No server-side conversation storage. |
| `POST` | `/v1/embeddings` | OpenAI Embeddings | Qualified text/image models, scalar or batched input, no streaming. |
| `POST` | `/google/{version}/models/{model}:generateContent` | Google GenerateContent compatibility | Native Google request/response skin; exact supported stable/beta versions frozen by official-client fixtures. Provider is implicitly `google` for bare path models; URL-encoded canonical Grad IDs may be supported only after SDK conformance. |
| `POST` | `/google/{version}/models/{model}:streamGenerateContent` | Google streaming compatibility | Native stream semantics and cancellation; exact query/event framing fixture-governed. |
| `GET` | `/healthz` | Internal | Liveness only. |
| `GET` | `/readyz` | Internal | Redis/script/config readiness; no provider call. |

Authentication is `Authorization: Bearer <workspace-api-key>`. Anthropic clients may send their standard API-key header; normalize it only at the authentication edge. Reject query credentials. Accept optional `x-grad-provider` to disambiguate a bare direct alias, `x-grad-session-id` for stability, `x-grad-data-policy: no-retain` to tighten policy, `x-grad-migration-experiment` to explicitly opt that request into a preconfigured live canary, and bounded `Idempotency-Key`/`x-grad-request-id` for admission/charge deduplication. Inference idempotency does not promise response-body replay: a duplicate active request returns the existing admission identity; a duplicate completed request returns a stable conflict/status reference unless that wire protocol later defines replay. Return request/canonical/actual model, model provider, release, data-policy, experiment/bucket, trace ID when eligible, and price/usage metadata. Raw endpoint/capacity-provider identity remains operator-only.

The same paths accept dedicated native-distribution credentials. Credential lookup resolves exactly one principal before policy/model resolution: `WorkspacePrincipal` or `DistributionChannelPrincipal`. A workspace credential selects organization prepaid accounting and the workspace-filtered catalog. A channel credential selects a versioned distribution profile, channel catalog/price book, exposure/concurrency limits and receivable settlement. No header/body value can switch principal kind, organization, workspace, distribution channel, catalog profile or financial domain. Customer-configured gateways forward a workspace credential and remain workspace traffic.

For a native OpenRouter request, OpenRouter validates its end user's OpenRouter token and account, then calls the same public Grad gateway with a Grad-issued OpenRouter channel credential. Grad validates that channel credential and admits against channel exposure/model/capacity/rate/concurrency state; it does not receive or validate the end-user token. The public gateway is the only allowed channel ingress. AWS inference-edge, cell and runtime endpoints are private and reject channel/customer keys; cells receive only the edge's short-lived signed service identity and exact-release request.

The production OpenAI-compatible base URL is configured as `GRAD_OPENAI_BASE_URL` and includes `/v1`; DNS is frozen by deployment, not generated contracts. Baseline OpenAI compatibility requires only standard bearer auth and fields. Optional `x-grad-*` metadata must not be required by official OpenAI clients or customer gateways.

OpenAPI/JSON Schema plus recorded conformance fixtures are authoritative for public JSON and streams. Provider-native skins remain separate protocol structs; do not force Google or Anthropic unions into OpenAI shapes. Implement an explicit support matrix per field/event. Preserve unknown response metadata only where safe; never silently accept a request feature that will be dropped.

Stable gateway errors have JSON fields `error.type`, `error.code`, `error.message`, `error.param`, and `request_id`, translated to protocol-native envelopes when required. Billing status examples:

- `402 insufficient_credits` with no balance amount disclosure beyond the authenticated organization;
- `429 low_balance_concurrency_limit` with a bounded `Retry-After`;
- `403 organization_suspended`, `organization_reconciling`, or `workspace_suspended`;
- `503 admission_unavailable` when Redis cannot guarantee reservation.

Protocol/capability errors are equally stable: `400 unsupported_parameter`, `unsupported_capability`, `invalid_tool_schema`, `context_too_large`, `incompatible_model`, `ambiguous_model`, or `provider_mismatch`; `404 model_not_found`/`model_provider_not_supported` for absent catalog identity; `429 route_capacity_exhausted` when the exact eligible lane exists but temporary capacity is unavailable; `503 admission_unavailable`, `route_unavailable`, or `upstream_midstream_error` for serving/control infrastructure failure. A request outside the selected model/release's tested capability/data-policy matrix fails before provider spend. The gateway does not silently remove fields, truncate content, invoke a parser/search plugin, repair output, cross a direct provider/model/version, or downgrade Grad effort/speed.

### Public model semantics

`GET /v1/models` returns only models allowed by effective organization/workspace/key policy. Each entry has the OpenAI-compatible core plus a namespaced `grad` object:

```json
{
  "id": "grad/high/fast",
  "object": "model",
  "owned_by": "grad",
  "grad": {
    "kind": "grad",
    "effort": "high",
    "speed": "fast",
    "release_id": "rr_...",
    "lifecycle": "stable",
    "modalities": ["text", "image"],
    "capabilities": ["tools", "structured_output", "reasoning"],
    "context_tokens": 200000,
    "max_output_tokens": 16000,
    "data_modes": ["product_intelligence", "no_retain"],
    "pricing": {"currency": "USD", "version": "pb_..."}
  }
}
```

Exact prices use integer/string unit fields in the documented schema; the example omits rates to avoid implying floating-point money. Direct entries use `kind: direct`, canonical IDs such as `openai/<id>`, an exact provider/model/version and any safe compatibility aliases. Stable family heads such as `grad/glm-5.2/fast` use `kind: grad_family`; immutable pins such as `grad/glm-5.2/fast@r2026.07.13.3` use `kind: grad_release`. Every Grad entry discloses its current immutable route release and bundle identity in the namespaced object. Responses echo the canonical requested identity and expose actual family/release in Grad headers and authenticated usage metadata. The standard response `model` field convention is frozen per protocol fixture before implementation.

`x-grad-session-id` is customer-chosen bounded opaque text, HMAC-normalized before indexing, and never a billing identity. Given the same active release, requirements and healthy candidates, it yields the same route decision. A route break returns a reason in usage metadata. Request-level no-retain may only make workspace data policy stricter; it cannot broaden access or retention.

Model resolution is deterministic:

1. Canonical `grad/<effort>/<speed>` resolves a qualified active managed-product release; all targets are owned inference for that cell.
2. Canonical `grad/<family>/<speed>` resolves the active release within that family's declared compatibility envelope.
3. A Grad identity with `@<release>` resolves exactly one immutable supported `RouteRelease`; it never follows an alias head.
4. Canonical `<provider>/<model>` resolves exactly that curated provider/model definition.
5. A bare upstream model ID resolves only if the active alias registry has exactly one binding, or `x-grad-provider` names the matching curated provider.
6. During preview, `grad/<effort>/slow` may resolve to `grad/<effort>/flex` with warning headers; it is not a fifth speed class. Other deprecated preview aliases follow the same documented warning/removal contract.
7. No request body can supply endpoint URLs, provider arrays, weights or arbitrary credentials.

A valid `x-grad-migration-experiment` is the only exception to ordinary direct-pin routing. It identifies an active customer-approved experiment bound to the same organization/workspace/source model/workload, budget and expiry. The gateway deterministically selects baseline direct or candidate Grad before pricing/admission and discloses the choice. Missing/invalid/mismatched/expired headers fail or use the ordinary hard pin according to the published error contract; they never silently enroll traffic. Creating an experiment in the console does not affect requests without the header.

## First-party control API

The Vite application calls tRPC routers under `/trpc`:

- `session`: current user, active organization, and active workspace;
- `organizations`: create, list, update, switch, organization settings;
- `organizationMembers`: list, invite, accept, role, remove;
- `workspaces`: create, list, update, switch, members, limits, delete request;
- `apiKeys`: list, create, revoke, rotate;
- `credits`: organization balance, top-up intent, history, receipt link, warning settings;
- `usage`: ClickHouse-backed aggregate and paginated request facts behind typed filters; PostgreSQL remains financial authority;
- `models`: Grad managed effort/speed matrix, stable family heads, immutable release pins, curated direct-provider registry, aliases, lifecycle, capability/data-policy/price detail, and workspace access policy;
- `workloads`: ClickHouse-backed profiles, traces, spend/latency/capability summaries and migration evidence;
- `traceAccess`: single-trace view, bounded export and delete requests; each view/export requires workspace authorization and produces a short-lived signed internal grant plus audit event;
- `migration`: candidates, recommendations, evaluator settings, replay/shadow/canary experiments, budgets, stop/cancel/promote actions;
- `settings`: team/workspaces, Product Intelligence/no-retain, retention/export/delete, budgets and advanced limits;
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
| `workspaces` | organization, name/slug, exactly-one Default flag, status, concurrency/output/reserve/privacy/model policy, config version and monotonic opaque cache epoch rotated on deletion/privacy-boundary change. |
| `workspace_memberships` | unique workspace/user, workspace role/status; user must also have active organization membership. |
| `api_keys` | organization, workspace, optional creator/owner kind, public prefix, keyed digest, scopes, status, expiry, last-used; raw secret never stored. |
| `model_provider_definitions` | curated namespace, adapter/profile version, lifecycle, training/retention policy and operator approval. A compatibility view may preserve the old name during migration. |
| `model_products` | Grad effort/speed identities, lifecycle, published envelope and active release. |
| `model_definitions` | provider-qualified model/version or Grad checkpoint, owner/license, aliases, modalities, context/output limits, exact supported parameters, lifecycle and public metadata. |
| `model_aliases` | unique alias, provider constraint, canonical model, activation/removal dates; ambiguous active bare aliases forbidden. |
| `direct_model_endpoints` | exact model provider/model, encrypted secret reference, region/data policy, capacity, buy-price version and status. Grad cells/targets have a separate fleet lifecycle. |
| `research_campaigns` | immutable approved objective/search scope, model/workload/hardware targets, quality/SLO/economics policy, controls, budget, timeout, data/provider authority, stop rules and lifecycle. |
| `experiment_specs` / `experiment_runs` | content-addressed preregistration and append-only executions with exact scope identities, predictions, fidelity, seeds, observations, environment validity, metering and cleanup evidence. |
| `evidence_claims` | versioned claim, exact scope, evidence class, analysis/control artifacts, uncertainty, composition graph, admission decision, expiry and independent reviewer. |
| `research_candidates` | lineage DAG node, parent bundles/candidates, coherent intervention set, implementation source and candidate lifecycle. |
| `model_stack_bundles` | canonical manifest digest, immutable S3/ECR references, complete model/runtime/kernel/serving/topology/placement/protocol/security identity, signatures and support metadata. |
| `bundle_qualifications` / `bundle_gate_results` | exact bundle, policy/evaluator/holdout versions, gate outcomes, measurements, signed attestations, limitations, expiry and invalidation reason. |
| `release_proposals` / `release_approvals` | exact bundle/qualification, product aliases, price/SLO/capability/placement envelope, rollout/rollback, proposer and independent approval signatures. |
| `model_alias_heads` | versioned family or managed-product alias generation, active/rollback release, effective time and audit event; immutable pins do not use a moving head. |
| `qualification_evidence` | endpoint/model/scope, evidence kind, fixture/evaluation version, measured result, threshold, artifact reference, expiry. |
| `route_releases` | immutable direct provider/model or Grad managed/family/pinned identity, exact bundle digest, fixed sell prices, eligibility/SLO, attempt/session policy, release state and rollback target. |
| `route_candidates` | release, concrete model, endpoint selector, priority/weight, capability/privacy/capacity constraints, required evidence. |
| `route_rollouts` | release, deterministic bucket range, audience, start/halt state, SLO gates. |
| `capacity_intents` / `capacity_leases` | durable desired pool generation, budget/owner epoch, external allocation identity/history, acquired cost, lifecycle and cleanup evidence; projected into rebuildable fleet CRDs. |
| `distribution_channels` | downstream gateway contract, credentials reference, receivable/risk state, channel price book, model allowlist, concurrency/rate/capacity limits and reconciliation terms. |
| `distribution_profiles` | immutable protocol/catalog/privacy/price/limit profile version for one approved native channel; never selected by an untrusted request field. |
| `channel_receivable_transactions` | unique channel usage/revenue/credit/invoice/adjustment business entries; separate from customer organization credit. |
| `trace_records` | organization/workspace/request, data mode, capture status, encrypted S3 reference, per-trace wrapped-key state, byte/content classes, retention deadline, deletion/export/ClickHouse projection state; no raw payload. |
| `trace_access_grants` | one trace/workspace/user/action, nonce digest, issued/expiry/consumed state and audit request; short-lived, single-use, never a bearer URL to S3. |
| `trace_analytics_outbox` | authoritative usage/trace version, content-free typed projection payload, ClickHouse batch/deduplication/checkpoint state and retry/dead-letter metadata; pruned only after durable projection. |
| `workload_profiles` | workspace-local explicit/fingerprinted workload, source provider/model, capability/schema hashes, traffic/error/token/latency/spend aggregates. |
| `migration_candidates` | workload, candidate Grad release, compatibility, projections, evidence level/confidence, exclusions and current state. |
| `migration_experiments` | candidate, replay/shadow/live-canary mode, sample/bucket, evaluator, budget, stop conditions, state and audit actor. |
| `migration_recommendations` | immutable evidence snapshot, source/candidate versions, quality/cost/latency result, uncertainty, status and expiry. |
| `workspace_budgets` | organization/workspace, interval (`daily/weekly/monthly/lifetime`), integer limit; not a wallet. |
| `api_key_budgets` | organization/workspace/key, interval and integer limit. |
| `price_books` | immutable version/effective time; direct provider/model and Grad effort/speed release input/output/cache/reasoning/tool sell SKUs plus reservation buffer. |
| `topup_intents` | organization, amount, currency, Stripe IDs, idempotency key, state. |
| `payment_events` | unique provider event ID, type, object ID, verification/processing metadata. |
| `ledger_accounts` | organization asset/liability/revenue/clearing account and currency. |
| `ledger_transactions` | unique business/idempotency key, type, effective time, evidence link. |
| `ledger_entries` | transaction, account, signed micro-USD amount; entries sum to zero per currency. |
| `usage_charges` | unique event ID/request/attempt, organization/workspace/key, requested product/model, actual model/endpoint class, route release/decision, price version, units, sell, buy evidence. |
| `usage_corrections` | unique original charge/reason/idempotency key, compensating sell amount, anti-abuse decision and ledger transaction. Never mutates original usage. |
| `outbox_events` | aggregate, version, typed Protobuf payload, state/attempt/lease. |
| `audit_events` | actor, organization, optional workspace, action, target, request, safe before/after metadata. |

Tenant indexes begin with `organization_id`; workspace access paths then include `workspace_id`. Constraints/triggers or transactional domain checks guarantee exactly one Default workspace per organization, workspace membership implies organization membership, and a key's organization matches its workspace. Authorization tests generate arbitrary organizations/workspaces/users/memberships and verify no cross-boundary query or mutation.

## ClickHouse analytical projection

ClickHouse is not part of the public contract and no browser or customer receives SQL/database credentials. The Hono domain layer exposes a closed `TraceQuery` grammar with organization/workspace derived from server authorization, bounded time range, cursor, sort, model/workload/status/capture filters, and predeclared aggregate choices. The repository always supplies query parameters plus maximum execution time, result rows/bytes and an audited query ID; arbitrary SQL, expressions, table functions and user-selected columns are impossible.

The initial content-free tables are `request_facts_v1`, `attempt_facts_v1`, `evaluation_facts_v1`, `workspace_rollups_1h_v1`, and `model_rollups_1h_v1`. Every base row carries organization/workspace, immutable event identity/version, event time, retention deadline and only typed allowlisted dimensions. Requested/canonical/actual model, provider or Grad effort/speed/release, status/error class, capability flags, units, copied sell/buy evidence classes and timings are allowed. Prompts, completions, tool payloads, files, credentials, arbitrary headers/URLs and free-form tags are forbidden by schema and leak-scanner tests.

`request_facts_v1` is versioned/deduplicating rather than mutable OLTP state. Projection commands use a deterministic event/deduplication identity; duplicate, reordered and rebuilt input must converge. Rollups are recomputable and never feed ledger/admission. PostgreSQL tombstones and retention deadlines are checked before trace detail and suppress rows while asynchronous ClickHouse deletion converges. See [ClickHouse trace analytics decision](CLICKHOUSE_TRACE_ANALYTICS_DECISION.md) for schema, read/ingest/delete/restore behavior.

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
    models.proto
    traces.proto
    migration.proto
    pricing.proto
  gradiated/inference/v1/
    serving.proto
    releases.proto
    cells.proto
    capacity.proto
  gradiated/research/v1/
    campaigns.proto
    experiments.proto
    evidence.proto
    candidates.proto
    bundles.proto
    qualification.proto
    workflows.proto
```

Important messages include `ApiKeyProjection`, `OrganizationBillingProjection`, `WorkspacePolicyProjection`, `ChannelAccountProjection`, `ModelProviderDefinition`, `ModelProduct`, `ModelDefinition`, `ModelAlias`, `ModelFamily`, `ModelAliasHead`, `GradEffort`, `GradSpeed`, `DataMode`, `CapabilityRequirement`, `ResearchCampaign`, `ExperimentSpec`, `ExperimentRun`, `EvidenceClaim`, `ResearchCandidate`, `ModelStackBundleManifest`, `BundleQualification`, `BundleGateResult`, `ReleaseProposal`, `ReleaseApproval`, `DirectModelEndpointProjection`, `QualificationReference`, `RouteRelease`, `RouteCandidate`, `RouteDecision`, `ReleaseManifest`, `CellTarget`, `GenerateRequest`, `GenerateEvent`, `CapacityIntent`, `CapacityLease`, `CapacityPoolSpec`, `CapacityAllocationSpec`, `CapacityAllocationStatus`, `InferenceCellStatus`, `CellHeartbeat`, `TraceEnvelope`, `TraceCaptureEvent`, `WorkloadProfile`, `MigrationCandidate`, `MigrationExperiment`, `MigrationRecommendation`, `LimitWindow`, `PriceBook`, `Reservation`, `ReservationEvent`, `SettlementEvent`, `ChannelSettlementEvent`, `FailedRequestCreditEvent`, `ProjectionCommand`, and `ReconciliationCheckpoint`.

`ModelStackBundleManifest` has generated TS/Rust types but its identity is the SHA-256 of RFC 8785-canonical JSON, not ordinary JSON bytes or an assumed cross-language Protobuf wire ordering. `RouteRelease`, `CellTarget` and internal `GenerateRequest` carry the exact bundle digest and alias generation. A cell cannot become ready when its attested runtime image, manifest, placement envelope or signatures differ from the release.

Rules:

- Protobuf v3 fields use explicit domain enums and wrapper/optional presence where absence differs from zero.
- Never reuse field numbers or enum values; reserve removed fields/names.
- IDs are strings/bytes by declared convention; money is signed `int64` micro-USD with checked boundary conversion to JS `bigint`.
- Timestamps use `google.protobuf.Timestamp`; durations use `Duration`.
- Events carry `event_id`, `organization_id`, `workspace_id`, `api_key_id`, `request_id`, `billing_epoch`, `sequence`, `schema_version`, `occurred_at`, and idempotency/business keys.
- Protobuf payloads in Redis Streams are binary/base64 or a documented binary-safe field; stream envelope fields remain inspectable.
- Gateway-to-inference messages carry exact release digest, deadlines, canonical input, capability/data mode, opaque billing principal and opaque cache scope. Provider allocation IDs, credentials, bids and Kubernetes objects are forbidden from that serving contract.
- Shared fleet Protobuf is canonical for Grad domain fields. CRD JSON schemas/types are generated from or checked against that contract, and CI fails on stale Rust/TypeScript/CRD output. Kubernetes metadata/spec/status conventions remain CRD-specific rather than leaking into the serving protocol.
- `GenerateEvent` sequence and cumulative usage are monotonic. A retry after output is forbidden; pre-output retries preserve exact release/effort/speed/data policy.

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
gw:model-catalog:<version>                              binary immutable managed/concrete catalog
gw:route-release:<release_id>                           binary immutable candidates/eligibility/attempt policy
gw:route-head:<canonical_model_product>                 pointer to active stable/canary releases
gw:cell-target-set:<route_release_id>                   signed bounded exact-release cell targets
gw:key-index:<public_lookup_id>                         auth locator: organization/key IDs + digest version
gw:{<organization_id>}:traces                           bounded encrypted trace Redis Stream
gw:trace-ingest-key:<version>                           public encryption key + validity window
gw:reservation-leases                sorted-set/sharded advisory index; entries point to organization-tagged keys
```

If a global lease index prevents one atomic cross-slot operation, it is advisory only: the authoritative lease remains in the organization-tagged reservation. Sweepers read the index then invoke the organization-local atomic transition.

The API-key prefix contains a non-secret random lookup ID. The gateway reads the global locator to find the organization/key slot, then the organization-local atomic admission validates the keyed digest, status, workspace binding and version; the locator alone can never authenticate or dispatch. Revocation removes/fences both projections with urgent lag alarms.

Global catalog/release keys are immutable or atomic pointers and are read before the organization-local financial script; admission receives and verifies canonical provider/model or Grad release, data mode, route decision and price versions against workspace/key policy. Trace stream append is separate from financial admission/settlement and carries ciphertext only. Projection writes carry an expected prior/new version; stale/reordered commands no-op. Organization billing epochs fence old events. Organization/workspace suspension uses high-priority commands and lag alarms.

## Request and usage identity

- `request_id`: one customer request, stable across bounded target attempts.
- `attempt_id`: one upstream attempt.
- `route_release_id`: immutable direct-model or Grad effort/speed release admitted and priced for the request.
- `route_decision_id`: deterministic selection result including capability filter, session/canary bucket, candidate and endpoint class.
- `cell_target_id`: signed external inference cell/target epoch chosen for an owned attempt; never a billing or provider credential.
- `reservation_id`: one organization-funded reservation attributed to one workspace/key, usually one request.
- `event_id`: unique immutable event; redelivery has the same ID.
- `usage_charge_id`: PostgreSQL posting identity derived from settlement event ID.

Usage records include organization, workspace, API key ID, request/attempt, ingress protocol, requested canonical provider/model or Grad effort/speed, actual provider/model/release, route decision, region/native tier, data mode and trace ID/status, workload ID/fingerprint, capabilities, timings, terminal/usable-output state, units, immutable price/reserve/sell/credit, provider buy-cost evidence and metering evidence class.

Corrections append compensating usage/ledger events. They do not mutate the original financial fact.
