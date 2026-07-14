# Task: 2026-07-14-architecture-simplicity

## Outcome

The architecture has a documented complexity budget and a smaller canonical design. Every runtime, build and stateful dependency; deployable boundary; cross-language contract; and persistent model/field is classified keep, combine, defer or remove. Canonical plans are reconciled so junior agents implement the reduced system rather than the superseded complete-but-overbuilt design.

<What will be true when this is done?>

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/14
- GitHub project:
- owner: root
- Codex thread:
- created: 2026-07-14T10:13:06+00:00
- started: 2026-07-14T10:13:06+00:00
- last updated: 2026-07-14T12:54:04+02:00
- scope: docs/SIMPLICITY_REVIEW.md,docs/STARTUP_ARCHITECTURE.md,docs/IMPLEMENTATION_COVERAGE.md,docs/ARCHITECTURE.md,docs/CONTEXT_INDEX.md,docs/decisions/0001-aws-eks-platform.md,docs/decisions/0004-clickhouse-trace-analytics.md,docs/decisions/0005-multi-provider-spot-inference.md,docs/decisions/0006-kubernetes-provider-abstraction.md,product/AGENTS.md,product/README.md,product/HANDOFF.md,product/docs/ARCHITECTURE.md,product/docs/API_AND_DATA_CONTRACTS.md,product/docs/CONTROL_PLANE_IMPLEMENTATION.md,product/docs/GATEWAY_IMPLEMENTATION.md,product/docs/OWNED_INFERENCE_IMPLEMENTATION.md,product/docs/RESEARCH_FACTORY_IMPLEMENTATION.md,product/docs/DISTRIBUTION_IMPLEMENTATION.md,product/docs/DELIVERY_PLAN.md,product/docs/PRODUCT_SPEC.md,product/docs/TESTING_AND_CI.md,product/docs/EVIDENCE_AND_DECISIONS.md,product/docs/MODEL_LANES_AND_MIGRATION.md,product/docs/OWNED_INFERENCE_ARCHITECTURE.md,product/docs/SECURITY_BILLING_OPERATIONS.md,product/docs/INTEGRATIONS.md,infra/AGENTS.md,infra/README.md,infra/HANDOFF.md,infra/docs/PLATFORM_IMPLEMENTATION.md,infra/docs/CLOUD_ARCHITECTURE.md,infra/docs/KUBERNETES_AND_HELM.md,infra/docs/TERRAFORM_AND_ENVIRONMENTS.md,infra/docs/AUTOSCALING_AND_CAPACITY.md,infra/docs/MULTI_PROVIDER_GPU_FLEET.md,infra/docs/CI_CD_AND_RELEASES.md,infra/docs/LOCAL_DEVELOPMENT.md,infra/docs/SECURITY_OPERATIONS_DR.md,infra/docs/DELIVERY_PLAN.md,tasks/done/2026-07-14-architecture-simplicity.md
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value: Removing redundant projections, workflow engines, custom control resources, generic envelopes and speculative model entities will reduce implementation and operational failure modes without reducing billing correctness, security, compatibility, trace usefulness, owned-inference quality or research velocity.
- acceptance checks: inventory all dependencies and stateful systems; inventory persistent/core models and fields; apply explicit necessity tests; publish keep/combine/defer/remove decisions and estimated boundary reduction; preserve user-mandated Vite/Hono/tRPC, Rust gateway, PostgreSQL billing authority, Redis-only gateway state dependency, workspaces, top-ups, external GPU abstraction, trace retention choice, KV cache and router distribution; reconcile every canonical blueprint/delivery/handoff; validate links and stale terms.
- quality gate: analytical claims labeled and falsifiable; unstable retained vendor/platform claims checked against primary docs; `python3 tools/devex/check.py`; Markdown-link validation; terminology/dependency searches; `git diff --check`; no edits/staging under active research paths.
- SLO or budget: Markdown only, zero external spend, no cloud/provider mutation; default to removal when a dependency or field has no correctness/security/customer/evolution justification.
- timeout: one architecture session; measured choices become explicit triggers rather than launch dependencies.
- artifact locations: `docs/SIMPLICITY_REVIEW.md`, reconciled startup/product/infra blueprints and this packet.
- resume command: `git show --stat --oneline HEAD`
- rollback or cleanup: revert only the architecture-simplicity documentation commit; no external resources are created.

## Plan

1. Inventory and score all dependencies, stateful systems, deployables, contracts, models and fields.
2. Freeze removal/defer/combine decisions and the irreducible product-quality core.
3. Rewrite canonical blueprints and delivery order around the reduced system.
4. Verify, publish directly to main and close issue #14.

## Result

- status: done
- verification: `python3 tools/devex/check.py` passed; `git diff --check` passed; all local Markdown links in 41 changed/current files resolved; scope audit found 41 owned changed paths and zero unclaimed/missing paths; terminology searches found no current canonical ClickHouse/CRD/target-projector/custom-period contradictions.
- changed paths: the exact 41-path list is the `scope` field above; unrelated `.agents/skills/**` and `research/sol/**` work was preserved and excluded.
- limitations or blocked paths: architecture is planning, not measured deployment evidence. EKS Auto Mode, Aurora-backed Temporal, Valkey durability, AWS Private CA enrollment, provider economics, PostgreSQL analytics capacity and all numeric scaling/SLO values retain explicit staging/benchmark gates.
- commit: this scoped documentation commit; hash recorded in Git history after publication.
- next action: delegate WP-00/I-00, then build the WP-01–04 paid direct-model vertical before owned inference or native channel work.
- released: 2026-07-14T10:54:43+00:00
