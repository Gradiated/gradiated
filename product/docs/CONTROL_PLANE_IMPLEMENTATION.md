# Control plane implementation blueprint

## Scope and invariants

This document is the build contract for the customer/operator web application, Hono API, PostgreSQL domain, background workers, retained-data services and public release authority. It does not define public inference wire behavior, GPU execution or research candidate mutation.

Non-negotiable rules:

- Better Auth proves identity/session only; product tables own organizations, workspaces, roles and policy.
- Every protected use case receives a server-derived `ActorContext`; IDs or roles from the browser never establish authority.
- PostgreSQL mutations commit domain state, idempotency record, audit and outbox in one transaction.
- Ledger entries are balanced integer micro-USD; no service mutates an old financial fact.
- The control API never participates in inference admission and cannot make Redis a financial authority.
- Research state is mutated only through the private Python research API. Node owns public product release approval/alias policy, not research evidence.
- Raw trace payloads are never returned by ordinary database/analytics queries and never pass through ClickHouse.

## Technology and package layout

Use Node LTS, strict TypeScript, Hono, tRPC v11, Zod at transport/config boundaries, Drizzle over `node-postgres`, Better Auth, React/Vite, TanStack Router/Query, Tailwind and shadcn/ui. Pin exact versions in RF/WP-00 and do not use `drizzle-kit push` outside disposable local databases. Generated reviewed SQL migrations are canonical deployment artifacts.

```text
product/
  apps/
    web/src/
      app/ routes/ features/ components/ lib/
    control-api/src/
      bootstrap/ middleware/ trpc/ rest/ auth/ health/
    control-worker/src/roles/
      financial.ts projection.ts modelops.ts scheduler.ts
    intelligence-worker/src/roles/
      trace.ts analytics.ts recommendation.ts retention.ts
    trace-access/src/
  packages/
    domain/src/
      tenancy/ keys/ billing/ catalog/ releases/ traces/ workloads/ audit/
    db/src/
      schema/ repositories/ transactions/ migrations/ queries/
    authz/src/
    contracts/src/gen/
    research-client/src/gen/
    analytics/src/
    crypto/src/
    jobs/src/
    ui/src/
    testkit/src/
```

Dependency direction is `transport/UI -> application use case -> domain -> repository/clock/ID/event interfaces`. Drizzle, Stripe, Redis, ClickHouse, S3/KMS and generated clients implement ports. Domain packages do not import Hono, React, Stripe SDK, Redis clients or Drizzle table objects.

## Shared application contracts

```ts
type ActorContext = {
  actorUserId: UserId;
  sessionId: SessionId;
  organizationId: OrganizationId;
  organizationMembershipId: OrganizationMembershipId;
  workspaceId?: WorkspaceId;
  workspaceMembershipId?: WorkspaceMembershipId;
  requestId: RequestId;
  recentAuthAt?: Instant;
};

interface UnitOfWork {
  transaction<T>(fn: (tx: TransactionContext) => Promise<T>): Promise<T>;
}

interface IdempotencyStore {
  begin(scope: string, key: string, requestHash: Digest, tx: TransactionContext): Promise<BeginResult>;
  complete(recordId: Id, responseRef: JsonValue, tx: TransactionContext): Promise<void>;
}

interface OutboxWriter {
  append(event: DomainEvent, tx: TransactionContext): Promise<void>;
}

type AppError =
  | { code: 'unauthenticated' | 'forbidden' | 'not_found'; safeMessage: string }
  | { code: 'conflict' | 'invalid_state' | 'idempotency_conflict'; safeMessage: string }
  | { code: 'validation_failed'; fields: FieldError[] }
  | { code: 'dependency_unavailable' | 'internal'; incidentId: string };
```

Use nominal/branded IDs, `bigint` money at application boundaries, UTC instants and explicit page cursors. Never accept an unscoped repository method such as `getWorkspace(id)`; require organization and workspace scope in the method signature and SQL predicate.

## Tenancy, membership and key domain

### Core aggregates and services

