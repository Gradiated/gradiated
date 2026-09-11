# Product

Gradiated hosts open-weight models and sells inference through customer API keys
and OpenRouter. The current architecture is defined by
[ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [canonical data model](../docs/DATA_MODEL.md),
and the executable API schemas in `services/api`.

The product side is deliberately small:

- Vite/React/shadcn console;
- TypeScript/Node API plus one background worker from the same image;
- PostgreSQL for product and financial authority;
- generated OpenAPI 3.1 contracts and clients;
- direct exact-model endpoints backed by the Rust gateway.

The customer product still includes users, organizations, workspaces, memberships, API keys, model access, usage and billing. There is no general gateway, provider router, model alias layer or separate inference-router service.

## Repository shape

Turborepo orchestrates the deployable `services/` and shared `packages/`:

- `services/api`: TypeScript/Hono Management API;
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

## API development

Use the pinned Node 22 release through nvm. Install dependencies once, then run
the complete development stack through mprocs:

```sh
nvm use
corepack enable
pnpm install
pnpm dev
```

`pnpm dev` first stops stale listeners on the console, API, gateway, and SGLang
ports (3000, 3001, 3002, and 30000), then launches mprocs. Prefer it over
invoking `mprocs` directly so a process left behind by an earlier crash cannot
block startup.

Mprocs starts PostgreSQL, Valkey and ClickHouse through Docker Compose. It also
starts the API, worker, console, Rust gateway, and pinned SGLang/MLX runtime as
native processes. The worker runs generation ingestion, generation settlement,
and serving-state projection concurrently. Datastores stay containerized.
Application services run on the host for fast reloads. The first SGLang start
creates an ignored Python 3.12 environment and downloads the pinned
`mlx-community/Qwen3-0.6B-4bit` model. Later starts reuse both caches. The
checked-in Dockerfile builds the production API image but is not part of the
normal local loop.

The `migrate-postgres` and `migrate-clickhouse` panes do not start
automatically. Select each pane and press `s` after a new datastore starts or
after its schema changes. Mprocs does not support sidebar sections, so the
manual migration, seed, and Stripe processes stay together at the bottom of
the process list.

After the API is ready, run the idempotent local seed from the `seed` mprocs pane
or from another terminal, then exercise the complete non-streaming inference
path:

```sh
pnpm --filter @gradiated/api seed
pnpm smoke:gateway
```

The smoke command creates a temporary API key through the Management API, calls the
gateway on port 3002, verifies UUIDv7 and authoritative usage in the response,
and revokes the key. A successful response is returned only after the gateway
has atomically finalized the generation in Valkey.

To test the production gateway with the official OpenAI SDK, set a production
API key and run:

```sh
GRADIATED_API_KEY=grad_... pnpm smoke:gateway:openai
```

The SDK test calls `models.list()` and both non-streaming and streaming
`chat.completions.create()`. It uses
`https://api.gradiated.com` by default. Set `GRADIATED_MODEL` to
select a specific model or `GRADIATED_BASE_URL` to test another gateway.

The console listens on port 3000 and proxies `/api` and `/health`
to the API process on port 3001. The generated OpenAPI schema is available at
`http://localhost:3000/api/openapi.json`; interactive reference is at `/docs`.

To view a cloud sandbox through `gradiated-dev.test`, map the hostname to
`127.0.0.1` in `/etc/hosts`, then start the SSH profile:

```sh
pnpm dev:forward
```

The SSH profile owns the forwarded ports. Add a `LocalForward` line to
`gradiated-dev` to expose another port. The command stops stale local
listeners before it starts one persistent SSH session. Press `Control-C` to
stop all forwarded ports. Visit `http://gradiated-dev.test:3000` for port 3000
and use the same pattern for the other ports.

In production, the console is hosted at `https://console.gradiated.com` and the
API at `https://api.gradiated.com`. Set `VITE_API_URL` when building the console,
`BETTER_AUTH_URL` to the API origin, and `CONSOLE_URL` to the console origin.
`TRUSTED_ORIGINS` must contain the exact console and website origins. Local
development leaves `VITE_API_URL` unset and uses the configured console and
website ports.

Feature flags come from PostHog: set `VITE_POSTHOG_KEY` (the project's public
client key) when building the console and every flag is then evaluated per
signed-in user, so a flag such as `training` can be rolled out to one
email domain from the PostHog UI. Without the key every flag is off. Mprocs
gives the console the PostHog Development project's token, so local flags are
evaluated against that project; `VITE_FEATURE_FLAGS=training` in the root
`.env` forces flags on by name without PostHog.

The seeded development identity is `dev@gradiated.com`; local test-mode magic
links are captured by the API rather than delivered. Compose volumes preserve
local data; use
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
