# Task: 2026-07-13-open-distribution-integrations

## Outcome

The product has an implementation-ready open distribution strategy: Grad-owned inference is a first-class OpenAI-compatible provider endpoint usable directly or through prioritized third-party gateways, with current onboarding requirements, packages, reusable harnesses, channel accounting, tests, and delegation order documented.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/9
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-13T20:45:00+00:00
- started: 2026-07-13T20:45:00+00:00
- last updated: 2026-07-13T22:59:09+02:00
- scope: product/docs/DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md, product/docs/ARCHITECTURE.md, product/docs/INTEGRATIONS.md, product/docs/API_AND_DATA_CONTRACTS.md, product/docs/TESTING_AND_CI.md, product/docs/DELIVERY_PLAN.md, product/docs/PRODUCT_SPEC.md, product/README.md, product/HANDOFF.md, docs/decisions/0002-opinionated-inference-product.md, tasks/done/2026-07-13-open-distribution-integrations.md
- excluded paths: `research/**`, runtime/application code, credentials, partner applications/contact, cloud/provider mutations, paid requests, unrelated worktree changes
- dependencies: ADR-0002/0003/0005/0006, product architecture audit, existing OpenRouter spike and integration plan

## Contract

- hypothesis or user value: One hardened OpenAI-compatible serving surface plus channel-specific catalog/auth/accounting adapters and a shared conformance harness can distribute Grad inference through multiple routers without duplicating model runtimes or forcing users onto Grad's gateway.
- acceptance checks: distinguish direct endpoint, self-configured custom-provider support, and formal marketplace/provider listing; inventory and prioritize current relevant gateways; record onboarding/protocol/auth/catalog/billing/SLO requirements; select packages per TypeScript/Rust/Python harness; define shared fixtures, contract tests, live soaks, channel accounting and failure behavior; update canonical API/integration/testing/delivery/handoff docs.
- quality gate: current official primary sources with retrieval date and evidence labels; falsification/uncertainty; local link resolution; `python3 tools/devex/check.py`; `git diff --check`; terminology/invariant searches.
- SLO or budget: planning only, zero external spend/mutation; no partner application, credentials, terms acceptance, publishing, or customer traffic; direct OpenAI compatibility remains usable independent of formal listing.
- timeout: one working session; stop source collection after the major seed distribution classes are covered and leave invitation/contract-only details as revalidation gates.
- artifact locations: `product/docs/DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md`, canonical product docs in scope, and this packet.
- resume command: `sed -n '1,420p' product/docs/DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md && sed -n '114,135p' product/docs/DELIVERY_PLAN.md`
- rollback or cleanup: revert the scoped documentation commit; no external resources are created.

## Plan

1. Inspect existing downstream-channel assumptions and define the missing endpoint/listing/harness decisions.
2. Research current official OpenRouter and other gateway integration surfaces, onboarding and package ecosystems.
3. Write the dated distribution brief, update canonical contracts/tests/delivery/handoff, verify, and publish directly to `main`.

## Result

- status: complete
- verification: current official OpenRouter, OpenAI, Hugging Face, Cloudflare, LiteLLM, Portkey, Helicone, Vercel AI SDK/Gateway and Kong sources reviewed; `python3 tools/devex/check.py` passed; `git diff --check` passed; all repo-local Markdown links in changed docs resolved; principal/accounting/OpenRouter-hop terminology searches passed.
- changed paths: `product/docs/DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md`, `product/docs/ARCHITECTURE.md`, `product/docs/INTEGRATIONS.md`, `product/docs/API_AND_DATA_CONTRACTS.md`, `product/docs/TESTING_AND_CI.md`, `product/docs/DELIVERY_PLAN.md`, `product/docs/PRODUCT_SPEC.md`, `product/README.md`, `product/HANDOFF.md`, `docs/decisions/0002-opinionated-inference-product.md`, and this packet.
- limitations or blocked paths: no authenticated partner UI, live/paid request, application, OSS contribution, credential exchange, commercial term review or hosted conformance run was authorized or performed. Vercel native AI Gateway listing remains unconfirmed; Kong requires an exact-version/licensing spike; all vendor requirements must be revalidated before onboarding.
- commit: `82bd779` (`docs: specify open inference distribution`); completion metadata follows in the task-close commit.
- next action: when implementation begins, claim WP-00 public contract/tooling first, then delegate WP-09 shared harness and target-owned integrations in the documented order.
