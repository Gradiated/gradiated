# Billing, Redis admission, and reconciliation

This document is the implementation contract for money movement. Examples use integer micro-USD. No path may convert through floating point.

## Financial model

PostgreSQL contains a balanced, append-only ledger. An organization's posted credit is derived from entries, not trusted from a mutable cache. Recommended logical accounts are customer credit liability, Stripe clearing/cash, inference revenue, promotional credit expense, refunds/chargebacks, and provider-cost accrual. The exact accounting chart requires accountant review before production, but engineering invariants do not:

- each transaction balances to zero in one currency;
- each external/internal business event has one unique idempotency key;
- entries never update/delete after posting;
- reversals refer to and offset an original transaction;
- the organization available balance equals posted credits minus posted sell charges and holds represented by the chosen projection checkpoint.

Maintain a transactionally updated materialized organization balance row for efficient locking and projection, but verify it against ledger sums continuously. It is a derivative, not a separate authority. Workspaces and API keys have spend/budget windows but never independent funded balances in seed.

## Organization billing and workspace limit policy

The organization billing projection contains:

```text
billing_mode: prepaid | invoiced (later)
status: active | reconciling | suspended | closed
risk_mode: normal | restricted | suspended
spendable_microusd
billing_epoch
projection_version
normal_max_concurrency
low_balance_threshold_microusd
low_balance_org_max_concurrency   default 1
safety_reserve_microusd
```

Each workspace projection contains status, curated model-provider/model and Grad effort/speed access, Product Intelligence or Private/No Retention data mode, retention policy, an opaque monotonic cache epoch, normal and low-credit concurrency caps, maximum request reserve/output, and zero or one budget for each `daily`, `weekly`, `monthly`, and `lifetime` interval. API keys can have more restrictive equivalents. Period state tracks both settled spend and active reserved spend. Organization/workspace deletion or a privacy-boundary change first closes new admission, then advances the cache epoch so no new request can address old ephemeral blocks.

Low credit is calculated from organization projected spendable credit after the proposed reservation. It is not a stale flag. `risk_mode` is an explicit operator/risk override: restricted applies the low-credit organization cap regardless of balance; suspended admits nothing. Effective policy is the intersection/minimum of organization, workspace, and key constraints. Workspace/key budgets cap use of shared organization credit and do not allocate money.

## Top-up state machine

States: `created -> checkout_pending -> paid -> credited`, with terminal/side paths `expired`, `failed`, `refunded`, and `charged_back`.

1. Authorized organization owner/billing member creates a top-up with organization, allowed amount/currency, and idempotency key.
2. API stores intent then creates a Stripe Checkout Session carrying only opaque IDs in metadata.
3. Browser return displays `processing`; it never changes credit.
4. Webhook handler verifies signature against raw body, inserts unique `payment_events`, locks the intent/payment object, and validates amount, currency, organization binding, and allowed transition.
5. One PostgreSQL transaction posts balanced organization credit entries, advances intent, increments organization billing projection version, inserts audit and outbox records, and marks the event handled.
6. Worker atomically applies versioned credit to Redis. Dashboard reads posted and projected status through API.
7. Duplicate or reordered events return success after proving the existing effect. Conflicting duplicates quarantine the intent and alert.

Refunds and chargebacks always append compensating organization transactions. Project the debit/restriction immediately; if it exceeds spendable credit, record explicit debt and set organization `risk_mode=suspended`, closing all workspaces.

## Maximum-cost estimation

Before admission, determine a conservative sell reserve:

```text
candidate_reserve = checked_add(
  safety_reserve,
  priced_known_input_units +
  priced_declared_max_output_units +
  priced_bounded_tool/cache/reasoning exposure
)

require candidate_reserve <= effective_max_request_reserve
reserve = candidate_reserve
```

