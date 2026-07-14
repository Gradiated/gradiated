# Self-service organization deletion

## Product contract

An organization owner can delete an organization without contacting support. The request immediately stops new inference and administrative mutation, then a durable worker drains financial work, refunds refundable unused credit, cryptographically deletes customer payloads and removes or pseudonymizes product identity. Legally required financial evidence remains inaccessible to the former customer and contains no trace payload.

Deletion is an asynchronous, observable workflow rather than a cascading SQL statement. This is durable correctness, not speculative workflow complexity.

## User journey and API

The console requires a recent reauthentication, the exact organization name and acknowledgement that keys, workspaces, traces and access will be lost. Only an active owner can submit or cancel.

```text
DELETE /api/v1/organizations/{organization_id}
  Idempotency-Key: required
  body: { confirmation_name }
  -> 202 { deletion_id, status, requested_at, execute_after, status_url }

GET /api/v1/organizations/{organization_id}/deletion
  -> current deletion view

DELETE /api/v1/organizations/{organization_id}/deletion
  -> 204 when cancelled before irreversible purge
```

The fixed seed cancellation window is seven days. It is a deployment policy, not an organization-configurable field; `execute_after` is frozen on the request for deterministic recovery. Access and spend stop immediately even during that window. The UI shows pending refund, drain, purge, completion or a specific support-required block.

The endpoint is excluded from generated MCP tools at launch. API documentation still describes it for human-controlled automation.

## Persistent model

Add one workflow table:

| Model | Required fields |
| --- | --- |
| `organization_deletions` | `id`, `organization_id`, `requested_by`, `status`, `requested_at`, `execute_after`, `completed_at?`, `cancelled_at?`, `last_error_code?` |

`status` is `pending | running | blocked | completed | cancelled`. A partial unique index allows at most one `pending|running|blocked` request per organization. `organizations.status` adds `deletion_pending` and `deleted`; do not add duplicated phase flags to organizations/workspaces.

The row exists because completion spans Stripe, active Valkey reservations, S3/KMS, PostgreSQL and delayed object deletion. Repeating the whole workflow must be safe. Audit records retain the action/resource/result with pseudonymous actor identity after completion.

## Workflow

### Request transaction

1. Lock organization and verify active owner plus recent reauthentication.
2. Verify confirmation name and no conflicting deletion.
3. Insert deletion row and set organization `deletion_pending`.
4. Revoke invitations and prevent membership/key/top-up mutations.
5. Append projection/audit/outbox records and commit.
6. Project suspended organization/key/workspace snapshots to Valkey; no new request can reserve.

Existing reservations may finish or expire. Their usage must settle before financial closure.

### Cancellation

Before `execute_after` and before purge starts, cancellation locks the deletion, changes it to `cancelled`, restores organization `active`, and republishes policy. Revoked API keys are not resurrected; owners create replacements. Cancellation is impossible after refund or payload-key destruction begins.

### Execution

The financial worker repeatedly performs idempotent phases:

1. prove there are no active Valkey reservations and financial stream lag for the organization is zero;
2. reconcile balance to the immutable ledger;
3. refund unused refundable credit to original Stripe payments, oldest eligible payment first, and wait for authoritative webhook outcomes;
4. append balanced refund/processor transactions; never edit top-ups or usage;
5. rotate the organization's cache-scope epoch, making prior KV cache unreachable, then let bounded ephemeral cache expire;
6. tombstone every trace, destroy wrapped data keys first, and delete S3 objects/exports;
7. revoke all keys, memberships, OAuth grants, sessions, invitations and external integration credentials;
8. remove workspaces, recommendations/evaluations and non-financial customer metadata under explicit foreign-key rules;
9. redact the organization name and Stripe link, set `deleted`, mark workflow completed, and emit a content-free completion audit.

A positive balance is never silently forfeited. A processor dispute, failed refund or unreconciled reservation sets `blocked` with a stable error code and visible remediation; customer content deletion can continue where financial retention rules permit. Support can resolve the block but cannot skip ledger equality.

## Retention boundary

Delete or cryptographically destroy:

- request/response/tool traces and exports;
- workspace/key/member/invitation records not required as financial evidence;
- recommendations, evaluation payloads and customer-facing analytics;
- sessions, OAuth grants and retained customer identifiers;
- customer-specific cache reachability immediately, then ephemeral bytes by TTL/drain.

Retain for the applicable statutory/payment-dispute period:

- append-only ledger transactions/entries;
- payment event identity, top-up/refund facts and settled usage amounts required to explain charges;
- minimal pseudonymous audit and deletion-completion evidence.

Retained records replace direct display identity with a non-reversible tombstone identifier where foreign keys/accounting permit. They contain no prompt, completion, tool payload, email, API secret or free-form metadata. Exact legal periods are policy/configuration and counsel-reviewed runbooks, not custom per-organization billing periods.

## Failure behavior

- Every external call uses a stable idempotency key derived from deletion and phase.
- Crash/retry may repeat a phase but cannot reactivate access, duplicate a refund or recreate a trace key.
- S3 deletion is verified by inventory/object checks; key destruction denies reads before physical deletion converges.
- Valkey unavailable leaves the organization suspended and blocks completion; it never assumes reservations are gone.
- PostgreSQL/ledger uncertainty blocks completion.
- A deleted organization ID can never be reused or restored.

## Verification

fast-check state models generate request, duplicate request, cancel, top-up webhook, reserve/settle/lease expiry, refund webhook, worker crash and retry. Properties prove:

- one active deletion, idempotent API outcomes and no cancellation after irreversible work;
- no new reservation after request commit;
- all admitted usage settles exactly once before closure;
- balance/ledger equality and no lost/duplicated refund;
- trace detail fails immediately after tombstone/key destruction;
- no membership/session/key/OAuth authorization survives completion;
- retained evidence is payload/PII-free and organization IDs are never reused;
- object/cache cleanup converges under reordered and failed steps.

Integration tests use PostgreSQL, Valkey, MinIO, fake Stripe and KMS envelope fixtures. Staging runs a cryptographic-delete/object-inventory drill before enabling the UI.
