# Product workstream instructions

This directory is the implementation contract for the revenue-first inference gateway. Read `README.md`, `HANDOFF.md`, and the active packet linked by the handoff before changing product code or architecture.

## Product invariants

- An organization is the customer, tenant, and billing boundary. It owns credits, top-ups, ledger accounts, organization membership, global policy, and management credentials.
- Every organization has exactly one non-deletable seed Default workspace. Workspaces own inference keys, member access, routes, model/provider policy, budgets, concurrency, usage attribution, and observability settings.
- API keys resolve one organization and one workspace. Organization, workspace, and key limits are checked together; workspace budgets never create an independent credit balance.
- PostgreSQL is the durable financial source of truth. Credits are represented by an append-only, balanced ledger; corrections and refunds are compensating entries.
- The Rust gateway has exactly one internal runtime dependency: Redis. It must never call PostgreSQL, the control API, or a second queue on the request path.
- Redis admission is atomic. No upstream request starts unless authentication, status, reserve, concurrency increment, reservation lease, and billing-event append succeed together.
- Money is integer micro-USD (`i64`/`bigint`) with checked arithmetic. Floating point is forbidden for prices, balances, reservations, and settlements.
- Public inference wire compatibility is governed by OpenAPI/JSON Schema and conformance fixtures. Internal TypeScript/Rust messages are governed by Protobuf v3 and generated from `proto/`.
- Generated contracts are checked in. CI regenerates them and fails on drift, lint failure, breaking changes, or cross-language golden-fixture mismatch.
- The Vite application is a client of the Hono control API. tRPC is private to the first-party UI; public management endpoints remain versioned REST/OpenAPI.
- Provider secrets and full prompts/responses are never logged, committed, placed in test fixtures, or included in CI artifacts.

## Verification contract

Every change must have deterministic examples and property-based tests where invariants or state transitions are involved.

- TypeScript: Vitest plus `fast-check`; use model-based commands for billing, authorization, and webhook state machines.
- Rust: `cargo nextest`, `proptest`, and `proptest-state-machine`; use Redis Testcontainers for admission/settlement state machines.
- Every PBT failure must print the seed and shrink path, upload a replay artifact in CI, and expose a one-command replay. Accepted failures become regression fixtures.
- Pull requests run bounded deterministic PBT suites. Main/nightly runs deeper time-budgeted suites. Tests must be runnable by agents and CI; the product owner is not expected to run anything locally.
- Official OpenAI and Anthropic client smoke tests run through the Rust gateway in protected CI jobs. Untrusted pull requests use deterministic fake providers and never receive provider secrets.

## Working rules

- Claim a GitHub issue and task packet before editing. Reserve exact paths and preserve unrelated work.
- Keep architecture decisions, schemas, migrations, test fixtures, runbooks, and generated files in this directory; external tools are not the source of truth.
- Prefer small domain packages with explicit dependency direction over framework-owned business logic.
- A failed provider or missing optional secret is a test result, not permission to weaken billing or admission behavior.
- Before handoff run `python3 tools/devex/check.py`, document narrow checks, update `HANDOFF.md`, and release the packet. Do not commit or push unless explicitly authorized.
