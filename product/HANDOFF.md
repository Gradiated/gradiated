# Product handoff

## Current decision

Build the exact-model product in [ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [Kimi K3 provider launch plan](../docs/KIMI_K3_PROVIDER_LAUNCH_PLAN.md), the [canonical data model](../docs/DATA_MODEL.md), and the [product API contract](../docs/API.md).

The direct product remains: Vite/React/shadcn UI served by a TypeScript/Hono API, a TypeScript worker from the same image, organizations/workspaces, API keys, usage and billing. OpenRouter and direct customers use the same Rust gateway. Kimi K3 is the first model and SGLang is the initial external GPU runtime.

## Current implementation

The application slice includes Better Auth, organizations, workspaces, API
keys, the model/deployment catalog, durable balances, Stripe Checkout top-ups,
and the TypeScript settlement worker foundations. Model writes pass through a
normalizing Zod schema before PostgreSQL and Valkey, so the Rust gateway reads a
complete `GatewayModel` projection without supplying catalog defaults.

The Rust gateway includes its HTTP health shell, typed configuration, Valkey
Cluster reads, authentication/access primitives, strict model/deployment
contracts, request-envelope parsing, and the pre-admission
`RequestCoordinator`. The coordinator now performs credential, workspace,
account, balance, exact-model, deployment, streaming, output-limit, and
model-parameter qualification. It captures prices and the served release
digest, but it creates no lease and calls no runtime.

## Next product work

Continue the gateway with exact tokenizer/chat-template loading and context
bounds. Then implement the real Valkey admission Lua script and cluster-backed
state-machine tests before wiring non-streaming SGLang dispatch and atomic
terminal settlement. The public Chat Completions route must not dispatch work
until admission is present.

Do not add a second or general gateway, provider router, alias system, generalized fleet service or speculative product surface without a new decision record.
