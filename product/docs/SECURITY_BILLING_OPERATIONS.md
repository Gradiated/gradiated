# Security and operations

Billing algorithms are specified in [Billing and Redis](BILLING_AND_REDIS.md); this document covers the surrounding security and operational controls.

## Security boundaries

- Browser to Hono: secure, HttpOnly, SameSite session cookies; CSRF protection for cookie-authenticated mutation; strict CORS to the console origin.
- Hono to PostgreSQL/Redis/Stripe: private networking where available, TLS, least-privilege credentials, rotation, and explicit timeouts.
- Client to gateway: TLS, bounded body/header/time, hashed API-key lookup, rate/concurrency limits, no query credentials.
- Gateway to provider: egress allowlist, DNS/SSRF controls, TLS verification, encrypted provider credentials, strict redirects disabled.
- Worker: separate credentials for PostgreSQL posting, Redis projection, Stripe operations, and alerting.
- Trace/recommendation worker: separate Redis consumer, private trace S3 and KMS decrypt permissions; no payment or provider-secret authority.
- Trace-analytics projector/query path: content-free PostgreSQL outbox to ClickHouse insert role and Hono-only read role; no raw-payload decrypt, ledger mutation, provider secret or browser credential authority.

API-key format includes a non-secret environment/prefix and high-entropy secret. Each key is bound to one organization/workspace. Store an HMAC/keyed digest with a rotatable server pepper, never a recoverable raw key. Display the raw value once. Key revocation projects urgently to Redis and has an SLO below 30 seconds; gateway can require fresher projection for risk events.

## Authorization

Organization roles:

- owner: organization ownership, billing, all workspaces, closure;
- admin: organization members/policy and all workspace administration except ownership/billing methods;
- billing: top-ups, receipts, credit and billing settings, no inference secrets by default;
- member: only assigned/default workspaces.

Workspace roles are admin, developer, and viewer. Organization admins have administrative access to every workspace; other users require `workspace_membership`. Every organization member has Default-workspace access in seed.

All checks require organization membership and, when scoped below it, workspace membership in the domain/database query shape. Better Auth proves user/session identity only. Sensitive operations require recent authentication, audit event, and idempotency token. PBT generates arbitrary role/membership transitions and cross-organization/workspace IDs.

## Payment security

- Use Stripe-hosted Checkout for seed to reduce card-data scope; no card details touch our systems.
- Verify webhook signature against raw body, enforce timestamp tolerance, and store safe event identifiers.
- Bind Checkout Session/payment intent to immutable organization/top-up IDs and validate amount/currency server-side.
- Return generic status to browser; never accept balance-changing fields from redirect/query parameters.
- Restrict top-up denominations and velocity until fraud evidence supports broader limits.
- Chargebacks/refunds immediately lower projected spend and can suspend the organization and all workspaces.
- Reconcile Stripe settlement reports to clearing ledger as a separate finance job; inference reconciliation does not replace payment reconciliation.

## Privacy and data handling

### Product Intelligence — default

The default workspace mode retains bounded request, response and tool traces for customer-facing history, workload analytics, evaluations and Grad migration recommendations. Initial raw retention targets 30 days and is configurable downward; final defaults require launch legal/security review. Retention is visible during onboarding and in Settings—not buried as an inference from terms.

The gateway always removes authorization/provider keys, cookies and non-allowlisted headers before capture. It encrypts a bounded trace to the current public ingest key before appending ciphertext to Redis. The worker stores ciphertext in a private, versioned S3 bucket with KMS-backed decrypt roles and lifecycle deadlines. PostgreSQL stores authorization, metadata, object reference and wrapped-key/tombstone state only. ClickHouse stores a content-free analytical projection of typed dimensions, copied usage/cost/timing facts, workload/evaluation features and aggregates. Raw payload never appears in ClickHouse, ordinary application logs, metrics, telemetry traces, billing streams, PostgreSQL rows, support exports or CI artifacts.

Files and oversized content are omitted or safely summarized with an explicit capture status. Customers can inspect, export and delete retained traces. Deletion atomically writes an audited PostgreSQL tombstone, revokes grants and destroys/revokes the per-trace wrapped key before asynchronous all-version S3 and ClickHouse cleanup. APIs filter tombstones/expiry while ClickHouse merge-based deletion converges; restored analytics replay the tombstone ledger before reads. S3 and managed ClickHouse backup residual windows are disclosed. A retention deadline miss is an incident and can disable new Product Intelligence capture for the affected scope.

