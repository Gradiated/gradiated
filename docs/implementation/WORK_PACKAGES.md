# Complete implementation work packages

Status: canonical dependency and delegation plan

This catalog decomposes the full startup into bounded packets suitable for parallel implementation agents. A packet is not permission to redesign its interfaces. If a frozen input is missing or contradictory, the agent opens a contract issue and continues on non-blocked work rather than inventing a second authority.

## 1. Standard packet contract

Every implementation issue copies this section into a task packet and fills concrete values.

| Field | Required content |
| --- | --- |
| outcome | one externally observable capability |
| dependencies | completed packet IDs and exact contract/schema versions |
| owned paths | disjoint files/directories; generated output ownership stated |
| excluded paths | neighboring packages and active work explicitly protected |
| inputs | fixtures, APIs, migrations, config and authority supplied by dependencies |
| outputs | code, migration, generated artifacts, dashboards/runbooks and handoff |
| failure behavior | timeout, retry, cancellation, duplicate, dependency loss and rollback |
| tests | deterministic unit/example, PBT/state model, integration and E2E layer |
| budget | external request/GPU/cloud/time cap; zero unless authorized |
| cleanup | resource and secret-safe cleanup proof |
| completion | exact commands plus behavioral evidence |

Universal definition of done:

1. No unapproved dependency, table, field, service, queue, controller or public field was added.
2. New state has one writer, one reason to persist and a tested cleanup/migration path.
3. All external input is bounded and validated; all errors are stable and payload-safe.
4. Invariants have property/state-machine tests with replayable seeds.
5. Integration uses fakes/Testcontainers first; protected real tests are separately budgeted.
6. Logs, metrics, fixtures and CI artifacts contain no secrets/customer payloads.
7. Generated files are current and clean regeneration creates no diff.
8. Relevant handoff/runbook is updated and the owned commit contains no unrelated paths.

## 2. Parallel execution rules

- A wave may start when every incoming solid dependency is merged to `main`.
- Agents within a wave use disjoint owned paths. Shared index files have one integrator owner.
- Contract producers land fixtures before consumers. Consumers pin the fixture digest in their packet.
- Database migration ownership is serialized through `product/packages/db/migrations`; domain packages submit migration requirements to the DB owner.
- Helm/GitOps desired-state files have one infrastructure integrator even when application agents own chart values/schema proposals.
- Generated code is changed only by the contract owner; consumers never patch generated output manually.
- Active research implementation under `research/factory/**` remains owned by its current issue until handed off. The RF packets below describe the target sequence, not authorization to overlap it.

## 3. Delivery waves

| Wave | Goal | Parallel packets after prerequisites |
| --- | --- | --- |
| W0 | repository and contract substrate | FND-00 through FND-04, DEV-00 |
| W1 | durable domain and control skeleton | DB-00, CP-00, API-00, WEB-00, INFRA-00 |
| W2 | tenant and money authority | CP-01/02, BILL-00/01, API-01, INFRA-01/02 |
| W3 | atomic serving foundation | BILL-02/03, GW-00/01/02, API-02, WEB-01 |
| W4 | first paid direct request | GW-03/04/05/06, INT-00, WEB-02, OPS-00 |
| W5 | retained intelligence and deletion | TRACE-00/01/02, REC-00, CP-03, WEB-03 |
| W6 | owned inference substrate | BUNDLE-00, IR-00, CELL-00/01, RUNTIME-00, FLEET-00/01, INFRA-03 |
| W7 | multi-node and research production | CELL-02, RUNTIME-01, FLEET-02/03, RF-00..04, QUAL-00 |
| W8 | distribution and production hardening | DIST-00/01/02, OPS-01/02/03, INFRA-04 |
| W9 | launch qualification | LAUNCH-00 through LAUNCH-03 |

Revenue gate: W4 can onboard bounded paid direct traffic after its own production gates; it does not wait for W6-W8. Public Grad-owned inference waits for W7 qualification. Native OpenRouter listing waits for W8.

## 4. Foundation packets

### FND-00 — Monorepo and pinned toolchains

- Depends: none.
- Owns: root workspace manifests, lockfiles, tool-version files, base formatting/lint configuration.
- Build: pnpm workspace for product TypeScript; Rust workspaces for gateway/product services and `grad`; uv/Python project integration; pinned Node/Rust/Python/Buf/Terraform tool versions.
- Must not: create application domains or duplicate the active research package configuration.
- Acceptance: clean install from lockfiles; offline cache-compatible CI; hello-world typecheck/test for each language; license/secret scan has deterministic config.

### FND-01 — Protobuf, JSON Schema and generation pipeline

- Depends: FND-00.
- Owns: `product/proto/**`, cross-language generation scripts/conventions and language `gen/` outputs. Artifact-source schemas remain with BUNDLE/RUNTIME/RF owners.
- Build: gateway snapshot/billing/trace, inference serving/registration and research service/reference packages from [the contract catalog](CONTRACT_CATALOG.md); Buf lint/breaking; prost/TS/Python generation only for real consumers; canonical JSON helper and schema validation.
- Failure: generation fails on unsupported tool version, dirty output, missing fixture or breaking change.
- Acceptance: cross-language round-trip goldens, unknown-field fixtures and clean regeneration in CI.

### FND-02 — Public inference schema fixtures

