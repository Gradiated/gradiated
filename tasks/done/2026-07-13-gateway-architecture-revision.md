# Task: 2026-07-13-gateway-architecture-revision

## Outcome

The gateway product specification is revised to use a Vite/shadcn frontend, Hono/tRPC control API, Rust-only gateway, organization-scoped prepaid credits, Default and additional workspaces with independent keys/policy/limits, PostgreSQL ledger authority, Redis-only gateway state, generated Protobuf contracts, PBT, reconciliation, and real-provider CI tests. A source-backed OpenRouter architecture/feature spike informs the hierarchy and roadmap.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/1
- GitHub project: unavailable to current fine-grained token; human-managed until access exists
- owner: Codex
- Codex thread: current product architecture thread
- created: 2026-07-13
- started: 2026-07-13
- last updated: 2026-07-13
- scope: `product/**`, this packet, and the product entry in `docs/CONTEXT_INDEX.md` if required
- excluded paths: `research/**`, all active experiment artifacts, shared runtime source outside `product/**`
- dependencies: current product planning baseline

## Contract

- hypothesis or user value: organization-funded prepaid inference with workspace-scoped keys, routes, models, budgets, and concurrency can generate revenue safely while PostgreSQL remains the reconcilable financial source of truth.
- acceptance checks: Vite/Hono replaces the old web architecture; every organization gets a Default workspace; organization credit and nested workspace/key limits are atomic in Redis; reconciliation failure semantics are explicit; TS/Rust generation and CI drift checks are specified; PBT/replay and official-client E2E paths are specified; a source-backed OpenRouter spike covers hierarchy, keys, limits, routing, and provider integration.
- quality gate: all product documents agree on tenancy, dependencies, protocols, billing states, tests, and delegation order.
- SLO or budget: $0 external spend; planning-only; no live provider calls.
- timeout: 30 minutes.
- artifact locations: `product/README.md`, `product/HANDOFF.md`, `product/AGENTS.md`, `product/docs/*.md`.
- resume command: `python3 tools/devex/context.py && sed -n '1,240p' product/HANDOFF.md`.
- rollback or cleanup: revert only owned product documentation and this packet; preserve all research changes.

## Plan

1. Verify official Vite/Hono/tRPC, Protobuf generation, PBT, provider SDK, OpenRouter product, and gateway-integration constraints.
2. Revise product, organization/workspace architecture, API/data, security/billing, Redis, integration, testing, and delivery contracts.
3. Validate terminology and repository checks, then complete the handoff.

## Result

- status: done
- verification: `python3 tools/devex/check.py` passed (environment reports Rust toolchain absent, irrelevant to documentation-only scope); `git diff --check` passed on tracked owned paths; repository-local Markdown links resolved; stale architecture terminology scan passed; no live provider requests were made.
- changed paths: `product/AGENTS.md`, `product/README.md`, `product/HANDOFF.md`, all `product/docs/*.md` including new `BILLING_AND_REDIS.md`, `TESTING_AND_CI.md`, and `OPENROUTER_SPIKE.md`; product entry in `docs/CONTEXT_INDEX.md`; this packet.
- limitations or blocked paths: GitHub Project mutation unavailable to the current token; OpenRouter evidence is public vendor documentation only, so internal physical topology and commercial acceptance remain unknown; actual model IDs and managed Redis failover semantics require implementation-time verification.
- commit: not requested
- next action: claim WP-00 in `product/docs/DELIVERY_PLAN.md` and scaffold contracts/PBT/CI before parallel implementation.
- released: 2026-07-13T15:25:26+00:00
