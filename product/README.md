# Product

Gradiated hosts exact open-weight models and sells inference through direct customer API keys and OpenRouter. The current architecture is defined by [ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [Kimi K3 launch plan](../docs/KIMI_K3_PROVIDER_LAUNCH_PLAN.md), the [canonical data model](../docs/DATA_MODEL.md), and the [product API contract](../docs/API.md).

The product side is deliberately small:

- Vite/React/shadcn console;
- TypeScript/Node API plus one background worker from the same image;
- PostgreSQL for product and financial authority;
- generated OpenAPI 3.1 contracts and clients;
- direct exact-model endpoints backed by the Rust gateway.

The customer product still includes users, organizations, workspaces, memberships, API keys, model access, usage and billing. There is no general gateway, provider router, model alias layer or separate inference-router service.

## Repository shape

Turborepo orchestrates the deployable `services/` and shared `packages/`:

- `services/api`: TypeScript/Hono product API;
- `services/worker`: TypeScript background loops;
- `services/console`: Vite/React/shadcn customer console;
- `services/gateway`: Rust inference data plane;
- `packages/contracts`: Zod API and cross-process contracts;
- `packages/control`: shared control-plane business logic and datastore adapters;
- `packages/config`: strict runtime configuration.

`packages/control` is a modular monolith shared by the two TypeScript processes,
not another deployed service. Datastore-specific code remains inside it until a
measured boundary justifies a split.

## Current state

The product application currently implements Better Auth sign-in, organization
bootstrap, explicit workspace selection, one-time API-key creation/revocation,
the model catalog, durable billing balances and Stripe Checkout top-ups backed
by PostgreSQL and Valkey. The Vite application uses shadcn/ui, React Query,
React Hook Form with Zod validation, and Zustand for the small
organization/workspace UI selection state. Do not revive deleted product
blueprints; extend the focused contract when a behavior is ready to be decided.

Read [HANDOFF.md](HANDOFF.md) for the next build sequence.

## API development

Use the pinned Node 22 release through nvm. Install dependencies once, then run
the complete development stack through mprocs:

```sh
nvm use
corepack enable
pnpm install
pnpm dev
```

`pnpm dev` first stops stale listeners on the local console and API ports (3000 and
3001), then launches mprocs. Prefer it over invoking `mprocs` directly so a
process left behind by an earlier crash cannot block startup.

Mprocs starts PostgreSQL, Valkey and ClickHouse through Docker Compose, applies
PostgreSQL migrations from the host, starts the API with source watching, and
runs the idempotent seed. Datastores stay containerized; TypeScript services run
on the host for fast reloads. The checked-in Dockerfile builds the production
API image but is not part of the normal local loop.

The console listens on port 3000 and proxies `/api` and `/health`
to the API process on port 3001. The generated OpenAPI schema is available at
`http://localhost:3000/api/openapi.json`; interactive reference is at `/docs`.

In production, the console is hosted at `https://console.gradiated.com` and the
API at `https://api.gradiated.com`. Set `VITE_API_URL` when building the console,
`BETTER_AUTH_URL` to the API origin, and `TRUSTED_ORIGINS` and `CONSOLE_URL` to
the console origin. Local development leaves `VITE_API_URL` unset and keeps the
existing Vite proxy and ports.

The seeded login is `dev@gradiated.com` with password `1234`. These are
deliberately fixed local-only values, not production defaults. Compose volumes
preserve local data; use
`docker compose down --volumes` only when intentionally resetting it.

Stripe is optional locally. To exercise test-mode top-ups, put the following in
the ignored repository-root `.env` file; mprocs loads it into the API process:

```sh
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
CONSOLE_URL=http://localhost:3000
```

Use the webhook secret printed by this Stripe CLI command:

```sh
stripe listen --forward-to http://localhost:3001/api/webhooks/stripe
```

The same command is available as the `stripe-listen` pane in mprocs. It does
not start automatically; select it and press `s` when you want to test Stripe.
After copying a newly printed webhook secret into `.env`, restart the `api`
pane so it loads the value.

Without both variables, the rest of the local stack runs normally and the
billing page reports that Checkout is not configured if a top-up is attempted.

Run `pnpm check` before committing. Route declarations are the source of truth;
after changing them, run `pnpm openapi:generate` and commit the
updated `services/api/generated/openapi.json`.

Run `pnpm --filter @gradiated/console test:e2e` for the page-level Playwright
suite. It builds the API dependencies, starts and waits for the complete local
datastore stack, applies migrations, and starts the API and Vite. Every browser
test receives a unique funded user, organization, and workspace through the
shared fixture, so the spec files remain safe to run in parallel.

GitHub's product-only `tests.yml` workflow runs only for `product/**` changes.
Its unit, real-datastore integration, and browser E2E jobs have no dependencies
on one another and therefore run in parallel.
