# Product workstream instructions

Read the root [AGENTS.md](../AGENTS.md), [ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [Kimi K3 launch plan](../docs/KIMI_K3_PROVIDER_LAUNCH_PLAN.md), the [canonical data model](../docs/DATA_MODEL.md), this file and [HANDOFF.md](HANDOFF.md) before changing product code.

## Boundaries

- TypeScript/Node owns the browser product, HTTP API, PostgreSQL and billing workflows.
- Rust owns everything in the inference hot path: authentication, admission, exact model selection, streaming, cancellation, usage and SGLang dispatch.
- Direct customers and OpenRouter use the same Rust inference API.
- Requests name an exact hosted model. Do not add provider routing, fallback, branded aliases or silent parameter dropping.
- Every HTTP API is authored with described Zod schemas and route metadata, then generates OpenAPI 3.1, docs, the browser client and Rust fixtures.
- The browser uses only the generated control client.

## Local contract

The commands docker compose up --build and mprocs must eventually run the complete local stack without cloud credentials, a GPU or paid services. The fake SGLang runtime is part of that local stack.

There are no detailed product blueprints yet. Author them in small, reviewed documents when implementation starts; do not reconstruct the deleted gateway/distribution plans.

## Verification

Run the narrowest relevant checks, python3 tools/devex/check.py, and git diff --check. Preserve unrelated worktree changes and never commit credentials or customer/model payloads.
