# Product workstream instructions

Read the root [AGENTS.md](../AGENTS.md), [ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [canonical data model](../docs/DATA_MODEL.md), and this file before changing product code.

## Boundaries

- TypeScript/Node owns the browser product, HTTP API, PostgreSQL and billing workflows.
- Rust owns everything in the inference hot path: authentication, admission, exact model selection, streaming, cancellation, usage and SGLang dispatch.
- Direct customers and OpenRouter use the same Rust gateway.
- Requests name an exact hosted model. Do not add provider routing, fallback, branded aliases or silent parameter dropping. The customer-key proxy in `services/proxy` is the only exception, and [PROXY_FEATURE_PLAN.md](../docs/PROXY_FEATURE_PLAN.md) bounds it.
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

## Code readability

- Separate logical steps inside functions with one blank line. Apply this to
  authored Rust and TypeScript code.
- Keep related declarations together. Add a blank line between setup,
  validation, loops, state changes, and the final return.
- Add a blank line after a guard clause before the normal path continues.
- Do not add a blank line after every statement. Use spacing to show logical
  groups. Formatters do not replace this readability check.
- Do not edit generated code or imported upstream code only to change spacing.

## Comments

The default is no comment. Names, types and small functions carry the meaning.

- Write a comment only when a reader cannot tell what the code does, or would
  get it wrong, without it. Examples: a vendor or wire-format quirk, a magic
  value, or a workaround that looks like a mistake.
- Do not write doc comments that restate a name, explain why a function exists,
  describe how components fit together, or narrate the next lines. The code and
  the plans in `docs/` already say that.
- Keep each comment to one or two lines, next to the line it explains.
- Before you finish a change, reread every comment you added and delete each
  one that the code already makes clear.
- Write comments about the code as it stands. Do not refer to conversations,
  requests or the history of an edit.

Example of a comment to delete:

```rust
/// Every request gets its generation identifier here, whatever serves it, so one
/// value names the billing row, the stored contents and the client's reference.
```

## Local contract

`pnpm dev`/mprocs is the canonical local path. Docker Compose runs only the
stateful dependencies; the TypeScript services, Rust gateway, proxy, collector and SGLang run as
native host processes for fast feedback and access to host acceleration.
The supported Apple Silicon inference profile runs a pinned SGLang/MLX build
and a pinned small local model. Focused gateway tests may replace the runtime
through the `ModelRuntime` test boundary, but there is no separately deployed
fake-SGLang service.

There are no detailed product blueprints yet. Author them in small, reviewed documents when implementation starts; do not reconstruct the deleted gateway/distribution plans.

## Verification

Run the narrowest relevant checks, python3 tools/devex/check.py, and git diff --check. Preserve unrelated worktree changes and never commit credentials or customer/model payloads.
