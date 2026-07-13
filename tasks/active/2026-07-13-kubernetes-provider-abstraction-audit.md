# Task: 2026-07-13-kubernetes-provider-abstraction-audit

## Outcome

The repository has an implementation-ready Kubernetes control abstraction for heterogeneous GPU providers and a complete architecture audit whose identified gaps are either resolved in canonical documents or retained as explicit measured gates.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/8
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-13T20:00:29+00:00
- started: 2026-07-13T20:00:29+00:00
- last updated: 2026-07-13T20:00:29+00:00
- scope: product/docs, product/README.md, product/HANDOFF.md, product/AGENTS.md, infra/docs, infra/README.md, infra/AGENTS.md, docs/ARCHITECTURE.md, docs/decisions/0001-aws-eks-platform.md through docs/decisions/0006-kubernetes-provider-abstraction.md, tasks/active/2026-07-13-kubernetes-provider-abstraction-audit.md
- excluded paths: research/**, application/runtime code, credentials, provider/cloud mutations, paid capacity, unrelated worktree changes
- dependencies: ADR-0001 through ADR-0005 and architecture commit `95b6592`

## Contract

- hypothesis or user value: Kubernetes CRDs/controllers can provide one declarative fleet actuation and observability surface across provider-native and managed-Kubernetes supply without representing native allocations as fake Nodes/Pods or creating a second business source of truth.
- acceptance checks: decide CRD/operator versus direct Rust interfaces/Crossplane/Virtual Kubelet/CAPI/Karmada; define source-of-truth and reconciliation ownership; freeze resources/status/finalizers/security/testing; audit product, billing, routing, data, cache, provider channel, infra, CI, DR, UX and delegation for contradictions and missing decisions; update canonical docs.
- quality gate: current primary-source evidence with falsification/uncertainty; architecture gap matrix; `python3 tools/devex/check.py`; `git diff --check`; local Markdown links; targeted invariant/terminology searches.
- SLO or budget: planning only, zero provider/cloud spend and zero external resource mutation; Kubernetes/fleet controllers remain off the request path and controller outage must not stop already-published serving cells.
- timeout: one working session; stop source collection when primary evidence is sufficient to decide the abstraction and leave provider/runtime unknowns as qualification experiments.
- artifact locations: `product/docs/KUBERNETES_PROVIDER_ABSTRACTION_2026-07-13.md`, `product/docs/ARCHITECTURE_AUDIT_2026-07-13.md`, `docs/decisions/0006-kubernetes-provider-abstraction.md`, updates in declared product/infra/docs scope, and this packet.
- resume command: `git diff -- product infra/docs docs/ARCHITECTURE.md docs/decisions/0006-kubernetes-provider-abstraction.md tasks/active/2026-07-13-kubernetes-provider-abstraction-audit.md`
- rollback or cleanup: revert the scoped documentation commit; no external resources are created.

## Plan

1. Inspect all canonical product/infrastructure documents and build a contradiction/ownership/gap matrix.
2. Research current Kubernetes operator/CRD, finalizer, Crossplane, Virtual Kubelet, Cluster API and multi-cluster semantics; decide and document the provider abstraction.
3. Resolve gaps across canonical architecture/contracts/security/testing/delivery/handoff documents, verify, and publish directly to `main`.

## Result

- status: complete; pending direct-to-main publication and claim release
- verification: `python3 tools/devex/check.py`; `git diff --check` on all owned paths; custom local Markdown link resolution across 36 changed files; obsolete `only internal network dependency`/`ProviderEndpointProjection`/`provider_endpoints` invariant search; authority/CRD/channel/cache/relay terminology presence audit.
- changed paths: ADR-0001 through ADR-0006 and root architecture map; product canonical architecture/API/billing/integration/testing/delivery/spec/handoff/README/instructions plus the dated Kubernetes decision and full audit; infrastructure cloud/Kubernetes/fleet/autoscaling/Terraform/CI/security/local/CLI/delivery/README/instructions. No runtime/application code.
- limitations or blocked paths: no cloud/Kubernetes/provider/model/payment request or paid experiment was run; provider behavior, controller runtime/version, CRD scale/reconciliation, relay performance, Valkey durability, model economics, legal terms and numeric SLOs remain the explicit measured gates in the audit. User-owned `research/sol/**` and root research handoff changes were untouched.
- commit: pending (will be recorded in the completed packet/handoff commit)
- next action: commit only declared paths to `main`, record the commit, release this claim, push, and close GitHub issue #8.
