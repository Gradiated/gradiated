# Product

Gradiated hosts open-weight models and sells inference through customer API keys
and OpenRouter. The current architecture is defined by
[ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [canonical data model](../docs/DATA_MODEL.md),
and the executable API schemas in `services/api`.

The product side is deliberately small:

- Vite/React/shadcn console;
- TypeScript/Node API, background worker and separate Temporal worker from the shared product image;
- PostgreSQL for product and financial authority;
- generated OpenAPI 3.1 contracts and clients;
- customer-key provider relay through the Rust proxy;
- exact-model hosted inference through the Rust gateway;
- captured generation content through the Rust collector into S3.

The customer product still includes users, organizations, workspaces, memberships, API keys, model access, usage and billing. Provider relay is scoped by [PROXY_FEATURE_PLAN.md](../docs/PROXY_FEATURE_PLAN.md); stored content follows [TRACES_PLAN.md](../docs/TRACES_PLAN.md).

## Repository shape

Turborepo orchestrates the deployable `services/` and shared `packages/`:

- `services/api`: TypeScript/Hono Management API;
- `services/worker`: TypeScript ingestion, settlement and reconciliation loops;
- `services/temporal-worker`: dedicated Temporal workflows and activities, with SDK metrics and independent deployment;
- `services/console`: Vite/React/shadcn customer console;
- `services/gateway`: Rust inference data plane;
- `services/proxy`: public inference front door and customer-key relay;
- `services/collector`: asynchronous generation-content batching and S3 uploads;
- `packages/contracts`: Zod API and cross-process contracts;
- `packages/control`: shared control-plane business logic and datastore adapters;
- `packages/config`: strict runtime configuration;
- `packages/credentials`: shared TypeScript and Rust provider credential loaders.

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
the complete development stack through mprocs. The launcher requires `lsof`
(`apt-get install lsof` on Debian/Ubuntu):

```sh
mise run env:build
nvm use
corepack enable
pnpm install
pnpm exec turbo run build --filter=@gradiated/api --filter=@gradiated/worker
pnpm dev
```

`mise run env:build` writes the ignored repository-root `.env` from the
`gradiated/dev/env` secret. It uses the `gradiated-restricted` AWS profile,
which every collaborator has through the `Restricted` group: it creates the
profile if needed and opens an AWS sign-in when the session has expired. Rerun it when that secret changes; it keeps any
variables only your `.env` has under a local-only section.

`pnpm dev` first stops stale application listeners (3000–3004, 9003–9004,
8233, 9464–9465, and 30000), then launches mprocs. It leaves datastore ports alone. Prefer it over
invoking `mprocs` directly so a process left behind by an earlier crash cannot
block startup.

Mprocs starts PostgreSQL, Valkey, ClickHouse and SeaweedFS through Docker
Compose. The API, worker, console, Rust gateway, proxy and collector run as native
processes. SGLang is optional: select its pane and press `s` on Apple Silicon to
start the pinned SGLang/MLX runtime. Its first start creates an ignored Python
3.12 environment and downloads `mlx-community/Qwen3-0.6B-4bit`; later starts
reuse both caches. Provider relay and capture do not require a GPU or SGLang.

Local inference clients use `http://127.0.0.1:3003/v1` (the proxy). The proxy
forwards hosted calls to the gateway on 3002 and customer-key calls to the
provider. Management requests still go to the API on 3001.

| Service                      | Local endpoint                      |
| ---------------------------- | ----------------------------------- |
| Console                      | `http://localhost:3000`             |
| Management API               | `http://127.0.0.1:3001`             |
| Gateway (internal inference) | `http://127.0.0.1:3002`             |
| Proxy (client inference)     | `http://127.0.0.1:3003`             |
| Proxy health/metrics         | `http://127.0.0.1:9003`             |
| Collector intake             | `http://127.0.0.1:3004/v1/contents` |
| Collector health/metrics     | `http://127.0.0.1:9004`             |
| SeaweedFS S3                 | `http://127.0.0.1:8333`             |

SeaweedFS [mini](https://github.com/seaweedfs/seaweedfs/wiki/Quick-Start-with-weed-mini)
is pinned to 4.47. It creates `gradiated-local-contents` idempotently and persists
objects in the `seaweedfs-data` Compose volume. Only its S3 port is published,
on loopback. The collector uses the real S3 client with `AWS_ENDPOINT_URL_S3`
and local-only credentials from `mprocs.yaml`, rather than the filesystem store.
API and worker receive the same S3 settings for trace reads and workspace cleanup
when those features are available. The API's root-env loader preserves these
local storage settings. No AWS account or production credentials are needed.

The collector spool survives process restarts under `.agents/runtime/collector/`.
Local batches flush after two seconds. Stopping the stack preserves both the
spool and S3 volume; `docker compose down --volumes` intentionally removes the
object store along with the other local datastores. Clear the collector spool
as well if intentionally resetting captured content.

Capture is enabled by default for new workspaces with 180-day retention and
requires `x-gradiated-task`. Use the
trace settings UI/API when available; enabling capture does not enable training.
Hosted gateway capture is not implemented yet. The local object store exercises
S3 uploads, tags, listing and range reads; it does not reproduce AWS IAM or KMS.

With `pnpm dev` running and PostgreSQL migrated, verify the local path without
provider credentials, external requests or a model download:

```sh
pnpm smoke:capture
```

The smoke checks the running proxy's gateway catalog forwarding, then starts a
temporary proxy with the checked-in dev capture settings and a loopback synthetic
streaming provider. It verifies the native collector's S3 batch/manifest uploads,
retention/trainability tags, and range reads with zstd decompression. It removes
its temporary database records, S3 objects and processes. Ports and storage settings
are read from `mprocs.yaml`; the normal dev proxy keeps its provider endpoints.
The pinned AWS CLI is run through mise.

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
# Include the small runtime model for the inference smoke check.
SEED_LOCAL_QWEN=1 pnpm --filter @gradiated/api seed
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
The Gradiated API reference combines management routes with documentation-only
registrations for the Rust gateway in `services/api/src/routes/gateway-contract.ts`
and `systemone-contract.ts`, with inference schemas in `gateway-schemas.ts`.
Keep these aligned with gateway behavior; contract tests check route coverage
and field descriptions. Gateway requests still run through the Rust service.

The management API uses `hono-rate-limiter` with in-memory, per-process limits:
300 requests/minute per IP, with 10/minute for waitlist signups. Excess requests
return 429 with `Retry-After`. Stripe's signed webhook is excluded from these
quotas. Hono's built-in body limiter caps management bodies at 1 MiB; inference
and telemetry retain their separate limits. Counters reset on restart and are
not shared between replicas.

Production traffic reaches the API through one ALB in X-Forwarded-For append
mode, without client ports. The limiter uses its final appended IP, ignoring
client-supplied prefixes; direct local requests fall back to the socket address.
Revisit that trust rule before adding another proxy or exposing the API directly.

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

Auto top-up charges run in the worker, which does not read `.env`. To test
them locally, start mprocs with `STRIPE_SECRET_KEY` exported in your shell.
Deployed webhook endpoints need `checkout.session.completed`,
`checkout.session.async_payment_succeeded`, `invoice.paid`,
`invoice.payment_failed` and `customer.updated`. Cards are entered in the console with Stripe's Payment
Element, which needs `STRIPE_PUBLISHABLE_KEY`; without it the card dialog
reports that card entry is not configured. Manage billing opens the Stripe
billing portal, which needs a saved portal configuration with invoice history.

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

For backend storage integration, run these commands from `product/`:

```sh
pnpm turbo run build --filter='@gradiated/worker^...'
pnpm --filter @gradiated/worker test:integration
pnpm --filter @gradiated/collector test:integration
```

These suites use disposable local datastores. Worker tests exercise actual
Valkey acknowledgement, ClickHouse storage and aggregation, and PostgreSQL
settlement retries. Collector integration runs proxy captures through the real
collector into S3-compatible storage. CI runs them in its backend storage job,
in addition to the unit checks and gateway/proxy integration suites.

GitHub's product-only `tests.yml` workflow runs only for `product/**` changes.
Its unit, real-datastore integration, and browser E2E jobs have no dependencies
on one another and therefore run in parallel.

## Local model catalog

The default seed lists every model in `packages/control/src/catalog/models/`,
including DeepSeek V4.1 Flash 1017 and GLM-5.3 Flash. It retires the
old Qwen catalog entry without deleting history. Use `SEED_LOCAL_QWEN=1` to
include Qwen for the local inference smoke check.

To update only the model catalog, run from `product/`:

```sh
SEED_CATALOG_ONLY=1 pnpm --filter @gradiated/api seed
```

This mode does not sign in or change account credit. The new entries do not
create inference deployments. The local SGLang process still serves Qwen;
DeepSeek and GLM require matching deployments before they can serve requests.

DeepSeek IDs were checked on 10 November 2026; GLM IDs on 13 September 2026:

- [DeepSeek catalog ID](https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017):
  `deepseek/deepseek-v4.1-flash-1017`.
- [DeepSeek weights](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017):
  `deepseek-ai/DeepSeek-V4.1-Flash-1017` at
  `1bae0e1088993b9b82de08f59de5be5a34e42170`.
- [GLM catalog ID](https://openrouter.ai/z-ai/glm-5.3-flash):
  `z-ai/glm-5.3-flash`.
- [GLM weights](https://huggingface.co/zai-org/GLM-5.3-Flash):
  `zai-org/GLM-5.3-Flash`.

DeepSeek V4.1 Flash 1017 is hosted on our capacity at $0.006 input,
$0.001 cached input, and $0.20 output per million tokens. Output pricing also
applies to reasoning tokens. OpenRouter fallback is capped at our input/output
prices; providers above either cap cannot serve fallback requests.

The original `deepseek/deepseek-v4.1-flash` checkpoint is retired and is neither
listed nor served, including through its retained OpenRouter mapping. Existing
callers must explicitly select `deepseek/deepseek-v4.1-flash-1017`; the old ID is
not an alias. GLM reuses the existing model configuration. Both active seeds
expose text input.

Verification: API type checks and three model configuration tests passed.
Two catalog-only seed runs returned exactly the two requested models from the
local API. The full account seed could not finish because the local magic-link
endpoint returned HTTP 500. The console test expectations were updated;
the authenticated browser test was not run.

### Transactional email

The API sends magic-link and verification-code emails through Resend's HTTPS
API. Set `RESEND_API_KEY` and `AUTH_EMAIL_FROM` when `AUTH_TEST_MODE=false`.
Production uses `Gradiated <auth@mail.gradiated.com>`. The key comes from
`gradiated/prod/product/api` in AWS Secrets Manager through External Secrets.
No key belongs in a ConfigMap or Git. The approved email templates and their
plain-text versions remain in `services/api/src/auth-email.ts`.

Apply the Terraform transactional-email module and verify `mail.gradiated.com`
in Resend before deploying the sender change. Sending requests time out after
10 seconds. Provider errors do not include email bodies, codes, or API keys.
Test mode keeps its in-memory transport and does not call Resend.

### Temporal worker

Run `pnpm --filter @gradiated/temporal-worker dev` with `DATABASE_URL`,
`CONTENTS_BUCKET` and explicit `TRAINING_EXECUTOR=mock` for local orchestration
tests. The optional mprocs process supplies those local settings. Temporal runs
in Docker Compose on port 7233; the API also needs `TRAINING_EXECUTOR=mock` to
accept starts. Production requires the Temporal connection/encryption variables
documented in the run contract. The production deployment remains at zero
replicas until a real executor is configured. Its SDK Prometheus endpoint exports
queue wait (schedule-to-start), execution latency and failure metrics independently
of the existing worker. The ordinary worker needs no Temporal credentials.

The dev server runs headless. Start the **temporal-ui** pane manually in mprocs
(or run `./scripts/run-temporal-ui-local.sh`) to open
[Temporal UI](http://localhost:8233). It is off by default and binds only to
loopback. The launcher downloads the pinned UI Server 2.54.1 native release,
checks its SHA-256 and caches it under `.agents/runtime/temporal-ui`; macOS and
Linux on arm64/x86_64 are supported. Docker Compose still owns the Temporal
server and its persisted state, while stopping the UI leaves that server running.
Local UI connects only to `127.0.0.1:7233` / namespace `default`, uses no Cloud
credentials and permits local workflow actions. Start the datastore pane first.
An existing Compose dev server must be recreated once to pick up `--headless`
and release port 8233; preserve the `temporal-data` volume.

Training schedules are stored on tasks in PostgreSQL (`training_schedule`: a
five-field UTC cron expression, or null to disable automatic training). Defaults
are weekly with persisted random minutes, hours and weekdays. Task PATCH requests
save settings and then create or update `training-task-<task_id>` directly;
clearing the cron deletes the schedule. Temporal failures are logged and leave
the saved settings intact. Resubmitting those settings retries the schedule
update. Scheduled workflows check task, workspace and organization eligibility
before admission; workspace changes do not require schedule updates.
The collector registers task rows at
capture time and retries PostgreSQL outages from a local queue; it never contacts
Temporal. Task listing reads PostgreSQL without scanning trace storage.
