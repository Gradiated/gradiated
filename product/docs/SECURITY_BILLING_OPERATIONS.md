# Security and operations

Billing algorithms are specified in [Billing and Redis](BILLING_AND_REDIS.md); this document covers the surrounding security and operational controls.

## Security boundaries

- Browser to Hono: secure, HttpOnly, SameSite session cookies; CSRF protection for cookie-authenticated mutation; strict CORS to the console origin.
- Hono to PostgreSQL/Redis/Stripe: private networking where available, TLS, least-privilege credentials, rotation, and explicit timeouts.
- Client to gateway: TLS, bounded body/header/time, hashed API-key lookup, rate/concurrency limits, no query credentials.
- Gateway to provider: egress allowlist, DNS/SSRF controls, TLS verification, encrypted provider credentials, strict redirects disabled.
- Worker: separate credentials for PostgreSQL posting, Redis projection, Stripe operations, and alerting.

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

Default request records contain IDs, protocol/model, unit counts, timing, status, and financial evidence—not prompts, messages, tool arguments, generated content, authorization headers, or provider keys. Debug capture requires explicit workspace opt-in, short TTL, encryption, field redaction, region policy, and an audit event. Seed should ship with payload capture disabled.

Logs use structured allowlists. Hashing response content for CI is permitted only for fixed synthetic prompts and not customer traffic. Traces propagate opaque request/attempt IDs. Error text is scrubbed before customer exposure and telemetry.

## Limits and abuse controls

At the edge enforce body/header limits, connection limits, request timeout, API-key RPM/TPM, organization low-credit concurrency, workspace/key period and concurrency limits, effective model/provider allowlists, maximum output/reserve, and bounded retries. Cost-bearing limits use one Redis atomic transition. Network/IP signals may supplement but never replace organization/workspace/key controls.

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

## Observability

Dashboards and alerts cover:

- requests, success/terminal state, provider attempts, time to first byte, duration, cancellations;
- admitted/rejected by reason, organization spendable/reserved aggregate, organization/workspace/key caps and windows, reservation age, overages;
- Redis latency/errors/failover/memory/evictions/AOF/replication and stream length/pending/oldest age;
- worker consumption, duplicates, poison events, PostgreSQL posting lag, projection version lag;
- top-up webhook verification/duplicates/latency/failures, refunds/chargebacks;
- ledger imbalance (must be impossible by constraint), materialized-balance mismatch, reconciliation delta/closed workspaces;
- provider spend, customer sell amount, gross margin, real-CI daily/monthly cost.

Metrics must avoid unbounded workspace/request labels. Detailed tenant lookup belongs in protected operational views.

## Runbooks

Ship and exercise runbooks for:

- Redis unavailable/failover/acknowledged-write loss;
- reservation lease orphan and settlement uncertainty;
- stream consumer lag, pending-entry recovery, poison event, retention pressure;
- PostgreSQL outage and outbox backlog;
- Stripe webhook outage, duplicated/conflicting event, refund, chargeback;
- price-book/config rollback and reserve-underestimation incident;
- organization/workspace/key suspension, key leak, abuse burst;
- provider outage/malformed stream and bounded failover;
- projection rebuild and reconciliation mismatch;
- secret rotation and suspected data exposure.

Every financial repair is append-only, idempotent, attributable to an operator/incident, and dry-run diffable. Destructive Redis rebuild requires the fenced procedure in `BILLING_AND_REDIS.md`.

## CI and secrets

GitHub environments separate untrusted PR checks, staging, and `provider-e2e`. Protected provider smoke requires reviewed workflow code and environment secrets. Fork PRs receive no credentials. Configure provider-side hard budget/rate limits in addition to the workflow preflight. The complete CI/replay contract is in [Testing and CI](TESTING_AND_CI.md).

The owner is not expected to run checks locally. A merge is permitted only when required CI reports generated-contract sync, TS/Rust verification, bounded PBT, fake official-client E2E, and relevant integration tests. Paid real-provider smoke is required on main/release according to the protected workflow, not on untrusted PRs.