```ts
interface OrganizationService {
  create(input: CreateOrganization, actor: SignedInActor): Promise<OrganizationCreated>;
  rename(input: RenameOrganization, actor: ActorContext): Promise<Organization>;
  requestClosure(input: RequestOrganizationClosure, actor: ActorContext): Promise<ClosureRequest>;
}

interface WorkspaceService {
  create(input: CreateWorkspace, actor: ActorContext): Promise<Workspace>;
  updatePolicy(input: UpdateWorkspacePolicy, actor: ActorContext): Promise<WorkspacePolicyVersion>;
  requestDelete(input: RequestWorkspaceDelete, actor: ActorContext): Promise<DeletionRequest>;
}

interface MembershipService {
  invite(input: InviteMember, actor: ActorContext): Promise<Invitation>;
  accept(input: AcceptInvitation, signedIn: SignedInActor): Promise<MembershipSet>;
  changeRole(input: ChangeRole, actor: ActorContext): Promise<void>;
  remove(input: RemoveMember, actor: ActorContext): Promise<void>;
}

interface ApiKeyService {
  create(input: CreateApiKey, actor: ActorContext): Promise<{ key: ApiKeyView; secretOnce: string }>;
  rotate(input: RotateApiKey, actor: ActorContext): Promise<{ key: ApiKeyView; secretOnce: string }>;
  revoke(input: RevokeApiKey, actor: ActorContext): Promise<void>;
}
```

`OrganizationService.create` is one transaction: insert organization, owner membership, exactly one Default workspace, owner workspace membership, audit event and `OrganizationConfigChanged` outbox. A database constraint plus PBT prevents two Defaults.

API key raw format is `grad_<environment>_<public-prefix>_<secret>`. Store only public prefix, keyed digest with pepper version, last-four display, scopes, status and metadata. Creation/rotation returns raw bytes once after commit; logs, analytics, traces and idempotency response storage contain no secret. Rotation creates a new key and optionally schedules the old key's grace revocation; it never mutates secret material in place.

### Authorization policy

`AuthorizationService.authorize(actor, action, resource)` is the one role evaluator. Repositories still scope SQL as defense in depth.

| Action | Organization role | Workspace role / condition |
| --- | --- | --- |
| billing/top-up/receipts | owner or billing | none |
| organization member admin | owner/admin | none; last owner protected |
| workspace policy/members/delete | owner/admin or assigned member | workspace admin |
| key create/rotate/revoke | owner/admin or assigned member | admin/developer; viewer denied |
| usage list/detail | active org membership | workspace viewer+ |
| trace export/delete | owner/admin or assigned member | workspace admin and recent auth |
| release/research operator | separate operator role | never inferred from customer role |

Invitation tokens are high entropy and stored by digest. Acceptance locks invitation and memberships, checks email policy/expiry/organization status and creates Default-workspace access in one transaction.

## Billing and payment domain

### Financial types and services

```ts
type Money = { currency: 'USD'; micros: bigint };

interface LedgerService {
  post(command: LedgerCommand, tx: TransactionContext): Promise<LedgerTransactionId>;
  balance(organizationId: OrganizationId, tx?: TransactionContext): Promise<Money>;
}

interface TopUpService {
  createCheckout(input: CreateTopUp, actor: ActorContext, idempotencyKey: string): Promise<CheckoutRedirect>;
  handleStripeWebhook(rawBody: Uint8Array, signature: string, receivedAt: Instant): Promise<WebhookResult>;
}

interface UsagePoster {
  post(event: SettlementEvent, streamIdentity: StreamIdentity): Promise<PostingResult>;
  postFailedRequestCredit(event: FailedRequestCreditEvent): Promise<PostingResult>;
}

interface BillingReconciler {
  reconcileOrganization(id: OrganizationId, reason: ReconcileReason): Promise<ReconcileReport>;
  rebuildProjection(id: OrganizationId, operator: OperatorContext): Promise<ProjectionEpoch>;
}
```

`createCheckout` validates an allowlisted amount/currency, writes `topup_intent(created)` and idempotency record, then creates the Stripe session with only internal top-up/organization references. If Stripe succeeds but the final local update fails, retry uses the same idempotency key and recovered Stripe object.

Webhook transaction:

