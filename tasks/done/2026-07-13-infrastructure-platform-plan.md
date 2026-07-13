# Task: 2026-07-13-infrastructure-platform-plan

## Outcome

The repository contains a detailed, source-backed, implementation-ready infrastructure contract for AWS, EKS, Terraform/Terragrunt, Helm/GitOps, pod/node autoscaling, managed data services, CI/CD, local orchestration, and the `grad` developer CLI.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/2
- GitHub project: unavailable to the current fine-grained token; human-managed until Project access exists
- owner: Codex
- Codex thread: current infrastructure planning thread
- created: 2026-07-13T16:12:22+00:00
- started: 2026-07-13T16:12:22+00:00
- last updated: 2026-07-13T16:29:07+00:00
- scope: infra,product/docs,product/HANDOFF.md,product/README.md,docs/ARCHITECTURE.md,docs/CONTEXT_INDEX.md,docs/decisions
- excluded paths: `research/**`, existing product application implementation, live AWS accounts/resources, credentials
- dependencies: committed product architecture `af06af9`

## Contract

- hypothesis or user value: a contract-first AWS/Kubernetes platform with CI-verifiable IaC and a single `grad` command surface lets parallel agents build the product without environment drift or depending on the owner to run local checks.
- acceptance checks: account/environment topology; S3 state/bootstrap/locking/recovery; Terraform/Terragrunt layout and checks; EKS/network/data/edge/observability; Helm/GitOps; KEDA/Karpenter signals and safety floors; Docker Compose/mprocs; `grad` CLI behavior; security/DR/cost controls; implementation work packages.
- quality gate: decisions use current official sources, distinguish vendor claims from proposed design, preserve product billing/gateway invariants, specify failures and rollback, and expose CI/agent verification commands.
- SLO or budget: $0 external spend; planning-only; no AWS mutation. Planned serving SLOs inherit the product spec and infra recovery objectives are explicit.
- timeout: one planning turn; stop only after the end-to-end plan and handoff are internally consistent.
- artifact locations: `infra/**`, `docs/decisions/0001-aws-eks-platform.md`, `docs/ARCHITECTURE.md`, `docs/CONTEXT_INDEX.md`, `product/README.md`, `product/HANDOFF.md`, `product/docs/DELIVERY_PLAN.md`, this packet.
- resume command: `python3 tools/devex/start.py && sed -n '1,260p' infra/README.md && sed -n '1,300p' infra/docs/DELIVERY_PLAN.md`.
- rollback or cleanup: remove only the new infrastructure planning files and owned cross-references; preserve all research changes and committed product architecture.

## Plan

1. Verify current AWS, Kubernetes, Terraform/Terragrunt, Helm, KEDA/Karpenter, and local-tool constraints from primary sources.
2. Define cloud topology, data durability, environment/state structure, deployment/autoscaling, security/operations, local DX, and `grad` contracts.
3. Write delegation packages, cross-agent ADR/index links, validate consistency, update handoff, and release the task.

## Result

- status: complete; ready for packet release and commit
- verification: `git diff --check` passed; `python3 tools/devex/check.py` passed; a repository-relative Markdown link check covered 24 files and passed. Infrastructure execution commands are contracts for later work and do not exist yet, so no Terraform, Helm, Compose, Kubernetes, AWS, or `grad` execution is claimed.
- changed paths: `infra/**`, `docs/ARCHITECTURE.md`, `docs/CONTEXT_INDEX.md`, `docs/decisions/0001-aws-eks-platform.md`, `product/README.md`, `product/HANDOFF.md`, `product/docs/DELIVERY_PLAN.md`, and this packet.
- evidence: `infra/evidence/AWS_PLATFORM_DECISION_2026-07-13.md` labels official vendor claims, analytical decisions, unknowns, falsifiers, and reversal triggers. No AWS account/resource was inspected or mutated.
- limitations or blocked paths: GitHub Project mutation unavailable to current token. AWS account IDs, primary region, domain, budgets, approvers, and pager/compliance inputs are intentionally unresolved launch inputs. Production Valkey and every numeric scaling threshold remain qualification-gated.
- unrelated work preserved: all existing `research/**`, watchdog, remote-handoff, and campaign changes were excluded.
- commit: first product architecture commit is `af06af9`; this infrastructure packet will be included in the next user-authorized documentation commit.
- next action: discuss the decisions, then claim I-00/product WP-00 for coordinated implementation. Cloud mutation cannot begin before the platform checkpoint inputs and authority in `infra/docs/DELIVERY_PLAN.md`.
- released: 2026-07-13T16:29:02+00:00