- Depends: FND-00.
- Owns: `product/schemas/inference/**`, `product/fixtures/contracts/inference/**`, fixture update tooling.
- Build: pin official schema/document snapshots; encode only launch Responses, Messages and Models subset; valid/error/stream/cancellation fixtures; record upstream retrieval/version.
- Must not: implement Chat, Embeddings or provider-hosted products.
- Acceptance: fixtures validate against local schemas; unsupported fields have expected stable errors; no network required for bounded tests.

### FND-03 — Shared testkit and PBT replay

- Depends: FND-00, FND-01.
- Owns: `product/packages/testkit/**`, gateway testkit, shared replay artifact format and CI upload/replay scripts.
- Build: deterministic clocks/IDs, fake Stripe/providers/router/cells/S3/KMS, disposable PostgreSQL/Valkey helpers, state-machine seed capture and shrink-path replay.
- Acceptance: intentional failing properties emit one-command replay artifacts in TS/Rust/Python; test cleanup proves no containers/processes remain.

### FND-04 — Configuration, errors and observability primitives

- Depends: FND-00.
- Owns: typed config packages, safe error taxonomy, logging/metric wrappers shared inside each language workspace.
- Build: environment-name/secret-reference loading, startup validation, request/incident IDs, bounded metric labels and redaction tests.
- Must not: create a universal cross-language application framework or generic event envelope.
- Acceptance: missing/invalid config fails before readiness; fuzzed secret/payload markers never appear in captured logs/errors/metrics.

### DEV-00 — `grad` CLI and local orchestration

- Depends: FND-00, FND-03.
- Owns: `tools/grad/**` or designated Rust CLI crate, compose/mprocs configuration and local fixture seeding.
- Build: `grad doctor`, `start`, `stop`, `status`, `logs`, `generate`, `test`, `infra check`, `helm check`, `research` wrappers exactly as [the CLI contract](../../infra/docs/GRAD_CLI.md).
- Safety: never accept secret values in argv; print underlying command in verbose mode; refuse production mutation locally.
- Acceptance: a clean machine can start fake stack, run a funded fake request and stop with no orphan process/container.

## 5. Database and domain packets

### DB-00 — PostgreSQL base schema and migration harness