Retention for customer features does not authorize training or global model improvement on customer content. That use requires a separate explicit opt-in, terms, isolation and ADR. Provider training/data use is independently disallowed in the curated provider registry unless a future customer explicitly opts into a different contract.

### Private / No Retention — opt-in

A workspace may choose Private/No Retention and a request may tighten Product Intelligence with `x-grad-data-policy: no-retain`. The gateway then suppresses payload trace creation before Redis/S3 and keeps only minimum billing/security/aggregate metadata. That content-free usage row may project to ClickHouse with `payload_state=no_retain`, preserving cost/latency/model analytics without a payload action. Route eligibility requires an endpoint qualified for the no-retention policy. Content-based history, replay and migration recommendations are unavailable; metadata-only opportunities are labeled low confidence. A request can never loosen workspace policy.

No-retention is not a cache-disable mode. Generative Grad requests always use active and prefix KV cache in an opaque workspace/channel/release/retention-class namespace. Cache state is confidential, bounded, ephemeral, unavailable to product APIs, and excluded from traces, object storage, analytics, backups, logs and provider support bundles. Cells or cache tiers that cannot prove those controls are ineligible for no-retention traffic.

Unknown provider data policy is ineligible in either mode. Prompt caching is eligible only when its semantics match the selected policy. Hosted tools/search/processors have separate policies and cannot inherit a false no-retention claim.

### Trace access and abuse prevention

Trace reads require workspace membership and least-privilege role; export/delete and sensitive views require recent authentication. Hono is the only customer ClickHouse query surface and maps closed filters to parameterized organization/workspace/time-bounded queries with result/compute limits. Browsers never receive SQL or ClickHouse credentials. RBAC/row policies are defense in depth; server-side authorization remains mandatory.

For payload detail, the ordinary control API mints a signed, single-use internal grant bound to actor/workspace/trace/action/expiry. A separate trace-access service rechecks trace/tombstone/key state, decrypts one object, streams without caching and audits success/failure. It cannot list the bucket and never returns a reusable S3 URL. Support/operator views default to metadata and require time-bounded break-glass approval for payload. Workload fingerprints are HMAC-scoped per workspace; derived features cannot become cross-customer identifiers.

## Limits and abuse controls

At the edge enforce body/header/file/trace limits, connection limits, request timeout, API-key RPM/TPM, organization low-credit concurrency, workspace/key period and concurrency limits, curated provider/model or Grad effort/speed access, effective data/capability policy, maximum output/reserve, and bounded retries. Cost-bearing limits use one Redis atomic transition. Trace streams have separate byte/event quotas and can be shed before billing capacity. Network/IP signals may supplement but never replace tenant controls.

Failed-request credit is a trust feature and an abuse surface. Eligibility is based on a protocol-specific `usable_output_delivered` fact, terminal cause, cancellation ownership, correction history, and risk policy. The original usage and provider buy cost remain immutable; an idempotent compensating sell entry provides the credit. Repeated deliberate disconnects, malformed-request retries, or policy failures are not free inference and can restrict the organization pending review.

Publishing a route release requires separation between evidence generation and release approval in production, an immutable evidence/price manifest, an explicit rollback release, and an audit event. ModelOps credentials can qualify/propose but cannot read customer payloads or mutate organization credit. Recommendation processors may read authorized Product Intelligence traces and call owned evaluation capacity but cannot publish a release or switch customer traffic. Emergency rollback changes only the active release pointer and never reprices in-flight reservations.

Organization risk modes are operator-controlled and audited; workspaces/keys also have active/suspended status. Automatic organization triggers include chargeback, impossible metering, projection regression, unexplained reconciliation delta, stream retention risk, and coordinated key abuse. Suspension fails closed; reopening requires the documented reconciliation/review path.

## Service objectives

Initial objectives, refined by measured load tests:

| Surface | Objective |
| --- | --- |
| Gateway availability | 99.9% monthly excluding upstream provider failure. |
| Gateway p95 added latency | <25 ms regional, excluding provider time and client upload. |
| Redis admission success | 99.99% for healthy/funded workspaces; no unreserved dispatch. |
| Key/workspace suspension projection | p95 <10 s, hard objective <30 s. |
| Usage posting lag | p95 <30 s, p99 <2 min. |
| Top-up credit projection | p95 <30 s after verified webhook commit. |
| Reconciliation | continuous event checks; full workspace pass hourly; unexplained delta closes admission. |
| Recovery | PostgreSQL RPO <=5 min/RTO <=30 min; Redis acknowledged-write target RPO <=1 s with explicit reconciliation. |
| Direct model availability | 99.9% per published provider/model excluding provider-wide failure; never crosses provider identity. |
| Grad route availability | 99.9% per published effort/speed cell where qualified capacity exists; never silently downgrades speed. |
| Route rollback | halt new canary assignment within 2 min of a hard gate; stable-head rollback projection p95 <30 s. |
| Session stability | >=99.9% of eligible healthy-session requests remain on the pinned concrete model; all breaks carry a reason. |
| Trace capture | >=99.9% for eligible bounded Product Intelligence requests while preserving billing-stream headroom; skips are visible. |
| Trace analytics | settled request searchable in ClickHouse p95 <15 s; common bounded console query p95 <500 ms; zero cross-workspace rows. Targets remain unmeasured until I-07. |
| Retention/delete | 100% of trace objects receive lifecycle deadline; customer delete completes within published target and no missed deadline remains unpaged. |

## Observability

Dashboards and alerts cover:

- requests, success/terminal state, canonical provider/model or Grad effort/speed, actual release, attempts, time to first byte, duration, cancellations and failed-request credits;
- admitted/rejected by reason, organization spendable/reserved aggregate, organization/workspace/key caps and windows, reservation age, overages;
- Redis latency/errors/failover/memory/evictions/AOF/replication and stream length/pending/oldest age;
- worker consumption, duplicates, poison events, PostgreSQL posting lag, projection version lag;
- top-up webhook verification/duplicates/latency/failures, refunds/chargebacks;
- ledger imbalance (must be impossible by constraint), materialized-balance mismatch, reconciliation delta/closed workspaces;
- direct identity violations (must remain zero), Grad effort/speed cell SLO/capacity, route eligibility, session/canary, candidate health, release gate/rollback, provider spend, sell amount and margin;
- trace capture/skips/bytes/lag/headroom, encryption-key version, object write/decrypt failures, ClickHouse projection lag/query latency/scanned bytes/parts/mutations/cost, outbox deduplication/dead letters, retention/delete/export/tombstone backlog, workload profiles, recommendation evidence levels and experiment stop reasons.

Metrics must avoid unbounded workspace/request labels. Detailed tenant lookup belongs in protected operational views.

## Runbooks

Ship and exercise runbooks for:

- Redis unavailable/failover/acknowledged-write loss;
- reservation lease orphan and settlement uncertainty;
- stream consumer lag, pending-entry recovery, poison event, retention pressure;
- PostgreSQL outage and outbox backlog;
- Stripe webhook outage, duplicated/conflicting event, refund, chargeback;
- price-book/config rollback and reserve-underestimation incident;
- managed route release halt/rollback, qualification expiry, unexpected model change, privacy-policy mismatch, and session-pin break spike;
- trace stream backpressure, encryption-key expiry, object/KMS outage, accidental plaintext detection, unauthorized trace access, retention/delete deadline miss and export incident;
- ClickHouse/PrivateLink outage, projection divergence/rebuild, slow or abusive query, schema migration rollback, mutation backlog and restore-with-tombstones;
- incorrect migration recommendation, replay budget runaway, shadow/live-canary stop and proof that original traffic remains unchanged;
- organization/workspace/key suspension, key leak, abuse burst;
- provider outage/malformed stream and bounded failover;
- failed-request credit spike, duplicate correction, and deliberate-disconnect abuse;
- projection rebuild and reconciliation mismatch;
- secret rotation and suspected data exposure.

Every financial repair is append-only, idempotent, attributable to an operator/incident, and dry-run diffable. Destructive Redis rebuild requires the fenced procedure in `BILLING_AND_REDIS.md`.

## CI and secrets

GitHub environments separate untrusted PR checks, staging, and `provider-e2e`. Protected provider smoke requires reviewed workflow code and environment secrets. Fork PRs receive no credentials. Configure provider-side hard budget/rate limits in addition to the workflow preflight. The complete CI/replay contract is in [Testing and CI](TESTING_AND_CI.md).

The owner is not expected to run checks locally. A merge is permitted only when required CI reports generated-contract sync, TS/Rust verification, bounded PBT, fake official-client E2E, and relevant integration tests. Paid real-provider smoke is required on main/release according to the protected workflow, not on untrusted PRs.
