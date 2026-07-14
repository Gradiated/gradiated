# Task: 2026-07-14-rest-mcp-multinode-architecture

## Outcome

The canonical product/infrastructure architecture replaces tRPC with a described Hono REST/OpenAPI contract and generated MCP adapter, makes organization deletion self-service, launches OpenAI Responses plus Anthropic Messages, and makes single/multi-node owned inference buildable behind one cell contract.

## Owner and coordination

- GitHub issue: 15
- GitHub project:
- owner: root
- Codex thread:
- created: 2026-07-14T12:26:59+00:00
- started: 2026-07-14T12:26:59+00:00
- last updated: 2026-07-14T12:26:59+00:00
- scope: docs/*.md,docs/decisions/*.md,product/*.md,product/docs/*.md,infra/*.md,infra/docs/*.md,tasks/active/2026-07-14-rest-mcp-multinode-architecture.md
- excluded paths:
- dependencies: current simplicity review and product/infra implementation blueprints

## Contract

- hypothesis or user value: one documented API and two modern inference protocols minimize adoption friction; hiding multi-node topology behind the cell preserves product simplicity while supporting frontier models.
- acceptance checks: no active document treats tRPC/operator-only deletion/multi-node deferral as current; all new authority, fields, APIs, failure paths, packages and PBT are explicit; DevEx and markdown/link checks pass.
- quality gate: canonical architecture, simplicity review, coverage ledger, product/infra plans and handoffs agree.
- SLO or budget: documentation-only; no provider/cloud spend.
- timeout: one bounded architecture pass.
- artifact locations: `docs/`, `product/docs/`, `infra/docs/` and workstream handoffs.
- resume command: `python3 tools/devex/start.py && git diff -- docs product infra tasks/active/2026-07-14-rest-mcp-multinode-architecture.md`
- rollback or cleanup: revert only issue-15 documentation commit; no runtime/cloud state exists.

## Plan

1. Verify current official Hono/Zod/OpenAPI/MCP, Responses, Messages and distributed-serving capabilities.
2. Freeze detailed REST/MCP, organization-deletion, public-protocol and multi-node contracts plus ADRs.
3. Reconcile architecture, data model, product/infra delivery, tests, handoffs and coverage; run repository checks and publish.

## Result

- status: done
- verification: `git diff --check`; `python3 tools/devex/check.py`; local Markdown-link target check; stale-contract searches for tRPC, operator-only deletion and multi-node deferral.
- changed paths: `docs/{ARCHITECTURE,CONTEXT_INDEX,IMPLEMENTATION_COVERAGE,SIMPLICITY_REVIEW,STARTUP_ARCHITECTURE}.md`; `docs/decisions/{0005,0006,0007,0008,0009,README}.md`; `product/{AGENTS,HANDOFF,README}.md`; control/gateway/inference/research/distribution/product/delivery/testing documents under `product/docs/`; `infra/{HANDOFF,README}.md`; cloud/platform/Kubernetes/scaling/fleet/security/CI/delivery/local documents under `infra/docs/`.
- limitations or blocked paths: implementation and paid two-node/provider qualification remain future work; legal retention periods require counsel/founder approval.
- commit: this architecture handoff commit
- next action: delegate `API-00`, `WP-01` deletion state model, `GW-03/GW-07` protocols and `MN-00` topology contracts as non-overlapping first packages.
- released: 2026-07-14T12:49:53+00:00