- Depends: FND-00, FND-03.
- Owns: `product/packages/db/**`, serialized migration directory and schema test harness.
- Build: Drizzle schema for the exact minimal persistent model, reviewed SQL migrations, constraints/indexes, transaction helper, scoped repositories, test reset and migration-forward/backward-compat tests.
- Fields: use [the simplicity model](../SIMPLICITY_REVIEW.md#minimal-persistent-model); any addition needs consuming query/command and invariant in this packet.
- Acceptance: migration from empty and previous fixture; all FKs/unique/check constraints; tenant predicate tests; no schema push outside disposable tests.

### CP-00 — Domain/application kernel

- Depends: FND-04, DB-00.
- Owns: `product/packages/domain/**`, `authz/**`, UnitOfWork/outbox/audit application ports.
- Build: typed IDs/money, actors, domain error mapping, command/query boundaries, small role matrices, outbox and audit contracts.
- Must not: import Hono, React, Drizzle implementation, Stripe, Valkey or AWS SDK types into domain packages.
- Acceptance: dependency-boundary lint plus state/authorization PBT using in-memory ports.

### CP-01 — Organizations, Default workspace and membership

- Depends: CP-00, DB-00.
- Owns: tenancy domain/application/repository modules and related migrations submitted through DB owner.
- Build: organization transaction, exactly one Default workspace, org/workspace memberships, issue/revoke/reissue/accept invitations, role changes, last-owner guard, terminal non-Default workspace archival with key revocation and scoped queries.
- Failure: duplicate/revoked/reissued invite, duplicate accept, expired token, concurrent organization creation and cross-tenant ID guessing have explicit behavior.
- Acceptance: fast-check model proves Default/owner/tenant invariants under arbitrary command sequences and transaction retries.

### CP-02 — Workspace keys and serving policy

- Depends: CP-01, FND-01.
- Owns: key/policy domain modules, digest/pepper crypto and snapshot builder.
- Build: display-once create, digest lookup, expiry, revoke, create-new rotation; workspace model allowlist, monthly/concurrency/data-mode policy; monotonic snapshots.
- Security: raw key exists only in create response memory; database/Valkey/logs store no recoverable key.
- Acceptance: collision/prefix, pepper rotation, concurrent revoke/use and policy-version PBT; cross-language snapshot golden.

### CP-03 — Self-service organization deletion

- Depends: CP-01, CP-02, BILL-03, TRACE-02.
- Owns: deletion use cases/worker and `organization_deletions` workflow table.
- Build: recent-owner request/cancel/status, immediate admission suspension, fixed window, drain/reconcile/refund, trace purge, access revocation and pseudonymous financial retention.
- Failure: every step is restartable; blocked financial/external uncertainty preserves suspension and actionable error code.
- Acceptance: model-based crash/reorder/retry test reaches completed/cancelled/blocked safely; no deleted principal can authenticate; statutory rows contain no customer payload or live identity.

## 6. REST, auth, UI and MCP packets

### API-00 — Hono route registry and problem details

- Depends: FND-00, CP-00.
- Owns: control HTTP shell, route manifest, validation/error/idempotency/pagination middleware and OpenAPI generation.
- Build: `/api/v1`, stable operation IDs, described Zod components, response validation in tests, RFC-style problems and request IDs.
- Acceptance: recursive description/example gate, duplicate operation/path failure, unknown mutation key rejection and generated OpenAPI clean diff.

### API-01 — Better Auth and authorization context

- Depends: API-00, CP-01, DB-00.
- Owns: Better Auth adapter/config/tables, cookie/CSRF/CORS middleware, session/org/workspace actor loaders and recent reauth.
- Build: email/password sign-up/sign-in, email verification, recovery/session, selected organization/workspace context, OAuth 2.1 provider foundation for MCP and one SES-backed bounded-template mail port for verification/recovery/invitations. Social login is deferred. Tokens/invitation rows remain PostgreSQL authority and endpoints do not reveal address existence.
- Acceptance: session fixation/CSRF/origin/expired-membership/cross-workspace tests; fake mail retry/non-enumeration tests; library tables are the only user/session authority.

### API-02 — Seed control resources

- Depends: API-01, CP-02, BILL-01.
- Owns: organization/member/workspace/key/billing/model route registrations and transport mapping.
- Build: exact route groups in contract catalog with idempotency and sensitive-output annotations, including non-Default workspace archival and bounded no-store usage CSV.
- Acceptance: generated client black-box CRUD journeys; every route exercises organization/workspace predicates; key secret and checkout URL never appear in docs examples/logs.

### API-03 — Generated MCP role

- Depends: API-02.
- Owns: MCP allowlist generator, REST client adapter and stateless Streamable HTTP server role.
- Build: OAuth authorization code + PKCE, short-lived user/org-bound tokens, safe tool names/descriptions/input/output schemas and annotations.
- Must not: import repositories/domain packages or expose key secret, checkout, deletion, trace plaintext or operator actions.
- Acceptance: tool inventory equals reviewed allowlist; every tool calls REST; revoked session/membership fails; injection/oversized input tests pass.

### WEB-00 — Vite/shadcn application shell

- Depends: FND-00, API-00.
- Owns: `product/apps/web/**`, shared UI primitives and generated-client wrapper only.
- Build: Vite, React, TanStack Router/Query, Tailwind, shadcn, accessible layout, auth/loading/error boundaries and organization/workspace query-key discipline.
- Acceptance: no handwritten API DTO; selected scope change clears scoped cache; axe/keyboard/responsive smoke passes.

### WEB-01 — Onboarding, workspaces and keys

- Depends: WEB-00, API-02.
- Build: five-minute organization activation, implicit Default workspace, additional workspace/member/settings and create-copy-once/revoke key experience.
- Acceptance: Playwright journeys for first organization, invitation, scope switch, secret one-time display and unauthorized role controls.

### WEB-02 — Billing, models and usage shell

- Depends: WEB-00, API-02, BILL-01.
- Build: balance/top-up, immutable transaction/usage list, bounded usage CSV export, curated model capability/price view and bounded usage filters.
- Acceptance: money formatting uses bigint micros; checkout and webhook state refresh safely; empty/loading/lag/error states are explicit.

### WEB-03 — Trace, recommendations and deletion UX

- Depends: WEB-02, TRACE-02, REC-00, CP-03.
- Build: trace metadata/detail grant flow, capture-state/data-mode explanation, recommendation evidence/evaluation controls and destructive organization deletion/cancel/status screens.
- Acceptance: trace plaintext is no-store and absent from client cache persistence; recent reauth/name confirmation; deletion state survives refresh and blocks mutation.

## 7. Billing and Valkey packets

### BILL-00 — Fixed-chart ledger and balance projection

- Depends: DB-00, CP-00.
- Owns: billing domain/application/repositories and ledger constraints.
- Build: USD fixed chart, balanced transaction posting, unique business keys, locked `organization_balances`/`channel_balances`, compensating entries and reconstruction query.
- Acceptance: model-based top-up/usage/refund/chargeback/correction sequences always balance; projection equals ledger; overflow/underflow and duplicate/conflict fail safely.

### BILL-01 — Stripe top-ups and webhook state machine

- Depends: BILL-00, API-00.
- Owns: top-up application/Stripe adapter/raw webhook route and fixtures.
- Build: policy-v1 whole-USD $10–$10,000 amounts, checkout intent, signature verification, event dedupe, object/amount/org validation and balanced completion/refund/chargeback effects.
- Acceptance: fast-check reordered/duplicated/conflicting webhook sequences; commit-before-2xx; raw payload retained only in request memory and never fixtures/logs.

### BILL-02 — Valkey keyspace and atomic scripts

- Depends: FND-01, CP-02, BILL-00.
- Owns: projection publisher, Valkey schemas/scripts/functions and Redis integration tests.
- Build: disjoint organization/channel keyspaces, credential/release resolution, atomic reserve/settle/lease sweep, low-balance cap, monthly/concurrency limits and billing event append.
- Failure: noeviction/headroom checks, script timeout/unknown outcome recovery and idempotency conflict.
- Acceptance: proptest-state-machine against real Valkey proves no upstream-eligible token without reserve, one terminal, no negative available/concurrency and monotonic snapshots.

### BILL-03 — Financial consumer, reconciliation and rebuild

- Depends: BILL-00, BILL-02.
- Owns: TypeScript `apps/control` financial-role stream consumer, shared billing application projection/reconciliation commands and runbook.
- Build: consumer groups/claim/redelivery, usage posting, event receipt, projection update, full comparison and fenced epoch rebuild with conservative uncertain holds.
- Boundary: reuse BILL-00 ledger/repositories; do not create a Rust ledger implementation or a second financial domain.
- Acceptance: kill/restart at each DB/ack boundary; duplicate effects zero; stream retention pressure alarm; corruption fixture suspends affected account and rebuild restores equality without forgetting live holds.

## 8. Gateway and direct-provider packets

### GW-00 — Rust gateway server and canonical lifecycle

- Depends: FND-00, FND-01, FND-02, FND-04.
- Owns: gateway crate server/middleware/canonical request-event-error modules.
- Build: Axum/Tower/rustls ingress bounds, request state enum, cancellation/deadline, protocol/provider traits and safe telemetry.
- Acceptance: cancellation/failure injected at every transition; state cannot advance twice; no provider invocation adapter is yet enabled.

### GW-01 — Snapshot credential/catalog resolution

- Depends: GW-00, BILL-02.
- Owns: Valkey client/resolution modules.
- Build: peppered credential candidate lookup, organization/channel principal, workspace policy and deterministic stable/canary release selection.
- Acceptance: stale/regressed snapshot, revoked/expired key, ambiguous model, allowlist and deterministic canary properties.

### GW-02 — Admission, settlement and metering core

- Depends: GW-01, BILL-02.
- Owns: reserve/settle client, exposure estimator, attempt/usage meter and lease-safe terminal guard.
- Build: conservative sell estimation, one reservation token, low-balance/concurrency errors, actual sell calculation and exactly-once terminal call.
- Acceptance: arbitrary stream/cancel/provider error sequences prove no dispatch before reserve and settle-or-expire exactly once; actual-over-reserve incident path closes account.

### GW-03 — Models endpoint

- Depends: GW-01, FND-02.
- Owns: `/v1/models` protocol module.
- Build: authenticated list/get view from curated projected releases, capability/price/availability filtering and OpenAI-compatible object shape documented by fixture.
- Acceptance: workspace/channel catalog isolation, hidden unavailable Grad combinations, no internal endpoint/cell data.

### GW-04 — OpenAI Responses protocol

- Depends: GW-00, GW-02, FND-02.
- Owns: Responses parser/encoder/error and stream state modules.
- Build: exact stateless seed profile, ordered content/tools/results, supported structured/reasoning controls, native events and usage.
- Acceptance: official OpenAI client fake E2E stream/non-stream/tools/structured/cancel/errors; every deferred stateful/hosted field rejects before reserve.

### GW-05 — Anthropic Messages protocol

- Depends: GW-00, GW-02, FND-02.
- Owns: Messages parser/encoder/error and stream state modules.
- Build: version header, system/messages/content blocks, tools/results, bounded thinking, native events/usage.
- Acceptance: official Anthropic client fake E2E; dual-header same/different-principal cases; unsupported beta/feature rejects before reserve.

### GW-06 — Curated direct provider adapters

- Depends: GW-04, GW-05.
- Owns: provider adapter modules and provider conformance fixtures.
- Build: first OpenAI and Anthropic exact-model adapters, egress allowlist, strict TLS/redirect policy, error/usage mapping and bounded pre-output retry.
- Scope: one cheapest qualified model per provider first; each additional model/version is a registry/qualification change, not generic pass-through.
- Acceptance: deterministic fake malformed/partial/rate/timeout/cancel streams plus protected cheapest-model tests with hard cost caps and no body artifacts.

### INT-00 — End-to-end first paid slice

- Depends: API-02, WEB-02, BILL-03, GW-03, GW-04 or GW-05, GW-06, DEV-00.
- Owns: cross-service fake E2E fixtures/scripts only.
- Build: seed organization/credit/key, official client request through gateway/provider fake, stream, settle, post usage and display balance/usage.
- Acceptance: repeated/cancelled/failing cases reconcile; upstream fake records reservation proof timestamp before invocation; one command runs unattended.

## 9. Trace and customer-intelligence packets

### TRACE-00 — Gateway trace preparation and encryption

- Depends: GW-02, FND-01.
- Owns: gateway redaction/bounding/envelope-encryption/trace-stream module.
- Build: closed capture schema, credential/header stripping, file/oversize statuses, random data key and ingest-public-key wrapping, separate shed-able quota.
- Acceptance: fuzz secret markers and oversized content; no-retention emits no envelope; encryption failure never spills plaintext or threatens billing stream.

### TRACE-01 — Ciphertext persistence and retention

- Depends: TRACE-00, DB-00.
- Owns: intelligence role trace consumer, S3 object adapter, trace repository and retention worker.
- Build: idempotent object/metadata durability before ack, lifecycle deadline, object digest, capture status and key-destruction-first deletion.
- Acceptance: crash at put/DB/ack boundaries; same-ID/different-digest incident; lifecycle/delete replay and S3 fake/version tests.

### TRACE-02 — Authorized detail and PostgreSQL analytics

- Depends: TRACE-01, API-01.
- Owns: bounded usage/trace SQL queries, grant signer/nonce and trace-access role.
- Build: indexed organization/workspace/time queries, one-object grant, current membership/tombstone recheck, scoped decrypt and no-store streaming.
- Must not: add ClickHouse, generic analytics repository or presigned reusable ciphertext URL.
- Acceptance: cross-tenant/grant replay/revocation/delete race properties; production-shaped PostgreSQL query plans meet initial SLO fixture or create a measured tuning issue.

### REC-00 — Workload recommendation and bounded evaluation

- Depends: TRACE-02, CP-02, BILL-03.
- Owns: recommendation/evaluation domain and intelligence jobs.
- Build: workspace-scoped fingerprint, immutable summary, accept/dismiss/expire and explicit replay/shadow/live-canary authority/budget/stop conditions.
- Safety: no transition modifies customer ordinary traffic; replay/shadow use company budget, live canary uses ordinary admission plus cap.
- Acceptance: PBT proves budget/authority/stop invariants and no automatic alias/request rewrite; no-retention recommendations are labeled metadata-only.

## 10. Bundle, owned inference and fleet packets

### BUNDLE-00 — ModelStackBundle schemas and verification

- Depends: FND-01.
- Owns: artifact schema implementations, canonicalization/digest/signature/provenance libraries and fixtures.
- Build: model/checkpoint/operator/runtime/topology/bundle/qualification manifests from contract catalog.
- Acceptance: byte-identical canonical output across Python/Rust/TS where used; mutation changes digest; malformed/reference-cycle/signature/provenance tests.

### IR-00 — Private inference router

- Depends: FND-01, FND-04, GW-02.
- Owns: `product/services/inference-router/**`.
- Build: mTLS cell connection registry, exact-release attestation filter, least-load/capacity selection, deadline/stream relay, heartbeat/drain and payload-safe metrics.
- Must not: query PostgreSQL, allocate capacity, see price/balance/API keys or expose ranks.
- Acceptance: fake cell churn/duplicate identity/stale heartbeat/wrong digest/backpressure/cancel properties; direct traffic remains independent.

### CELL-00 — Cell agent, enrollment and runtime supervision

- Depends: BUNDLE-00, IR-00.
- Owns: cell agent/runtime launcher modules and fake runtime.
- Build: one-use token/CSR enrollment, short-lived identity rotation, allocation-scoped artifact credential use, signed digest verification, outbound mTLS HTTP/2 router connection, runtime start/readiness/drain, local protocol and cleanup.
- Acceptance: stolen/replayed token, wrong attestation/image, runtime crash, certificate expiry and drain deadline tests; cell has no customer credential or provider lifecycle secret.

### CELL-01 — Local scheduling and cache isolation

- Depends: CELL-00.
- Owns: cell local replica scheduler, active-sequence KV and prefix cache policy modules.
- Build: opaque trust domain from workspace/channel/release/retention class, exact-release cache, bounded memory/eviction and replica queue selection.
- Acceptance: no cross-scope cache hit under generated identities; no-retention cache enabled but never serialized; cancellation/free/eviction memory-accounting properties.

### FLEET-00 — SQL fleet state and planner

- Depends: DB-00, BUNDLE-00.
- Owns: capacity source/target/allocation/member/cell repositories and fleet planner.
- Build: target deficit, lease epoch/owner/expiry, budget/concentration checks, complete topology acquisition intent and drain/release commands. Desired warm count is computed from `capacity_targets`, recent CloudWatch release-level active/queued/rejected aggregates, measured cell throughput/startup/interruption and budget. Metric uncertainty preserves the configured floor and forbids aggressive scale-down.
- Acceptance: concurrent planners acquire one lease; budget/maximum cells never exceeded; partial multi-member intent is not routable.

### FLEET-01 — Driver framework, fake provider and sweeper

- Depends: FLEET-00, CELL-00.
- Owns: driver trait/framework, deterministic fake provider, ownership tag format, cleanup/orphan sweeper and provider qualification harness.
- Build: quote/create/observe/drain/delete/list-owned idempotency, unknown-outcome observation and acquisition freeze on cleanup uncertainty.
- Acceptance: state-machine PBT over provider reorder/timeouts/duplicate resources proves no leak and no double acquisition; list sweep finds unknown/expired resources.

### FLEET-02 — First native capacity provider

- Depends: FLEET-01.
- Owns: one provider-specific Rust driver and protected tests.
- Build: exact API/auth/offer/resource/tag/bootstrap/interruption/cleanup mapping for the selected provider; hard hourly/total budget and region/hardware allowlist.
- Acceptance: fake contract suite plus bounded real create/bootstrap/serve/preempt/delete/list-zero-orphans run; provider is not production-eligible without dated evidence.

### FLEET-03 — Managed-Kubernetes capacity provider

- Depends: FLEET-01, CELL-02.
- Owns: one provider-specific managed-Kubernetes driver, ordinary workload manifests and provider-local test fixtures.
- Build: acquire bounded provider cluster/node-pool capacity, create namespace/service-account/headless Service/StatefulSet or Jobs required by the exact topology, inject member enrollment/artifact grants and delete every underlying resource. The provider Kubernetes API is an adapter implementation, not Grad fleet authority.
- Must not: introduce Grad fleet CRDs, cross-provider scheduling, Argo ownership of dynamic allocations or assume provider autoscaling proves cell readiness.
- Acceptance: fake API/Kind contract plus bounded provider test for complete-member readiness, member loss, node-pool failure and zero-resource cleanup.

### FLEET-04 — Additional capacity-provider onboarding

- Depends: FLEET-02 or FLEET-03, QUAL-00.
- Owns: one new curated driver at a time plus its evidence profile.
- Build: implement the existing driver trait without changing it unless two measured providers expose a missing irreducible operation. Record auth, quota, offers, pricing, region/hardware, interruption, bootstrap, data/security, support and cleanup behavior.
- Acceptance: common provider harness and exact release/hardware qualification. Provider breadth is incremental; no dynamic plugin/discovery registry is added.

### CELL-02 — Multi-node topology

- Depends: CELL-00, FLEET-01, BUNDLE-00.
- Owns: multi-member join/coordinator/fabric launch modules and topology qualification fixtures.
- Build: exact ordinal/role tokens, headless discovery or native endpoint bootstrap inside one provider, runtime parallel dimensions and whole-cell fencing on required member loss.
- Acceptance: partial allocation rollback, duplicate/wrong ordinal, delayed join, collective failure/member loss and every-member cleanup PBT; router contract identical to single-node.

### RUNTIME-00 — First production runtime adapter

- Depends: BUNDLE-00, CELL-00, GW-04, GW-05.
- Owns: pinned vLLM-or-selected-runtime image definition, local serving adapter, tokenizer/metering/capability probe and tiny/representative fixtures.
- Build: exact bundle/runtime/topology flags, local typed serving protocol, readiness, streaming, cancellation, usage, cache configuration and safe shutdown. The runtime is an image implementation detail; public protocol translation remains in the gateway.
- Acceptance: reference-oracle output/usage parity, malformed/runtime crash/cancel tests, cold/warm cache and signed-image provenance. Selection of vLLM versus another runtime is recorded per bundle, not as a product enum.

### RUNTIME-01 — Custom research-produced runtime components

- Depends: RUNTIME-00, RF-03.
- Owns: out-of-tree model/operator/plugin build interface and production loading/ABI checks.
- Build: PyTorch/Transformers custom model code, Triton/CUDA/C++/Rust components behind explicit versioned runtime image boundaries; no production hot patch from a research workspace.
- Acceptance: independent reference oracle, exact-shape component tests, ABI/driver/hardware mismatch failure, reproducible image and full serving A/B before qualification.

### INFRA-03 — External-cell identity and networking

- Depends: INFRA-02, CELL-00, FLEET-01.
- Owns: Private CA/enrollment IAM/network policy, dedicated cell-connect NLB/service, outbound tunnel and provider bootstrap artifact infrastructure.
- Build: purpose CA, one-use enrollment route, certificate rotation/revocation, mTLS-only HTTP/2 cell-connect endpoint, allocation-tagged STS role restricted to exact artifact S3 paths/runtime ECR repository, egress restrictions and audit.
- Acceptance: external test cell can enroll/rotate/connect with no AWS long-lived key; unauthorized source/wrong allocation fails; compromised cell revocation removes route eligibility.

## 11. Research and qualification packets

### RF-00 — Research domain and immutable experiment specifications

- Depends: FND-01, DB-00; coordinate with active research-factory issue.
- Owns: Python program/hypothesis/campaign/spec/run/evidence application state once current owner hands it off.
- Build: exact minimal research model, authority/budget/deadline, immutable spec digest, evidence classes and negative-result preservation.
- Acceptance: Hypothesis state model rejects scope/budget/state violations and derives queue/frontier/open questions without persisted mirrors.

### RF-01 — Temporal workflows and idempotent activities

- Depends: RF-00, FND-03.
- Owns: deterministic portfolio/per-model/run/cleanup workflows and activity adapters.
- Build: timers, signals, cancellation, retries, heartbeats, human wait and cleanup; side effects only in idempotent activities calling application ports.
- Acceptance: Temporal replay across code versions, worker crash at every activity boundary, cancellation/timeout and cleanup proof; history cannot approve evidence.

### RF-02 — Experiment SDK and fidelity adapters

- Depends: RF-00, RF-01.
- Owns: research SDK, local/Kubernetes/native compute adapters and tiny deterministic model fixtures.
- Build: preregistration, environment capture, analytical/simulation/reference/microbenchmark/serving stages, telemetry and budgeted compute session ownership.
- Acceptance: each adapter emits same result envelope/artifact contract; fake capacity faults preserve evidence/cleanup; fidelity labels prevent cross-scope claim transfer.

### RF-03 — Bundle construction and evidence synthesis

- Depends: RF-02, BUNDLE-00.
- Owns: Python artifact/build pipeline and report synthesis.
- Build: checkpoint/operator/runtime/topology assembly, content-addressed upload, OCI digest/provenance, parent lineage and complete bundle creation.
- Acceptance: reproducible rebuild yields same digest; changed dependency changes digest; incomplete/unsigned/unlicensed source cannot produce proposal.

### QUAL-00 — Independent qualification service and gates

- Depends: RF-03, RUNTIME-01, CELL-02, GW-04, GW-05.
- Owns: separately credentialed Python evaluator role, qualification policy and immutable report format.
- Build gates: source/license/supply chain, model/operator correctness, protocol/metering, single-node, distributed topology, security/privacy/operations, quality/SLO/economics and staged canary.
- Independence: evaluator credentials cannot mutate research result, customer credit or release alias.
- Acceptance: known-bad bundles fail each gate; stale/scope-mismatched report cannot activate; one single-node and one multi-node positive fixture pass exact same serving contract.

### RF-04 — Always-on portfolio and release proposal

- Depends: RF-01, QUAL-00, CP-00.
- Owns: portfolio ranking/stop policy and signed release proposal integration.
- Build: continuous observation-to-hypothesis loop, bounded parallelism, diminishing-return/portfolio budget stops and human approval wait.
- Acceptance: autonomous loop cannot exceed campaign/company authority or move alias; approved proposal is exact immutable input to catalog activation.

### CP-04 — Catalog, release and alias authority

- Depends: CP-00, BUNDLE-00, QUAL-00.
- Owns: model definitions/endpoints/releases/aliases/qualification activation domain and projection.
- Build: immutable digest calculation, direct endpoint membership, owned bundle link, stable/canary alias generation, deterministic basis points and rollback.
- Acceptance: no activation without scope-valid qualification; in-flight admitted digest remains fixed; rollback projection meets target and never reprices prior reservation.

## 12. Distribution packets

### DIST-00 — Customer gateway recipes and compatibility harness

- Depends: GW-03/04/05, INT-00.
- Owns: version-pinned LiteLLM/Cloudflare/Portkey/Helicone/Vercel recipes and black-box harness fixtures.
- Build: base URL/key/model configuration, supported protocol table, streaming/error/cancel tests and troubleshooting docs.
- Must not: add these products as runtime dependencies or claim unsupported Chat/Embeddings behavior.
- Acceptance: each supported recipe runs against fake/staging Grad using a workspace key and reconciles like direct traffic.

### DIST-01 — Channel principal, exposure and accounting

- Depends: BILL-00, BILL-02, CP-04.
- Owns: channel domain/control routes, Valkey channel keyspace/scripts, immutable channel usage and statement primitive.
- Build: channel/credential/catalog/status, exposure/outstanding/concurrency reserve-settle, `channel_usage_records`, channel-priced release and contract-defined statement evidence.
- Acceptance: organization/channel keys and ledgers cannot cross by type or generated sequence; exposure never exceeds limit; channel request has no downstream Grad user assumption.

### DIST-02 — OpenRouter native provider integration

- Depends: DIST-01, QUAL-00.
- Owns: OpenRouter profile/adapter/onboarding artifacts and protected partner harness.
- Build: catalog mapping, auth, request/stream/error/usage compatibility, data policy, health/readiness, pricing/statement reconciliation and operational contacts.
- Acceptance: signed commercial/security gate plus conformance and bounded live traffic; requests enter the public gateway with channel credential and never bypass admission.

## 13. Infrastructure packets

### INFRA-00 — Terraform/Terragrunt bootstrap

- Depends: FND-00.
- Owns: `infra/bootstrap/**`, module/live scaffolding, state policy and infra CI wrappers.
- Build: four-account assumptions, versioned KMS S3 state/native locks, OIDC bootstrap roles, shallow Terragrunt units and policy checks.
- Acceptance: isolated bootstrap rehearsal, concurrent lock test, no secret/state/plan artifact committed; destructive plan needs protected approval.

### INFRA-01 — Network, DNS and edge

- Depends: INFRA-00.
- Owns: VPC/subnet/endpoints/NAT/DNS/ACM/WAF/CloudFront/ALB modules/live units.
- Build: three AZs, public managed-edge only, private app and isolated data subnets, separate control/gateway ALBs, static private-S3 origin and streaming timeouts.
- Acceptance: reachability matrix and policy tests prove forbidden east-west/egress paths; WAF/body/rate limits do not corrupt supported streams.

### INFRA-02 — Managed data, identity and artifact services

- Depends: INFRA-01.
- Owns: Aurora, RDS Proxy/pooling if selected, Valkey qualification config, S3/ECR, KMS, Secrets Manager, SES and backup modules.
- Build: Multi-AZ/PITR, purpose buckets/keys/roles, noeviction/protected headroom, lifecycle/versioning, verified SES identity/domain/DKIM and least-privilege send role.
- Acceptance: Aurora restore, S3 encrypt/delete, IAM least privilege and Valkey Lua/Streams/acknowledged-write/failover/load qualification. If Valkey fails, invoke ADR fallback test; do not weaken reserve invariant.

### INFRA-04 — EKS, Argo, charts and autoscaling

- Depends: INFRA-01, INFRA-02.
- Owns: EKS modules, Argo bootstrap, Helm charts, GitOps applications, KEDA and Kyverno policies.
- Build: private EKS, stable system capacity, qualified EKS Auto Mode app capacity with managed-group fallback, Pod Identity, PDB/topology/NetworkPolicy/security context, role-specific charts and CloudWatch logs/metrics/adapters used by KEDA and slow-path fleet planning.
- Acceptance: Helm/schema/kubeconform/policy/Kind upgrade tests, AZ/node/pod loss, KEDA fallback/floor/max behavior and full EKS rebuild without etcd product-state recovery.

### INFRA-05 — Research platform services

- Depends: INFRA-04, RF-01.
- Owns: Temporal chart/config/database role/backups and conditional Kueue/JobSet installation.
- Build: pinned Temporal services on EKS against separate Aurora DB/role with PostgreSQL visibility; research task queues and quota policies.
- Acceptance: workflow replay/cancel/backup/restore; Kueue/JobSet installed only with consuming distributed Kubernetes job; serving IAM/network remains unreachable.

## 14. CI, security and operations packets

### OPS-00 — CI, supply chain and immutable releases

- Depends: FND-00/01/03, INFRA-00.
- Owns: GitHub workflows, reusable verification, build/SBOM/provenance/signing and ECR/GitOps promotion automation.
- Build: path-aware but dependency-correct jobs, untrusted/protected separation, OIDC, build-once digest and generated drift.
- Acceptance: fork simulation has no secret/cloud mutation; tampered generated/image/provenance artifact fails; direct-main commit reruns exact checks before deploy.

### OPS-01 — Metrics, dashboards and alerts

- Depends: deployed application packets and INFRA-04.
- Owns: bounded metric definitions, dashboards, alerts and operator query views.
- Build: gateway/admission/billing/trace/control/fleet/cell/research/platform golden signals; SLO burn/lag/capacity/cost and invariant alerts.
- Acceptance: synthetic fault triggers expected alert with owner/runbook; cardinality/secret scans pass; no alert relies on plaintext payload.

### OPS-02 — Security controls and threat verification

- Depends: API-03, GW-06, TRACE-02, INFRA-03/04.
- Owns: threat model, IAM/network/secret/credential/certificate tests and break-glass procedure.
- Build: role matrix, egress deny, secret rotation, API/channel key response, cell compromise containment and supply-chain policy.
- Acceptance: automated negative reachability matrix; key/session/OAuth/provider/cell certificate rotation drills; trace decrypt and release authority separation.

### OPS-03 — Recovery and incident runbooks

- Depends: BILL-03, CP-03, TRACE-02, FLEET-02, INFRA-02/04/05.
- Owns: current runbooks, drill scripts and evidence template.
- Build: Valkey uncertain write/rebuild, ledger mismatch, Aurora restore, stream poison/lag, Stripe outage, trace/KMS incident, bad release, EKS loss, Temporal loss, provider orphan and organization deletion block.
- Acceptance: staging game days record detection/containment/reconciliation/recovery times and create issues for misses; financial repairs are append-only/dry-run diffable.

## 15. Launch packets

### LAUNCH-00 — Product and accessibility acceptance

- Depends: WEB-03, INT-00, DIST-00.
- Owns: end-user journey scripts and launch review report.
- Verify: five-minute onboarding, exact model selection, clear prices/errors/data policy, mobile/keyboard/accessibility, complete self-service deletion, and published pricing/status/support/security/Terms/Privacy/Acceptable Use surfaces.
- Gate: no founder-local action required; CI/staging video/screenshots contain synthetic data only.

### LAUNCH-01 — Financial and protocol qualification

- Depends: BILL-03, GW-06, TRACE-02.
- Verify: bounded/deep PBT, official client fake/real tests, provider malformed streams, reserve/settle/reconcile, failover and restore.
- Gate: accounting chart/legal review and measured no-unreserved-dispatch evidence.

### LAUNCH-02 — Owned inference and research qualification

- Depends: RF-04, CP-04, CELL-02, FLEET-02, INFRA-03.
- Verify: exact bundle from experiment through qualification/release, one single- and one multi-node topology, interruption/member loss/cache isolation/orphan cleanup, SLO/margin.
- Gate: human release approval and no qualification transfer across model/hardware/provider/topology.

### LAUNCH-03 — Production readiness and go-live

- Depends: LAUNCH-00/01/02 as applicable to launched surfaces, OPS-00/01/02/03.
- Owns: launch checklist, risk register, rollback pointers, on-call ownership and production promotion evidence.
- Direct paid launch may omit public owned/distribution gates but must hide those catalog entries. Public Grad/OpenRouter launch requires all gates.
- Acceptance: protected approval, immutable digests, budgets/quotas, backups/drills, dashboards/alerts/runbooks, public incident/support ownership, jurisdiction/tax/accounting/provider-term review and a rehearsed rollback.

## 16. Integration ownership matrix

| Integration seam | Producer owner | Consumer owner | Required shared test |
| --- | --- | --- | --- |
| Zod/OpenAPI -> web | API-00 | WEB-00 | generated-client black box |
| Zod/OpenAPI -> MCP | API-00 | API-03 | allowlist/authorization conformance |
| PostgreSQL -> Valkey snapshots | CP/BILL/CP-04 | GW-01/BILL-02 | monotonic projection goldens |
| gateway -> billing events | BILL-02/GW-02 | BILL-03 | crash/redelivery state model |
| gateway -> trace envelope | TRACE-00 | TRACE-01 | encrypted cross-language golden |
| gateway -> inference router | GW-02 | IR-00 | bidirectional stream/cancel/error fixture |
| router -> cell | IR-00 | CELL-00 | identity/attestation/churn suite |
| fleet -> provider | FLEET-01 | FLEET-02 | provider contract/orphan suite |
| research -> bundle | RF-03 | BUNDLE-00 | canonical digest/rebuild suite |
| qualification -> catalog | QUAL-00 | CP-04 | scope/expiry/signature activation suite |
| channel -> gateway | DIST-01 | GW-01/02 | disjoint principal/account state model |
| Terraform -> Argo | INFRA-00/04 | OPS-00 | bootstrap/rebuild and ownership test |
