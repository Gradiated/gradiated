# Product architecture contract

This file is the durable entry point for product architecture. Product source lives under the product workstream directory (currently `product/` when present); this document records boundaries and points to the decisions that explain them.

## Rules for coherent parallel work

- Every product change starts from a GitHub Issue with an explicit user outcome and acceptance check.
- One agent owns a directory or interface at a time. Split work by module or artifact before parallelizing.
- Public interfaces, schemas, persistence formats, and cross-service contracts require a decision record in `docs/decisions/` before implementation or in the same commit.
- Prefer a small number of stable interfaces over agent-specific wrappers or duplicated abstractions.
- Keep product code, tests, fixtures, prompts, and operational runbooks in the repository. Keep only credentials and private runtime state outside it.
- A change is not complete until its tests, migration/rollback path, limitations, and handoff are recorded.

## Decision record process

Use [`docs/decisions/TEMPLATE.md`](decisions/TEMPLATE.md) for decisions that affect architecture, data, APIs, model/provider boundaries, security, or operations. Record rejected alternatives and a reversal trigger; this prevents later agents from reopening settled questions without new evidence.

Research results inform architecture only through a linked, scope-matched artifact. Label whether the evidence is measured, analytical, vendor-reported, derived, inferred, or synthetic.

## Founder and implementation entry points

Read [the complete startup architecture](STARTUP_ARCHITECTURE.md) first, then [the simplicity review](SIMPLICITY_REVIEW.md) for the dependency budget and minimal persistent model. Use [the implementation coverage ledger](IMPLEMENTATION_COVERAGE.md) to verify capability ownership. These documents are the current architecture freeze; dated audits remain evidence of how the design evolved.

## Current architecture map

Keep this map short and update it when a product boundary changes:

| Area | Canonical location | Contract / owner |
| --- | --- | --- |
| Product source | `product/` | Product workstream issue and local instructions |
| Startup-wide architecture | `docs/STARTUP_ARCHITECTURE.md` | Founder narrative, planes, journeys, authority map and seed sequence |
| Completeness and contradictions | `docs/IMPLEMENTATION_COVERAGE.md` | Coverage matrix, simplifications, validation gates and blueprint map |
| Complexity budget/minimal model | `docs/SIMPLICITY_REVIEW.md` | Dependency decisions, reduced contracts, required fields and reintroduction triggers |
| Inference product boundary | `product/docs/` | [ADR-0002](decisions/0002-opinionated-inference-product.md), [feature decisions](../product/docs/OPENROUTER_FEATURE_DECISIONS.md), and product delivery packages |
| AWS infrastructure | `infra/` | [`infra/README.md`](../infra/README.md), [ADR-0001](decisions/0001-aws-eks-platform.md), and infrastructure issue/package |
| Shared agent procedures | `.agents/skills/` | Root `AGENTS.md` and skill contracts |
| Research workstreams | `research/` | [`research/README.md`](../research/README.md) |
| Execution packets | `tasks/` | GitHub Issue + packet lifecycle |
| GitHub automation | `tools/github/` | [`docs/GITHUB_OPERATING_SYSTEM.md`](GITHUB_OPERATING_SYSTEM.md) |
| Runtime/browser tooling | `tools/browser/` and `.agents/runtime/` | Browser safety contract |

## Current runtime boundary

The Vite console is static S3/CloudFront. Hono control roles, the Rust gateway/inference router/fleet processes and Python research roles run on private EKS. Aurora PostgreSQL owns financial, configuration, release, authorization, trace metadata, capacity allocation and research domain state; private S3/ECR store encrypted traces and immutable model/runtime artifacts. PostgreSQL indexed views provide seed product analytics. Temporal owns resumable research execution only. Qualification-gated Valkey is the gateway's only synchronous internal state/control dependency; curated model APIs and the inference router are serving dependencies. Owned `grad/<effort>/<speed>` traffic reaches isolated external-provider GPU cells. Rust provider drivers reconcile PostgreSQL allocation rows directly; custom fleet CRDs and ClickHouse are not seed dependencies. Kubernetes never owns business state or enters request routing. Always-on tenant-salted KV/prefix cache—including for no-retention—remains ephemeral cell state. Current subtraction decisions are in [the simplicity review](SIMPLICITY_REVIEW.md); older ADRs remain historical rationale where superseded.