1. verify signature over raw bytes before JSON parsing;
2. insert unique `payment_event(provider_event_id)` or return duplicate result;
3. lock the top-up intent and validate organization, amount, currency and provider object;
4. transition the intent according to the explicit state machine;
5. for a completed payment, post balanced cash/credit/clearing entries exactly once;
6. append `OrganizationCreditChanged` and audit records;
7. commit before returning 2xx.

Unsupported/conflicting events are retained as quarantined metadata and alert; they never improvise a ledger effect. Refunds and chargebacks use new compensating transactions. Automatic top-up is not implemented until a later package adds customer maximum, frequency, payment-method authority, velocity/fraud controls and its own PBT.

### Financial worker roles

- `financial-worker`: Redis billing stream -> immutable usage/ledger/outbox transaction; pending claim/redelivery; poison quarantine.
- `projection-worker`: ordered PostgreSQL outbox -> versioned Redis config/credit/catalog keys; urgent key/suspension path uses the same ordering.
- `scheduler`: continuous lag checks, hourly full reconciliation, retention and receipt jobs.
- `modelops-worker`: model metadata ingestion, endpoint qualification expiry and public release projection; no ledger mutation.

Every handler implements `JobHandler<T>.run(job, lease): Promise<JobOutcome>` and records `job_id`, idempotency key, attempt, lease owner/epoch, safe error class and next retry. Acknowledgement occurs only after the owned transaction commits.

## Catalog and public release authority

```ts
interface CatalogService {
  upsertProviderSnapshot(snapshot: SignedProviderSnapshot, operator: OperatorContext): Promise<CatalogVersion>;
  qualifyEndpoint(command: QualifyEndpoint, operator: OperatorContext): Promise<QualificationEvidenceId>;
}

interface ReleaseAuthority {
  propose(input: ReleaseProposalInput, operator: OperatorContext): Promise<ReleaseProposal>;
  approve(id: ReleaseProposalId, releaseOwner: ReleaseOwnerContext): Promise<RouteRelease>;
  startRollout(input: StartRollout, releaseOwner: ReleaseOwnerContext): Promise<RouteRollout>;
  haltOrRollback(input: HaltOrRollback, actor: OperatorContext): Promise<AliasGeneration>;
}
```

Direct releases bind one model provider/model/version/price/capability/endpoint-evidence set. Grad releases consume a signed `QualifiedBundleRef` from Python research control and add family or managed product envelope, price, SLO, placements, rollout and rollback. Node cannot alter the bundle or qualification; Python cannot activate a public alias.

Approval, release insertion, alias generation/outbox and audit commit atomically. Target publication is separate and requires cell attestation; an approved release with no eligible targets remains unavailable rather than resolving elsewhere.

## Trace, analytics and migration domain

### Encrypted trace envelope

Gateway output to the trace stream is `TraceCaptureEvent` with safe routing metadata plus:

```text
envelope_version
trace_id / request_id / organization_id / workspace_id
retention_deadline / capture_class / plaintext_length
ciphertext / nonce / authenticated_data_digest
wrapped_data_key_for_ingest_key / ingest_key_version
payload_schema_version / compression
```

Use a random data-encryption key per trace and an authenticated cipher selected by the crypto package. The gateway wraps that key to a rotating asymmetric ingest public key from Redis. The trace worker unwraps under a purpose-scoped private/KMS-backed role, rewraps/registers the key for trace access and writes ciphertext to S3. Cryptographic algorithm and envelope test vectors are frozen in the crypto package before implementation; no agent chooses one ad hoc inside the gateway.

### Services

```ts
interface TraceRegistryService {
  persistCapture(event: TraceCaptureEvent): Promise<TraceRecord>;
  tombstone(input: DeleteTrace, actor: ActorContext): Promise<Tombstone>;
  requestExport(input: ExportTraces, actor: ActorContext): Promise<ExportJob>;
}

interface TraceGrantService {
  issue(input: TraceAction, actor: ActorContext): Promise<SignedSingleUseGrant>;
}

interface AnalyticsRepository {
  listRequests(scope: AuthorizedScope, query: TraceQuery): Promise<Page<RequestFact>>;
  summarize(scope: AuthorizedScope, query: RollupQuery): Promise<UsageSummary>;
}

interface MigrationService {
  createReplay(input: CreateReplay, actor: ActorContext): Promise<MigrationExperiment>;
  createLiveCanary(input: CreateLiveCanary, actor: ActorContext): Promise<MigrationExperiment>;
  stop(input: StopExperiment, actor: ActorContext): Promise<void>;
}
```

