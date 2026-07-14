# Billing, Valkey admission and reconciliation

Status: current seed implementation contract

This document specifies money movement and hot-path admission. PostgreSQL is durable financial authority. Valkey is the gateway’s synchronous serving projection, reservation authority for in-flight requests and protected delivery path to PostgreSQL. Money is checked integer micro-USD; floating point is forbidden.

## 1. Financial model

The organization is the customer and billing boundary. Workspaces and keys have attribution, optional monthly spend limits and concurrency limits, but never independent wallets. USD is the only seed currency.

Top-up policy v1 accepts whole-USD amounts from $10 through $10,000 inclusive; the UI may offer presets but the server validates the range and currency. The single workspace/key spend window is the UTC calendar month identified as `YYYY-MM`; changing timezone or adding rolling/custom periods requires a new product contract, Valkey schema and reconciliation proof.

The fixed chart contains the minimum platform, organization and channel accounts needed for:

- processor cash/clearing;
- customer prepaid-credit liability;
- inference usage revenue;
- refunds, chargebacks, promotional/failed-request credits and adjustments;
- channel receivable/revenue/payment where a native distribution contract exists.

`ledger_transactions` and `ledger_entries` are immutable. Every transaction balances to zero in USD and has one unique business key/source identity. Refunds, chargebacks and corrections are compensating transactions; they never update prior entries or usage.

`organization_balances` and `channel_balances` are transactionally updated, lockable and rebuildable projections. They are the only persisted ledger totals. The ledger remains authority.

## 2. Top-up state machine

```text
created -> completed | failed | expired
```

Creating Checkout creates a `topup_intent`, not credit. The verified Stripe webhook transaction:

1. verifies the raw-body signature before parsing business fields;
2. inserts the unique provider event or confirms the prior equal result;
3. locks and validates the top-up intent, organization, USD amount and external object;
4. performs the one allowed state transition;
5. on completion, posts one balanced processor/customer-credit transaction and updates the locked balance projection;
6. appends audit and account-projection outbox work;
7. commits before returning 2xx.

Same event/object with conflicting immutable input is an incident and never overwrites the first effect. Raw webhook bodies and secrets are not retained in application logs or ordinary fixtures.

## 3. Conservative maximum exposure

Before reserve, the gateway computes the maximum customer sell amount for the admitted immutable release:

```text
max_sell = fixed_request_fee
         + max_input_tokens * input_price_micros
         + max_uncached_input_tokens * applicable_cache_delta
         + max_output_tokens * output_price_micros
```

The exact formula is release- and protocol-versioned and uses checked arithmetic/rounding. Input token count comes from the qualified tokenizer or a conservative upper bound. Output count is the smaller of request, release and protocol limits. Unsupported/unbounded input fails before reserve.

The reserve must cover every allowed attempt under the release’s customer sell contract. Provider buy-risk is a separate company budget; it does not permit charging above the admitted sell maximum.

## 4. Organization Valkey keyspace

All organization-local mutable keys use one hash tag so the reserve/settle script is atomic:

```text
gw:{organization_id}:account
gw:{organization_id}:workspace:<workspace_id>
gw:{organization_id}:key:<key_id>
gw:{organization_id}:reservation:<reservation_id>
gw:{organization_id}:billing
```

Global immutable catalog keys are versioned release/alias snapshots. Channel keys use a disjoint `gw-channel:{channel_id}:...` namespace and ACL; organization scripts cannot address them.

The account snapshot contains status, available/held amounts and version/epoch. Workspace/key snapshots contain only active status, binding, one optional monthly spend limit, concurrency, data mode/model policy and version. Do not add daily/weekly/lifetime windows, independent workspace balance, adaptive risk state or arbitrary policy JSON.

## 5. Atomic reserve

Input:

- internal request/reservation ID and immutable admission-input digest retained in reservation state for conflict detection;
- credential candidate/binding;
- organization/workspace/key or channel/credential IDs;
- requested public model ID, immutable release digest, alias generation and expected price/policy versions;
- conservative reserve micro-USD;
- current monthly-window identity and bounded lease expiry.

One script/function:

1. validates compatible epoch and monotonic projections;
2. authenticates active unexpired credential binding;
3. validates organization/channel, workspace and key status;
4. validates model allowlist, data policy, release/price/capability decision and output/reserve bounds;
5. returns the existing reservation for equal idempotent input and rejects conflicting input;
6. requires sufficient organization available credit or channel exposure;
7. requires optional workspace/key monthly settled plus active reserve plus new reserve within limit;
8. applies organization/channel, workspace and key concurrency limits;
9. when available-before-reserve is below the fixed deployment multiplier of this request’s hold, applies the fixed organization-wide low-balance cap, initially one;
10. moves amount from available to held, increments counters and creates reservation/lease;
11. appends the minimal `ReservationCreated` event in the same atomic transition;
12. returns an opaque reservation token bound to epoch and identity.

Expected outcomes are admitted/already-admitted, authentication/policy/model errors, insufficient credit, monthly/concurrency/low-balance limit, idempotency conflict or admission unavailable. No provider/router invocation occurs without an admitted token.

The low-balance multiplier/cap are deployment constants with property tests, not mutable organization/workspace fields.

## 6. Lease and live request behavior

