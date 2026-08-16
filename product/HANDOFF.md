# Product handoff

## Current decision

Build the exact-model product in [ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [Kimi K3 provider launch plan](../docs/KIMI_K3_PROVIDER_LAUNCH_PLAN.md), the [canonical data model](../docs/DATA_MODEL.md), and the [product API contract](../docs/API.md).

The direct product remains: Vite/React/shadcn UI served by a TypeScript/Hono API, a TypeScript worker from the same image, organizations/workspaces, API keys, usage and billing. OpenRouter and direct customers use the same Rust gateway. Kimi K3 is the first model and SGLang is the initial external GPU runtime.

## Next product work

The application slice now includes Better Auth, organizations, workspaces, API
keys, model catalog, durable balances and Stripe Checkout top-ups. Continue with
the TypeScript worker and usage views before implementing the Rust gateway and
cross-language inference fixtures.

Do not add a second or general gateway, provider router, alias system, generalized fleet service or speculative product surface without a new decision record.
