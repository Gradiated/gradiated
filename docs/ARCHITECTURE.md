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

## Current architecture map

Keep this map short and update it when a product boundary changes:

| Area | Canonical location | Contract / owner |
| --- | --- | --- |
| Product source | `product/` | Product workstream issue and local instructions |
| Inference product boundary | `product/docs/` | [ADR-0002](decisions/0002-opinionated-inference-product.md), [feature decisions](../product/docs/OPENROUTER_FEATURE_DECISIONS.md), and product delivery packages |
| AWS infrastructure | `infra/` | [`infra/README.md`](../infra/README.md), [ADR-0001](decisions/0001-aws-eks-platform.md), and infrastructure issue/package |
| Shared agent procedures | `.agents/skills/` | Root `AGENTS.md` and skill contracts |
| Research workstreams | `research/` | [`research/README.md`](../research/README.md) |
| Execution packets | `tasks/` | GitHub Issue + packet lifecycle |
| GitHub automation | `tools/github/` | [`docs/GITHUB_OPERATING_SYSTEM.md`](GITHUB_OPERATING_SYSTEM.md) |
| Runtime/browser tooling | `tools/browser/` and `.agents/runtime/` | Browser safety contract |

## Current runtime boundary

The Vite console is static S3/CloudFront. Hono control services, Rust gateway and inference edge, financial/trace/analytics/recommendation workers, ModelOps/fleet jobs, and platform controllers run on private EKS. Aurora PostgreSQL owns financial/configuration/release/authorization/desired-capacity/lease-history/trace-registry authority; private S3 stores encrypted retained payloads and signed model artifacts; ClickHouse Cloud is a content-free replayable trace-analytics projection reached through PrivateLink. Qualification-gated durable Valkey is the gateway's only synchronous internal state/control dependency; curated model APIs and the inference edge are upstream serving dependencies. Curated direct traffic goes to its exact model provider. Owned `grad/<effort>/<speed>` traffic goes through the AWS inference edge to isolated external-capacity-provider GPU cells selected from signed Redis route releases. Grad CRDs/controllers in AWS EKS reconcile native APIs or managed-Kubernetes cells without fake Nodes or a cluster spanning providers; Kubernetes never owns business state or enters request routing. Always-on tenant-salted KV/prefix cache—including for no-retention—remains ephemeral cell state. Platform details are in [ADR-0001](decisions/0001-aws-eks-platform.md); model/data boundaries are in [ADR-0003](decisions/0003-provider-grad-effort-speed-and-traces.md) and [ADR-0004](decisions/0004-clickhouse-trace-analytics.md); external serving and actuation are fixed by [ADR-0005](decisions/0005-multi-provider-spot-inference.md) and [ADR-0006](decisions/0006-kubernetes-provider-abstraction.md).