Every direct model-provider/model and Grad effort/speed release has an immutable published sell SKU. The capability planner must prove the input bound: use the exact pinned tokenizer where available; otherwise use a tested conservative byte/item upper bound plus published image/audio/file units. Price the reserve as uncached input, because a cache hit cannot be guaranteed, and use the smaller valid request/model output cap. Grad settlement may apply the immutable cached-input SKU only from authoritative terminal runtime units. Cache counters or locality are not billing authority.

Model-provider buy-cost differences and failed-attempt costs are our margin risk, not a variable customer charge. A retry cannot change sell-price version or add failed upstream units to customer usage. Direct traffic retries only the exact provider/model/version; Grad traffic retries only owned targets for the exact effort/speed release. Speed never silently downgrades. Each release separately bounds attempt count and internal maximum buy exposure.

If the protocol lacks a safe output bound, impose a documented workspace/model default and validate it, or reject the request. Do not silently truncate input or output. Unknown price, stale route/price version, arithmetic overflow, or reserve above policy fails before provider dispatch. Tests must prove reserve is at least the sell charge for every valid response and bounded attempt sequence within declared limits.

## Atomic admission transition

Implement as one versioned Redis Function/Lua script scoped to `{organization_id}`. Inputs include key digest, resolved organization/workspace/key IDs, canonical provider/model or Grad effort/speed, route release/decision, capability/data-policy/native-tier decision, config/price versions, request/reservation IDs, reserve, lease deadline, now/window IDs, and idempotency token.

The operation:

1. validates organization billing epoch/status/risk mode and projected key binding to the organization/workspace;
2. validates workspace/key status, provider/model or Grad-product access, effective data policy, immutable catalog/route/price version, capability decision, and request reserve/output limits;
3. returns the existing result for an identical idempotent reservation;
4. requires organization `spendable >= reserve + safety_reserve`;
5. computes `post_reserve_spendable`;
6. requires every workspace/key interval to have `settled + active_reserved + reserve <= limit`; missing limits mean unlimited at that layer;
7. chooses organization concurrency cap: zero if suspended/reconciling; low-credit cap if restricted or post-reserve is below threshold; normal cap otherwise;
8. chooses workspace/key caps from effective normal/low-credit policy and requires organization, workspace, and key in-flight below every applicable cap;
9. subtracts reserve from organization spendable; adds reserve to each applicable workspace/key window; increments all applicable in-flight counters; creates an active reservation/lease;
10. appends a `ReservationCreated` event to the organization Redis Stream carrying workspace/key attribution;
11. returns an opaque admission token with organization epoch and reservation ID.

All mutations and `XADD` either succeed or do not happen. Expected outcomes are `admitted`, idempotent `already_admitted`, `insufficient_credits` (402), `low_balance_concurrency_limit` (429), policy/key errors, or `admission_unavailable` (503).

This prevents bursts across several workspaces from spending the same last credits: every request for one organization serializes through the organization-local atomic transition. The low-credit organization cap defaults to one; workspace/key caps can only make it stricter.

## Lease and streaming behavior

Reservations have a finite lease renewed by a gateway heartbeat while an upstream request is active. A gateway crash does not immediately refund because the provider may still have incurred cost. An orphan sweeper waits a provider-specific grace period, inspects all durable evidence, and performs an idempotent conservative settlement or marks the organization `reconciling` for repair.

For long streams:

- renew lease before half its duration;
- meter chunks locally where possible without logging payloads;
- stop/finalize on client disconnect according to provider cancellation semantics;
- never issue a second cost-bearing fallback after response bytes have been exposed;
- if projected actual charge approaches reserve, atomically extend the reserve before further optional spend or cancel upstream.

## Atomic settlement transition

Inputs include admission token/epoch, reservation ID, final metered units, actual sell amount, provider cost evidence, terminal state, `usable_output_delivered`, and event ID.

The organization-local operation:

