# Product workstream instructions

Read the root [AGENTS.md](../AGENTS.md), [ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [Kimi K3 launch plan](../docs/KIMI_K3_PROVIDER_LAUNCH_PLAN.md), the [canonical data model](../docs/DATA_MODEL.md), this file and [HANDOFF.md](HANDOFF.md) before changing product code.

## Boundaries

- TypeScript/Node owns the browser product, HTTP API, PostgreSQL and billing workflows.
- Rust owns everything in the inference hot path: authentication, admission, exact model selection, streaming, cancellation, usage and SGLang dispatch.
- Direct customers and OpenRouter use the same Rust gateway.
- Requests name an exact hosted model. Do not add provider routing, fallback, branded aliases or silent parameter dropping.
- Every HTTP API is authored with described Zod schemas and route metadata, then generates OpenAPI 3.1, docs, the browser client and Rust fixtures.
- The browser uses only the generated API client.
- Turborepo orchestrates deployables under `services/` and shared TypeScript
  modules under `packages/`. Keep `packages/control` a modular monolith; do not
  create a package per table, workflow or datastore.
- Split tests by route or domain behavior. Shared fixtures belong in a small
  support module; do not accumulate unrelated coverage in a single app test.
- Prefer official shadcn/ui components and blocks for established application
  patterns before designing bespoke primitives. Adapt their composition to the
  product domain; do not retain placeholder navigation or fake data.
- Use `const` arrow functions for authored TypeScript functions and React
  components. Generated or directly imported shadcn primitives may retain their
  upstream syntax.

## Local contract

`pnpm dev`/mprocs is the canonical local path. Docker Compose runs only the
stateful dependencies; the TypeScript services, Rust gateway and SGLang run as
native host processes for fast feedback and access to host acceleration.
The supported Apple Silicon inference profile runs a pinned SGLang/MLX build
and a pinned small local model. Focused gateway tests may replace the runtime
through the `ModelRuntime` test boundary, but there is no separately deployed
fake-SGLang service.

There are no detailed product blueprints yet. Author them in small, reviewed documents when implementation starts; do not reconstruct the deleted gateway/distribution plans.

## Verification

Run the narrowest relevant checks, python3 tools/devex/check.py, and git diff --check. Preserve unrelated worktree changes and never commit credentials or customer/model payloads.
