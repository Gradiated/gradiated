# Control-plane library

This package holds the shared TypeScript business logic and adapters for `api`
and `worker`. It is one modular library, not a deployed service. It owns the
Drizzle schema and migrations, the PostgreSQL transactions and the ClickHouse
queries. It does not expose datastore types to the browser contract.

Add a module only with the feature that uses it. The package has no generic
repository or service framework.

## Modules

- `db/`: the PostgreSQL client, the migration runner and the Drizzle schema.
- `access.ts`: the active membership checks for organizations and workspaces.
- `catalog/`: models and model deployments.
- `billing/`: billing accounts and the balance ledger. Every balance change
  goes through `postBalanceTransaction` in `billing/ledger.ts`.
- `organizations/`: organization creation with the default workspace, the
  billing account and the signup credit.
- `workspaces/`: workspaces, API keys and the API-key secret format.
- `distribution-channels/`: the OpenRouter organization, workspace and key.
- `usage/`: workspace usage summaries and the generation log from ClickHouse.
- `settlement/`: the ClickHouse settlement reader and the PostgreSQL
  settlement store.
- `clickhouse/`: the ClickHouse client, the generation and profiling writers,
  and the migration runner.
- `deployment-status/`: runtime heartbeats. This is the only Valkey write in
  the package.
- `waitlist/`: website waitlist signups.
- `service-logging.ts`: redacted, rate-limited service logs.

Stripe workflows are in `services/api/src/billing`.

## Database

Set `DATABASE_URL`, then generate a migration after you change the schema:

```sh
pnpm --filter @gradiated/control db:generate
```

The committed SQL migrations are the deployment input. The release migration
job applies them with `pnpm --filter @gradiated/control db:migrate`.

## Tests

Run the type check and the tests with:

```sh
pnpm --filter @gradiated/control check
```

The integration tests start one disposable PostgreSQL container through the
local Docker engine. They apply the migrations once to a template database.
Each test file gets a copy of that template.

To use a local PostgreSQL server instead of Docker, set
`CONTROL_TEST_DATABASE_URL` to an administrative URL on `localhost`.

## ClickHouse

The ClickHouse migrations are in `clickhouse/migrations`. The migration runner
creates the application database and users before it applies the ordered SQL
files. It records each file name and SHA-256 checksum in
`gradiated_schema_migrations`. It stops before it applies anything if an
applied file changed.

Run the migrations with:

```sh
pnpm --filter @gradiated/control clickhouse:migrate
```

Set `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_SECURE`,
`CLICKHOUSE_DATABASE`, `CLICKHOUSE_ADMIN_USERNAME`,
`CLICKHOUSE_ADMIN_PASSWORD`, `CLICKHOUSE_APPLICATION_USERNAME`,
`CLICKHOUSE_APPLICATION_PASSWORD`, `CLICKHOUSE_METABASE_USERNAME` and
`CLICKHOUSE_METABASE_PASSWORD`.

The application user gets `SELECT` and `INSERT` on the database. The Metabase
user gets read-only `SELECT`. Do not use the application credentials for
schema migrations.
