# Product workstream instructions

This directory is the implementation contract for the revenue-first inference gateway. Read `README.md`, `HANDOFF.md`, and the active packet linked by the handoff before changing product code or architecture.

## Product invariants

- An organization is the customer, tenant, and billing boundary. It owns credits, top-ups, ledger accounts and organization membership.
- Every organization has exactly one non-deletable seed Default workspace, hidden from setup until another workspace exists. Workspaces own inference keys, member access, model/data policy, optional monthly limits, concurrency and usage attribution.
- API keys resolve one organization and one workspace. Organization, workspace, and key limits are checked together; workspace budgets never create an independent credit balance.
- PostgreSQL is the durable financial source of truth. Credits are represented by an append-only, balanced ledger; corrections and refunds are compensating entries.
- The Rust gateway has exactly one synchronous internal state/control dependency: Redis. Curated model APIs and the private inference router are upstream serving dependencies; it must never call PostgreSQL, the control API, Kubernetes, a capacity-provider lifecycle API, or a second queue on the request path.
- Redis admission is atomic. No upstream request starts unless authentication, status, reserve, concurrency increment, reservation lease, and billing-event append succeed together.
- Money is integer micro-USD (`i64`/`bigint`) with checked arithmetic. Floating point is forbidden for prices, balances, reservations, and settlements.
- Public inference wire compatibility is governed by protocol JSON/OpenAPI and conformance fixtures. Launch surfaces are OpenAI Responses Create, Anthropic Messages and Models; unsupported hosted/stateful surfaces fail before admission. Internal TypeScript/Rust messages are governed by Protobuf v3 and generated from `proto/`.
- Generated contracts are checked in. CI regenerates them and fails on drift, lint failure, breaking changes, or cross-language golden-fixture mismatch.
- The Vite application is a client of the Hono `/api/v1` REST API through the generated OpenAPI client. Described Zod v4 schemas generate OpenAPI 3.1, docs and explicitly allowlisted MCP tools. Do not add tRPC, handwritten duplicate clients or MCP handlers that bypass REST authorization.
- Organization deletion is owner self-service: suspend new admission immediately, drain/reconcile/refund, cryptographically delete payloads, revoke access and retain only pseudonymous required financial evidence. It requires crash/retry PBT.
- Provider secrets and customer payloads are never logged, committed, placed in ordinary fixtures, or included in CI artifacts. Product Intelligence payloads exist only as bounded encrypted trace objects under the data-mode/retention/access contract.
- PostgreSQL indexed views and measured rollups serve seed product analytics. Do not add ClickHouse, an analytics projector, or a second analytics authority without the benchmark trigger in `../docs/SIMPLICITY_REVIEW.md`.
- The customer catalog has curated direct provider/model IDs and first-party `grad/<effort>/<speed>` IDs. Direct requests never cross provider/model/version. Grad requests never leave owned inference or change effort/speed.
- Capability, modality, tool, structured-output, reasoning, privacy, and context requirements are checked before provider spend. Unsupported behavior fails explicitly; no silent parameter drop, truncation, parser/plugin, response healing, or privacy downgrade.
- Product Intelligence is the default; Private/No Retention and per-request tightening suppress payload persistence before Redis. Retention is not training consent.
- Every generative Grad release uses active-sequence KV cache and cross-request prefix reuse, including Private/No Retention. Cache is salted by opaque workspace/channel/release/retention-class scope, remains ephemeral serving state, and never enters traces, Redis, PostgreSQL, S3, backups, or logs.
- AWS hosts the gateway, inference router, fleet control, and authoritative data. Owned GPU execution runs in isolated external-capacity-provider cells. A cell may be one or many nodes but never spans provider/region and remains one routable/failure/cache unit. PostgreSQL allocation/member/cell rows are durable fleet state; Rust provider drivers reconcile them directly. Do not add fleet CRDs, fake Nodes/Pods, or provider discovery/ranks to the gateway/router path.
- Use `model provider`, `capacity provider`, and `distribution channel` explicitly. A direct model endpoint is not an inference cell or signed cell target.
- Migration recommendations are evidence-level state machines. Replay/shadow/canary require defined authority and budgets, and no state transition automatically changes customer traffic.
- Provider/model identity, effort/speed release, trace publishing/retention/delete, PostgreSQL tenant analytics, canary/session/rollback, migration experiments, and failed-request credits require TS/Rust property coverage where each implementation participates.

## Verification contract

Every change must have deterministic examples and property-based tests where invariants or state transitions are involved.

- TypeScript: Vitest plus `fast-check`; use model-based commands for billing, authorization, and webhook state machines.
- Rust: `cargo nextest`, `proptest`, and `proptest-state-machine`; use Redis Testcontainers for admission/settlement state machines.
- Every PBT failure must print the seed and shrink path, upload a replay artifact in CI, and expose a one-command replay. Accepted failures become regression fixtures.
- Agents run bounded deterministic PBT suites before direct pushes; main/nightly runs deeper time-budgeted suites. Explicitly requested or external pull requests run the bounded suite. Tests must be runnable by agents and CI; the product owner is not expected to run anything locally.
- Official OpenAI, Anthropic, and Google client smoke tests run through the Rust gateway in protected CI jobs. Untrusted pull requests use deterministic fake providers and never receive provider secrets.

## Working rules

- Claim a GitHub issue and task packet before editing. Reserve exact paths and preserve unrelated work.
- Keep architecture decisions, schemas, migrations, test fixtures, runbooks, and generated files in this directory; external tools are not the source of truth.
- Prefer small domain packages with explicit dependency direction over framework-owned business logic.
- A failed provider or missing optional secret is a test result, not permission to weaken billing or admission behavior.
- Before handoff run `python3 tools/devex/check.py`, document narrow checks, update `HANDOFF.md`, and release the packet. Commit only owned paths and push completed work directly to `main`; create a branch or pull request only when the user explicitly asks for one.