The ClickHouse and Aurora implementations consume the same closed query objects; neither accepts SQL from tRPC. Trace-access validates grant signature/audience/nonce/expiry, atomically consumes it, reloads trace scope and tombstone/key state, reads exactly one object, decrypts and streams with `Cache-Control: no-store`. It cannot list S3 or issue a presigned object URL.

Recommendation states are `opportunity -> replay_candidate -> evaluator_verified -> live_canary_ready -> accepted|rejected|expired`. Only explicit customer commands create experiments. No worker can modify workspace requested-model policy from a recommendation.

## tRPC and REST surface

All list procedures use `{cursor, limit<=100, filters}` and return `{items,nextCursor}`. Mutations accept a bounded `clientMutationId`; financially or externally significant REST routes require `Idempotency-Key`.

| Router | Queries | Mutations |
| --- | --- | --- |
| `session` | `current` | `switchOrganization`, `switchWorkspace` |
| `organizations` | `list`, `get` | `create`, `rename`, `requestClosure` |
| `organizationMembers` | `list`, `invitations` | `invite`, `accept`, `changeRole`, `remove` |
| `workspaces` | `list`, `get`, `effectivePolicy` | `create`, `updatePolicy`, `requestDelete` |
| `workspaceMembers` | `list` | `add`, `changeRole`, `remove` |
| `apiKeys` | `list` | `create`, `rotate`, `revoke` |
| `credits` | `balance`, `transactions`, `topUps` | `createCheckout`, `updateWarnings` |
| `models` | `catalog`, `detail` | `updateWorkspaceAccess` |
| `usage` | `requests`, `summary` | none |
| `traceAccess` | none | `issueViewGrant`, `requestExport`, `deleteTrace` |
| `workloads` | `list`, `detail` | `name`, `merge`, `split` only when supported by evidence |
| `migration` | `candidates`, `experiments` | `createReplay`, `createCanary`, `stop`, `recordDecision` |
| `research` | operator queries proxied to private API | operator commands proxied with signed actor context |
| `audit` | `list` | none |

REST endpoints are `/api/auth/*`, `/webhooks/stripe`, health/readiness and future versioned external management APIs. The Stripe route bypasses browser CSRF/session middleware but requires raw-body signature verification. Cookie-authenticated unsafe methods enforce strict origin/fetch metadata and, where required, an explicit anti-CSRF token.

## UI implementation contract

Each route has a loader/query key, permission guard, skeleton, empty state, error state, optimistic-policy decision and accessibility test. Financial status and raw key display are never optimistic.

```text
/
/keys
/models
/usage
/usage/traces/:traceId
/billing
/settings/organization
/settings/team
/settings/workspaces/:workspaceId
/settings/data
/settings/limits
/operator/research/*
/operator/releases/*
```

The active organization/workspace lives in URL/session selection, not an unscoped global store. Query keys begin with organization/workspace. A switch cancels in-flight queries and clears workspace-scoped client cache. Sensitive detail uses the one-time grant flow and never stores plaintext in browser persistence.

## Database and schema rules

- Drizzle schema expresses columns/types/indexes; reviewed SQL migrations express constraints, triggers, RLS/roles where used and data backfills.
- Migration names are ordered and immutable after main. CI creates an empty DB, migrates up, loads fixtures, upgrades from the previous release snapshot and verifies generated schema drift.
- Use expand/migrate/contract. Application code tolerates old/new shape during rollout; destructive contract runs only after old code is gone.
- Financial, outbox and idempotency unique constraints are correctness mechanisms, not best-effort indexes.
- PostgreSQL roles are purpose-specific: API read/write, financial poster, projector, trace registry, analytics outbox, research service, migration owner and break-glass. The API role cannot post ledger entries directly except through owned stored/domain transaction code.

## Event catalog

