# Control-plane library

Shared TypeScript business logic and adapters used by `api` and `worker` live
here. This is one modular library, not a deployed service. It owns the Drizzle
schema and migrations, PostgreSQL transactions, Valkey projection operations,
ClickHouse queries and Stripe workflows without exposing datastore types to the
browser contract.

Add modules only with the feature that consumes them; there is no empty generic
repository or service framework at launch.

## Database

Set `DATABASE_URL`, then generate a migration after changing the schema:

```sh
pnpm --filter @gradiated/control db:generate
```

Committed SQL migrations are the deployment input. Apply them with
`pnpm --filter @gradiated/control db:migrate` from the release migration job.
