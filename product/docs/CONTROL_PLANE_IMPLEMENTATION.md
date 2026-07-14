# Simplified control-plane implementation blueprint

## Boundary

The Node control plane owns identity integration, organizations/workspaces, keys, prepaid credit, Stripe, catalog/releases, retained-trace metadata, PostgreSQL product analytics, recommendations, distribution accounts and operator commands. It never participates in live inference admission and never mutates research experiment state directly.

The complete required field list is [the minimal persistent model](../../docs/SIMPLICITY_REVIEW.md#minimal-persistent-model). Adding a table or field requires a query/command, invariant and migration test in the same change.

## Dependencies and source layout

Use Node LTS, strict TypeScript, Hono, tRPC, Better Auth, Drizzle over `node-postgres`, Zod at untrusted boundaries, React/Vite, TanStack Router/Query, React Hook Form, Tailwind and shadcn/ui. Do not add a second ORM, a public REST surface without a consumer, ClickHouse or another product event bus.

```text
product/
  apps/
    web/src/{routes,features,components,lib}/
    control/src/
      roles/{api,financial,intelligence,trace-access}.ts
      transport/{hono,trpc,stripe}.ts
  packages/
    domain/src/{tenancy,keys,billing,catalog,traces,recommendations,distribution}/
    db/src/{schema,repositories,migrations,queries}.ts
    authz/src/
    contracts/src/gen/
    crypto/src/
    testkit/src/
    ui/src/
```

One image exposes four role commands. Deploy roles separately only for IAM, KMS decrypt, scaling or blast-radius reasons. Domain packages import no Hono, React, Drizzle, Stripe, Redis or AWS SDK object.

Catalog persistence includes relational `workspace_models` allowlists. Do not put allowed model IDs, routes or observability options into a workspace JSON blob.

## Common application contracts

```ts
type Actor = {
  userId: UserId;
  organizationId: OrganizationId;
  workspaceId?: WorkspaceId;
  requestId: RequestId;
};

interface UnitOfWork {
  transaction<T>(fn: (tx: Tx) => Promise<T>): Promise<T>;
}

interface Outbox {
  append(type: string, schemaVersion: number, payload: JsonValue, tx: Tx): Promise<void>;
}

type AppError =
  | { code: 'unauthenticated' | 'forbidden' | 'not_found' | 'conflict'; message: string }
  | { code: 'validation_failed'; fields: FieldError[] }
  | { code: 'dependency_unavailable' | 'internal'; incidentId: string };
```

Repository methods always require the organization and, when applicable, workspace in their signature and SQL predicate. IDs, roles and organization/workspace selection come from the authenticated server context, never browser claims.

The outbox schema is exactly `id, type, schema_version, payload_json, occurred_at, available_at, published_at, attempts, last_error_code`. Domain payloads carry their own required IDs; there is no universal event principal, aggregate envelope or correlation hierarchy.

## Tenancy and authorization

```ts
interface TenancyService {
  createOrganization(name: string, actor: SignedInActor): Promise<OrganizationCreated>;
  createWorkspace(input: CreateWorkspace, actor: Actor): Promise<Workspace>;
  updateWorkspace(input: UpdateWorkspace, actor: Actor): Promise<Workspace>;
  inviteMember(input: InviteMember, actor: Actor): Promise<Invitation>;
  acceptInvitation(token: string, actor: SignedInActor): Promise<void>;
}

interface KeyService {
  create(input: CreateKey, actor: Actor): Promise<{ view: ApiKeyView; secretOnce: string }>;
  revoke(id: ApiKeyId, actor: Actor): Promise<void>;
}
```

Organization creation is one transaction: organization, owner membership, one non-deletable Default workspace, owner workspace membership, audit and outbox. Better Auth's user ID is the product user ID; do not create another user table.

Roles are intentionally small:

| Scope | Roles |
| --- | --- |
| organization | `owner`, `admin`, `billing`, `member` |
| workspace | `admin`, `developer`, `viewer` |
| internal | deployment identity or explicit operator allowlist; never a customer role |

Organization owner/admin sees all workspaces; other members require a workspace row. Last owner removal is forbidden. Key secrets are returned once, stored only by keyed digest, and rotated by create-new/revoke-old—no grace-state machine.

## Billing and Stripe

Use a one-currency, fixed-chart, append-only double-entry ledger. Its structure is core financial authority, not optional analytics.

```ts
interface Ledger {
  post(command: BalancedTransaction, tx: Tx): Promise<LedgerTransactionId>;
  balanceForUpdate(orgId: OrganizationId, tx: Tx): Promise<MoneyMicros>;
}

interface TopUps {
  createCheckout(amountMicros: bigint, actor: Actor, idempotencyKey: string): Promise<CheckoutUrl>;
  handleWebhook(rawBody: Uint8Array, signature: string): Promise<void>;
}

interface UsageConsumer {
  reservationCreated(event: ReservationCreated): Promise<void>;
  usageSettled(event: UsageSettled): Promise<void>;
}

interface Reconciler {
  compare(orgId: OrganizationId): Promise<ReconciliationReport>;
  rebuildProjection(orgId: OrganizationId, actor: Operator): Promise<number>;
}
```

Webhook transaction:

1. verify raw-body signature;
2. insert unique Stripe event or return success for a duplicate;
3. lock the top-up intent and validate organization/amount/object;
4. transition `created -> completed|failed|expired`;
5. post exactly one balanced processor-clearing/customer-credit transaction and update the locked balance projection for completion;
6. append projection outbox and audit;
7. commit before 2xx.

Refunds, chargebacks and failed-request credits are new balanced transactions linked by source ID. They never modify old usage or top-up rows. `organization_balances` is a transactionally updated/rebuildable snapshot; ledger transactions/entries remain authority.

The financial role consumes the Valkey billing stream with consumer-group claim/redelivery. It upserts the operational `usage_record`, posts one customer-credit/usage-revenue transaction at settlement, updates the balance projection and commits before acknowledging. Duplicate event IDs and business keys have no effect.

## Catalog and release authority

```ts
interface Catalog {
  createDraft(input: DraftRelease, actor: Operator): Promise<ModelRelease>;
  activate(digest: ReleaseDigest, qualificationId: QualificationId, actor: ReleaseOwner): Promise<void>;
  updateAlias(input: AliasUpdate, actor: ReleaseOwner): Promise<ModelAlias>;
  retire(digest: ReleaseDigest, actor: ReleaseOwner): Promise<void>;
}
```

`model_definitions` owns stable direct/owned catalog identity; `provider_endpoints` owns credential/region lifecycle; `model_releases` is the immutable capabilities/prices/retry unit; `release_endpoints` freezes direct endpoint membership; `capacity_targets` holds owned placement; and `model_aliases` supplies stable/canary pointers and generation. There are no separate model product, family, price book, generic route-candidate, rollout or release-manifest tables.

Direct qualification references one provider/model/endpoint scope. Owned activation requires a valid exact-bundle qualification report. Rollback updates the alias to a prior active digest; in-flight requests keep their admitted digest.

## Traces, usage analytics and recommendations

The gateway encrypts retained payloads and appends ciphertext to a separate Valkey stream. The intelligence role:

1. validates bounded envelope metadata;
2. writes ciphertext to private S3;
3. inserts/updates one `traces` row;
4. acknowledges only after object and metadata are durable;
5. deletes by destroying wrapped key and deleting the object, then setting `deleted_at`.

Hono queries PostgreSQL `usage_records` and `traces` with mandatory organization/workspace/time bounds. Initial screens use indexes and closed query objects. No analytics repository abstraction or ClickHouse schema exists. Add a PostgreSQL rollup only with an `EXPLAIN ANALYZE` fixture proving a real query misses its SLO.

Trace detail uses a short-lived signed grant. The nonce is consumed once in Valkey; the `trace-access` role reloads PostgreSQL authorization/deletion state, reads exactly one S3 object, decrypts and streams `Cache-Control: no-store`. It cannot list the bucket or return presigned ciphertext.

Recommendations are one immutable summary tied to a source model and candidate release. Customer actions are `accept`, `dismiss`, or start an explicit evaluation. There is no automatic traffic rewrite and no separate workload-profile/migration-candidate/evidence-level state machine.

## Research API boundary

Hono is an authenticated BFF for the private generated Python research API. Python remains the sole normal writer for program/hypothesis/campaign/experiment/evidence/bundle/qualification state. Hono may read approved research views and send bounded operator commands, but has no mutation repository for research tables. Temporal belongs behind the Python service and never becomes a Node dependency.

## tRPC and UI

Seed routers are:

- `session`, `organizations`, `members`, `workspaces`, `workspaceMembers`;
- `apiKeys`, `billing`, `usage`, `traces`;
- `catalog` for customer reads and operator-only mutations;
- `recommendations`, `distribution`, and an operator `research` BFF when their packages arrive.

Routes are `/`, `/keys`, `/usage`, `/billing`, `/settings/organization`, and `/settings/workspaces/:id`. Product Intelligence detail lives under `/usage/:requestId`; do not build a second observability application. The Default workspace is implicit until another workspace exists. Client query keys begin with organization/workspace and switching clears scoped cache.

## Migrations, configuration and failure behavior

- Drizzle schema and reviewed SQL migrations are committed; never use schema push outside disposable tests.
- Expansion precedes code use; destructive contraction waits one release and a backup/restore check.
- Roles are `api`, `financial`, `intelligence`, `trace_access`, `research_command_writer`, and migration owner; grants reflect exact tables/actions.
- API readiness requires PostgreSQL and required config. Worker readiness requires its owned dependency; liveness checks only process progress.
- PostgreSQL failure blocks control mutations but not already projected serving. Valkey failure blocks projection/reconciliation and gateway admission. S3/KMS failure delays trace capture/detail but not settled inference.

## Verification and ordered packages

Use Vitest/fast-check/Testcontainers and Playwright. Required properties cover tenancy isolation, exactly one Default workspace, role commands, key lifecycle, Stripe event reorder/duplicates, ledger/balance equality, stream crash/redelivery, projection rebuild, trace retention/delete and no automatic recommendation switch.

1. `CP-00`: schema, migrations, UoW/outbox/idempotency and testkit.
2. `CP-01`: Better Auth, organizations/Default workspace/memberships and RBAC.
3. `CP-02`: API keys and workspace policy/projection.
4. `CP-03`: top-up, fixed-chart ledger/balance and Stripe state-machine PBT.
5. `CP-04`: financial stream consumer and reconciliation.
6. `CP-05`: immutable model releases/aliases/qualification activation.
7. `CP-06`: Vite/shadcn keys/billing/usage UI.
8. `CP-07`: encrypted trace persistence/detail/deletion and PostgreSQL analytics.
9. `CP-08`: recommendations/evaluations, distribution and research API UI as later slices.

Every package must prove a concrete command/query uses each new field. Unused schema is a failing review, not future-proofing.
