# ADR-0001: AWS EKS platform and durable gateway data tier

- status: accepted for implementation planning; production data tier remains qualification-gated
- GitHub issue: https://github.com/joshsny/gradiated/issues/2
- owner: infrastructure workstream
- date: 2026-07-13

## Decision

Host the seed product on account-isolated AWS environments. Run long-lived Rust gateway, Hono control API, workers, and platform controllers on private Amazon EKS. Serve the Vite application from private S3 through CloudFront. Use Aurora PostgreSQL Serverless v2 as the authoritative organization ledger/configuration database.

The gateway's only synchronous internal state/control dependency is a production Valkey tier; model APIs and the AWS inference edge are upstream serving dependencies. Start with node-based ElastiCache for Valkey 9 configured for synchronous durability, Multi-AZ, TLS, ACLs, and no eviction, but permit production only after scope-matched atomic command, failover, data-loss, memory-pressure, and latency tests pass. ElastiCache Serverless may be used for disposable environments; single-region MemoryDB is the fallback candidate if qualification fails.

Define AWS resources with Terraform modules and Terragrunt implicit stacks. Store versioned/KMS state in S3 with Terraform native lock files. Argo CD pulls pinned Helm releases into EKS. KEDA scales pods and Karpenter provisions bounded node pools. GitHub Actions authenticates through OIDC and applies development automatically after direct-to-main checks; staging/production are protected promotions.

Locally, Docker Compose provides dependencies, mprocs/dekit runs source processes, and a Rust `grad` CLI exposes reproducible workflows.

## Context and constraints

The product handles prepaid organization credit. PostgreSQL is authoritative, but the gateway cannot query it on the request path. Admission must atomically authenticate, reserve worst-case credit/limits/concurrency, create a lease, and append an idempotent event before calling a provider. Losing an acknowledged Valkey reservation can create uncompensated spend, so ordinary cache durability is inadequate.

The user selected AWS, Kubernetes, Terraform, Helm, KEDA, S3 state, Docker Compose, mprocs, and a custom CLI. The system must be operable by delegated agents and CI because the owner will not run it locally.

## Alternatives considered

1. **Chosen: EKS + Aurora + qualified durable node-based Valkey.** Matches required Kubernetes control, isolates the streaming gateway, and has an AWS-documented synchronous durability path subject to proof.
2. **ECS/Fargate or App Runner.** Lower seed operational surface, but conflicts with the requested Kubernetes/Helm/KEDA platform and provides less shared control for the gateway/worker topology. Reconsider if EKS delays revenue materially.
3. **ElastiCache Serverless everywhere.** Excellent operational simplicity and supports needed Lua/Streams commands, but reviewed documentation does not establish the same acknowledged-write durability needed for financial reservations.
4. **MemoryDB as first choice.** Has a durable transaction log and remains the fallback. Node-based ElastiCache Valkey 9 now documents synchronous durability and keeps the selected ElastiCache operating model; both still require command/failover/latency evidence.
5. **Terraform without Terragrunt.** Viable at small scale, but repeated account/environment units and dependency ordering would create more wrapper scripting in `grad`/CI.
6. **CI pushes directly to Kubernetes.** Avoided because private clusters and pull-based GitOps reduce inbound access and make desired state/rollback reviewable.

## Consequences

- positive: environment/account blast-radius isolation; reproducible modules/charts; no long-lived AWS CI keys; independent gateway/control ingress; explicit pod/node scaling; local and CI command parity.
- negative: EKS and multi-environment managed data have meaningful fixed cost and operational complexity; private bootstrap/recovery needs a VPC-capable path; one primary region limits seed disaster recovery; production Valkey blocks on a paid qualification campaign.
- migration or rollback: application releases revert Git digests with backward-compatible schemas; Terraform is forward-fixed, not state-rewound. If Valkey qualification fails, test single-region MemoryDB under the same invariant. If EKS cost/lead time violates the revenue gate, write a superseding ADR for ECS while preserving containers/contracts/data services.

## Evidence

- [Dated AWS platform decision brief](../../infra/evidence/AWS_PLATFORM_DECISION_2026-07-13.md) — vendor-reported facts plus analytical conclusions.
- [Infrastructure architecture](../../infra/README.md) — proposed design.
- [Billing/Redis product contract](../../product/docs/BILLING_AND_REDIS.md) — product invariant and failure behavior.

No managed-service behavior in this ADR is measured yet. The implementation plan explicitly separates official vendor claims from qualification gates.

## Reversal trigger

Revisit if the exact Valkey configuration loses an acknowledged reservation/event, cannot support atomic scripts/Streams within latency, is unavailable in the selected region, or exceeds the unit-economics budget; if customer residency requires multiple active regions; or if EKS implementation/operating cost delays the first paid vertical slice beyond an approved revenue milestone.