1. fences stale epoch and validates reservation identity;
2. returns prior result for a duplicate event/settlement;
3. checked-compares actual sell amount with reserved amount;
4. returns unused reserve to organization spendable and removes the same amount from active-reserved workspace/key windows, then adds actual sell amount to settled period spend; or atomically takes an overage from organization credit and every applicable limit if allowed;
5. if an unavoidable overage cannot be funded, records negative debt metadata and restricts/suspends immediately;
6. marks reservation settled, decrements organization/workspace/key in-flight exactly once, removes lease;
7. appends `RequestSettled` with organization/workspace/key attribution to the same Redis Stream;
8. returns final balance/status metadata.

Cancellation, model-provider/cell rejection, timeout, and partial response are settlement reasons, not excuses to delete a reservation. Evidence quality determines whether sell amount is measured, provider-reported, or conservative estimate. An exact-lane capacity rejection after reserve but before output releases unused reserve, decrements concurrency exactly once, and records zero sell usage plus any internal failed-attempt buy evidence. Protocol-usable partial output is charged at measured fixed-SKU units; after output the gateway never transparently replays. Settlement records whether usable output crossed the customer boundary; it does not issue a mutable in-place refund.

## Failed-request customer credit

After PostgreSQL posts the original settlement, an idempotent policy evaluates whether no usable output was delivered and the terminal state is eligible. If so, the same worker transaction appends a `failed_request_credit` ledger transaction and `usage_correction` that reverses the customer sell amount exactly once. The provider buy-cost accrual remains unchanged. The business key is derived from the original usage charge, so redelivery, reconciliation, or repeated terminal signals cannot double-credit.

Protocol validation, customer cancellation after usable output, moderation/refusal, deliberate disconnect abuse, and malformed requests are not automatically eligible. Uncertain midstream delivery is conservatively classified from the gateway's byte/event boundary and retained as a safe reason code. Reconciliation includes both original charges and posted corrections; it never rewrites the original event.

## Migration experiment accounting

Automated Product Intelligence profiling and offline replay on owned inference are product-development/marketing expense and never create a customer reservation or usage charge. They use a separate operator budget, capacity pool and event identity so they cannot be confused with customer traffic.

Customer-approved live canaries are ordinary requests funded by the organization and require `x-grad-migration-experiment`. Before admission, deterministic bucketing chooses baseline or Grad, resolves its fixed price, and includes experiment ID/bucket in the atomic transition. The experiment has maximum request/micro-USD caps in addition to ordinary limits; actual selected route price is disclosed. Console state alone never enrolls traffic. Shadow experiments are unbilled because output is not delivered, but retain an operator cost budget and require approval. Duplicate events cannot charge or consume either budget twice.

## Distribution-channel receivable admission

OpenRouter and other downstream distribution channels are not customer organizations and never use organization credit. PostgreSQL owns each channel contract, credential references, immutable channel price book, approved Grad releases, credit/receivable ceiling, aging/risk state, concurrency/rate/capacity limits and reconciliation terms. Balanced `channel_receivable_transactions` record revenue, invoice, payment, credit and adjustment effects. A projector publishes a versioned `ChannelAccountProjection` to Redis.

The gateway runs a separate atomic channel command that authenticates the channel credential, verifies model/release/price/policy versions, reserves receivable exposure and concurrency, deduplicates the downstream request ID, and appends a channel event before dispatch. Keys and commands use a channel hash tag and cannot address organization balance or workspace policy. Channel traffic has its own cache trust domain and defaults to content-free SLO/metering records rather than first-party Product Intelligence traces.

Settlement releases the channel reserve, posts measured units/revenue once, decrements concurrency, and emits a `ChannelSettlementEvent`. A worker posts the receivable ledger and reconciles downstream request IDs, units, errors, credits and invoices/auto-top-ups. Exceeded exposure, overdue invoices, contract suspension or reconciliation drift closes new channel admission while existing requests can settle. Property tests interleave customer and channel traffic and prove neither domain can mutate the other's balances, credentials, limits, traces or cache scope.

## Stream consumption and PostgreSQL posting

The worker uses Redis Streams consumer groups. For each event:

