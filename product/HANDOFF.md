# Product handoff

## Current decision

Build the exact-model product in [ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [Kimi K3 provider launch plan](../docs/KIMI_K3_PROVIDER_LAUNCH_PLAN.md), and the [canonical data model](../docs/DATA_MODEL.md).

The direct product remains: Vite/React/shadcn UI, a TypeScript/Hono control API, organizations/workspaces, API keys, usage and billing. OpenRouter and direct customers use the same Rust inference API. Kimi K3 is the first model and SGLang is the initial runtime.

## Next product work

1. Author the first Zod/OpenAPI control contract.
2. Build the Docker Compose and mprocs local stack with fake SGLang.
3. Build the Vite/shadcn app shell against generated mock handlers.
4. Implement the TypeScript control application and PostgreSQL migrations.
5. Implement the Rust inference API and cross-language fixtures.

Do not add a gateway, provider router, alias system, generalized fleet service or speculative product surface without a new decision record.
