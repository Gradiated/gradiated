# Product

Gradiated hosts exact open-weight models and sells inference through direct customer API keys and OpenRouter. The current architecture is defined by [ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [Kimi K3 launch plan](../docs/KIMI_K3_PROVIDER_LAUNCH_PLAN.md), and the [canonical data model](../docs/DATA_MODEL.md).

The product side is deliberately small:

- Vite/React/shadcn browser application;
- TypeScript/Node control application using Hono, Zod, Drizzle and Better Auth;
- PostgreSQL for product and financial authority;
- generated OpenAPI 3.1 contracts and clients;
- direct exact-model endpoints backed by the Rust inference API.

The customer product still includes users, organizations, workspaces, memberships, API keys, model access, usage and billing. There is no general gateway, provider router, model alias layer or separate inference-router service.

## Current state

There is no product application yet. The next product work is to author the API contract and local Compose/mprocs stack against the reviewed data model. Do not revive deleted product blueprints; write a new focused contract when a behavior is ready to be decided.

Read [HANDOFF.md](HANDOFF.md) for the next build sequence.