A finite reservation lease is renewed while a cost-bearing request remains active. A gateway crash does not immediately release the hold because upstream spend may have occurred. The sweeper waits the bounded evidence/grace period and performs the same idempotent terminal transition or suspends the account for reconciliation.

The gateway meters locally without logging payload. Client disconnect follows the exact provider cancellation behavior. After usable output, no transparent retry is allowed. Because initial reserve is conservative, the seed does not extend a reservation for optional additional spend; it stops before exceeding admitted bounds. An observed actual sell above reserve is an invariant incident.

## 7. Atomic settlement

Input:

- reservation token/epoch and request/reservation identity;
- terminal state and event ID;
- actual token usage and sell micro-USD;
- bounded actual target/attempt/provider-cost evidence required for usage posting;
- `usable_output_delivered` and cancellation owner.

One script/function:

1. validates epoch/token/reservation state;
2. returns the prior result for an equal duplicate and rejects a conflict;
3. checked-compares actual sell to reserve;
4. if actual exceeds reserve, suspends account admission, retains reservation/evidence and returns an invariant error—never clamps or invents debt metadata;
5. otherwise returns unused hold, records actual settled monthly spend and decrements concurrency once;
6. marks reservation settled, removes lease and appends minimal `UsageSettled` atomically;
7. returns final projected balance/status.

Timeout, cancellation, capacity rejection and partial output are terminal settlement reasons. A zero-sell request still emits a terminal usage event. Lease abandonment uses the same once-only terminal guard and is distinguishable from measured settlement.

## 8. Billing stream posting

The financial worker uses consumer groups and at-least-once delivery:

1. decode and validate schema/identity/version;
2. begin PostgreSQL transaction;
3. insert unique event/business receipt or confirm prior equal effect;
4. upsert the operational `usage_record` and, for settlement, post one balanced customer/channel revenue transaction and update the locked balance;
5. append audit/outbox and commit;
6. acknowledge only after commit;
7. publish a newer account/policy projection where required.

Pending entries are reclaimed after worker lease expiry. A poison/conflicting event places only the affected account in reconciliation, preserves content-safe evidence and is never acknowledged merely to reduce lag. Billing stream capacity/headroom has priority over trace capture.

## 9. Failed-request credit

The immutable usage record includes usable-output, terminal cause, cancellation owner and correction history. Policy may append an idempotent compensating sell credit for eligible failures. It never mutates original usage or erases provider buy cost.

Malformed/policy/authentication requests, deliberate disconnect patterns and requests that delivered usable output are not automatically free. Abuse policy can suspend the organization for review but does not create mutable risk/balance buckets.

## 10. Distribution-channel accounting

A native channel is not a customer organization. It has separate channel credentials, approved catalog prices, exposure/outstanding projection and concurrency. The same balanced transaction implementation is parameterized by channel account scope, but keyspaces, account rows, scripts and foreign-key domains are disjoint.

Reserve checks exposure rather than prepaid credit. Settlement posts channel revenue/receivable evidence once. `channel_statements` is implemented only when the first signed OpenRouter contract requires its period/reconciliation evidence; Grad does not build a configurable billing-period engine.

Exceeded exposure, overdue/suspended contract or unexplained reconciliation drift closes new channel admission while existing requests can settle. Channel traffic defaults to content-free usage unless the signed channel policy explicitly defines a compatible trace contract.

## 11. Reconciliation

At a common checkpoint, compare:

```text
posted_balance = ledger reconstruction
expected_valkey_available
  = posted_balance
    - active reservations
    - settled events not yet posted
    + committed credits not yet projected
```

For the one workspace/key monthly window, compare PostgreSQL posted usage with Valkey settled plus active reserve at the same epoch/checkpoint. For channels, compare ledger outstanding, active exposure and unposted settlements.

An unexplained delta suspends only the affected organization/channel, pages and blocks deletion/refund completion. Reconciliation never updates immutable ledger history.

## 12. Fenced projection rebuild

1. Stop or fence new admission for the affected scope.
2. Drain/claim durable billing events and record the cut.
3. Build a new epoch from PostgreSQL account, policy, key, alias and release authority.
4. Add conservative holds for reservations whose terminal effect is uncertain.
5. compare ledger/balance, policy/catalog versions, event cut and holds;
6. atomically switch the active epoch;
7. retain old epoch until every reservation/stream/rollback window closes;
8. reopen canary admission and observe reconciliation.

Never delete all Valkey keys and republish a clean balance that forgets in-flight liability.

## 13. Required properties

- every PostgreSQL transaction balances and business keys are idempotent;
- balance projection always equals ledger reconstruction;
- Checkout without verified webhook never adds credit;
- no accepted reserves overspend organization credit/channel exposure or monthly limits;
- concurrent workspaces cannot spend the same last credit;
- low-balance cap is applied atomically and customer configuration cannot loosen it;
- reserve atomically creates hold, counters, lease and event or does nothing;
- each reservation reaches settled or abandoned once;
- duplicate reserve/settle/webhook/stream delivery has one effect and conflicting duplicate fails closed;
- actual-over-reserve suspends and preserves evidence;
- consumer crash at every DB/ack boundary converges;
- organization and channel commands cannot mutate each other’s keys/accounts;
- rebuild never forgets uncertain active exposure.

Use fast-check for ledger/top-up/control models and proptest-state-machine against real Valkey for reserve/settle/lease behavior. Every failure emits a replay artifact.