1. decode and validate Protobuf, epoch, monotonic sequence, and schema version;
2. begin PostgreSQL transaction;
3. insert unique organization event receipt; if already committed, acknowledge and stop;
4. post usage charge and balanced ledger transaction for settlements, or persist reservation diagnostic/checkpoint for admission events;
5. increment the organization reconciliation checkpoint, persist workspace/key usage windows, and insert any outbox/audit records;
6. commit;
7. acknowledge the stream entry.

Pending entries are claimed after worker lease expiry. Poison events move to a retained dead-letter Redis Stream only after bounded attempts and immediately place the organization in `reconciling`; operators can inspect metadata and replay after repair. Retention must exceed maximum outage plus investigation window and is protected by memory/lag admission gates.

## Reconciliation equations

At a common organization checkpoint, compare:

```text
postgres_organization_posted_balance
  = total_posted_credits - total_posted_sell_charges
    + posted_failed_request_credits + other_posted_adjustments

expected_redis_org_spendable
  = postgres_organization_posted_balance
    - active_redis_reservations
    - settled_redis_events_not_yet_posted_to_postgres
    + credits_committed_in_postgres_not_yet_projected
```

For every workspace/key period, separately prove `redis_settled + redis_active_reserved` equals the PostgreSQL posted usage plus the same fenced pending-event/active-reservation cut. The implementation may choose an equivalent algorithm, but all terms use one organization epoch/version so concurrent traffic is not mistaken for drift.

Continuous reconciliation runs per event/batch; full organization plus nested workspace/key reconciliation runs at least hourly and after failover/deploy. A nonzero unexplained delta, event sequence gap, old pending entry, overage debt, or projection-version regression transitions the organization to `reconciling`. Small known in-flight lag can remain active only inside a documented amount/age envelope. Exceeding it suspends new cost-bearing admission across its workspaces.

## Projection rebuild

1. Set organization Redis status to `reconciling` in a new fenced epoch; all workspace admissions stop.
2. Allow bounded active requests to settle or conservatively close them.
3. Drain/post all usable stream events and record unresolved reservations.
4. Recompute organization posted balance and versioned organization/workspace/key auth, policy, and period windows from PostgreSQL.
5. Build replacement Redis keys under the new epoch, including explicit unresolved holds.
6. Atomically swap/activate the projection and verify readback hashes.
7. Run reconciliation. Reopen only on zero unexplained delta and complete event sequence.
8. Audit operator, reason, old/new epoch, hashes, and result.

## Required property invariants

Generated command sequences include organization/default-workspace creation, additional workspaces/keys/limits, top-up, duplicate/reordered webhook, direct provider/model pins, Grad effort/speed release/canary/rollback, trace-mode tightening, migration replay/shadow/live-canary budget, cross-workspace concurrent reserve, lease renewal, stream cancel, settle, duplicate settle, usable/no-usable-output correction, provider overage, refund, chargeback, worker redelivery, Redis failover checkpoint, and rebuild.

For every sequence:

- ledger entries balance and arithmetic never overflows;
- one business event has at most one financial effect;
- each eligible no-usable-output charge has exactly one compensating sell credit and ineligible/delivered-output charges have none;
- in-flight equals active reservations;
- organization spendable plus active holds agrees with the fenced financial/event cut;
- no request is dispatched without a reservation event;
- organization low-credit and workspace/key concurrency never exceed selected caps;
- workspace/key settled plus reserved spend never exceeds a configured hard period cap except the explicit unavoidable-overage path, which closes the organization;
- status/epoch fencing prevents stale reopen or stale settlement mutation;
- only explicit overage/chargeback paths can create debt, and they immediately restrict admission;
- reconciliation either proves organization and nested window equality or leaves the organization closed.
- route rollback never reprices or invalidates an already admitted reservation.
- direct traffic never settles under another provider/model/version and Grad traffic never settles under another effort/speed SKU;
- internal replay/shadow traffic cannot debit organization credit, while live-canary traffic cannot exceed its experiment plus ordinary billing limits.

Both fast-check domain models and Rust Redis state-machine tests assert these invariants. Cross-language generated traces allow the same minimized failure sequence to be replayed in both implementations.