All events carry `event_id`, `aggregate_type/id`, `aggregate_version`, `schema_version`, `occurred_at`, `idempotency/business_key`, `correlation_id`, `causation_id` and a typed `PrincipalRef`. Tenant events use workspace principal where applicable; channel/research events never invent tenant IDs.

Seed events:

- tenancy: `OrganizationCreated`, `MembershipChanged`, `WorkspacePolicyChanged`, `ApiKeyChanged`;
- finance: `TopUpCredited`, `RefundPosted`, `ChargebackPosted`, `ReservationCreated`, `UsageSettled`, `FailedRequestCreditRequested`, `LedgerPostingCompleted`, `OrganizationStatusChanged`;
- serving config: `CatalogVersionPublished`, `RouteReleaseApproved`, `AliasHeadChanged`, `CellTargetSetChanged`;
- retained data: `TraceCaptured`, `TracePersisted`, `TraceCaptureSkipped`, `TraceTombstoned`, `TraceDeleted`, `AnalyticsFactReady`;
- migration: `WorkloadProfileChanged`, `RecommendationChanged`, `MigrationExperimentChanged`;
- operations: `ProjectionRebuildRequested/Completed`, `ReconciliationMismatch`, `OperatorActionRecorded`.

Event payloads carry immutable facts/references, not current mutable object snapshots unless the projection contract explicitly requires one. Consumers ignore duplicate IDs and reject unsupported schema versions to a dead letter/closed state.

## Configuration, readiness and shutdown

Config is parsed once into a typed object; unknown production keys and missing required keys fail startup. Environment variables contain references/URLs and secret mounts, not policy that belongs in PostgreSQL.

`/healthz` proves process/event loop only. `/readyz` proves required connection pools, schema compatibility and role-specific dependencies without mutating money. Workers stop leasing jobs, finish/abandon safely, commit/ack owned work, then close pools. API shutdown rejects new traffic, drains bounded requests and never reports a financial mutation successful before commit.

## Verification and junior-agent packages

Required test layers:

- domain examples and fast-check state machines for tenancy, roles, ledger, webhooks, releases, trace/migration states;
- repository tests against PostgreSQL for every uniqueness/scope/transaction invariant;
- Hono `app.request()` tests for middleware, raw webhook, sessions, tRPC errors and idempotency;
- MSW/Testing Library route tests plus Playwright activation/funding/key/usage/privacy flows;
- worker redelivery/crash/lease/property tests with real PostgreSQL/Redis/S3/ClickHouse-compatible fixtures;
- golden event and research-client compatibility tests.

Implement in this order:

1. `CP-00`: IDs/errors/clock/UoW/idempotency/outbox, Drizzle/pg and fixture DB.
2. `CP-01`: Better Auth mount plus organization/default-workspace/membership/authz.
3. `CP-02`: API key lifecycle and Redis projection commands.
4. `CP-03`: ledger/top-up/webhook with model-based tests.
5. `CP-04`: financial consumer/projector/reconciler and operator repair commands.
6. `CP-05`: catalog/public release authority and generated research client.
7. `CP-06`: trace registry/envelope worker/grant/access/delete.
8. `CP-07`: analytics repository/projector and usage UI.
9. `CP-08`: workload/recommendation/experiment state plus UI.
10. `CP-09`: full Vite routes, Playwright and operations.

Each package owns one directory set, adds migrations/events before consumers, and must run its narrow examples/PBT plus `pnpm verify:ts`. No package may add a browser-to-database path, a second tenancy authority or a direct Redis financial mutation from tRPC.

## Source notes

Current official documentation retrieved 2026-07-14 reports Hono's standard Request/Response handler and security middleware, Better Auth's Hono handler and Drizzle/PostgreSQL adapters, and Drizzle's node-postgres/transaction/migration support: [Hono](https://hono.dev/docs), [Hono CSRF](https://hono.dev/docs/middleware/builtin/csrf), [Better Auth installation](https://better-auth.com/docs/installation), [Drizzle PostgreSQL](https://orm.drizzle.team/docs/get-started-postgresql), [Drizzle transactions](https://orm.drizzle.team/docs/transactions), [Drizzle migrations](https://orm.drizzle.team/docs/migrations). These are vendor-reported capabilities; WP-00 pins versions and proves integration before they become repository facts.
