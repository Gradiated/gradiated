# Testing and CI

## Objective

Agents and CI—not the product owner—must be able to verify every change. Tests prioritize irreversible failures: wrong money, unauthorized access, silent protocol changes, retained data against policy, cross-release routing, leaked capacity and irreproducible research.

## Test stacks

| Stack | Unit/example | Property/state model | Integration/E2E |
| --- | --- | --- | --- |
| TypeScript | Vitest | fast-check | Testcontainers, Playwright, MSW/fakes |
| Rust | cargo nextest | proptest + proptest-state-machine | real Valkey/PostgreSQL, fake providers/cells |
| Python | pytest | Hypothesis | Temporal test server, tiny model/runtime, fake compute |
| contracts | Buf/schema/OpenAPI lint + description gate | generated value/event/REST sequences | cross-language goldens, generated client and MCP conformance |
| infrastructure | Terraform/Helm/policy tests | lifecycle/fault models where useful | Kind and budgeted staging drills |

Every property failure prints the seed, minimal counterexample/shrink path and exact replay command. CI uploads a small sanitized replay artifact. Fixed failures become deterministic regression fixtures.

## Test tiers

### PR/main bounded tier

- formatting, lint, type/build and dependency/license/security checks;
- unit tests and short deterministic PBT budgets;
- generated-contract/schema/OpenAPI drift;
- fake provider/Stripe/cell and real disposable PostgreSQL/Valkey integration;
- public-protocol and gateway-to-cell goldens;
- Vite accessibility/component smoke and fake-client E2E;
- Terraform/Terragrunt/Helm/Kyverno/Kind checks for changed infrastructure.

### Main/nightly deep tier

- longer PBT/model-state budgets with a seed matrix;
- concurrency, cancellation, retry/reorder and failover fault injection;
- Temporal replay/crash/cancellation tests;
- trace retention/delete/export and PostgreSQL query/load fixtures;
- fleet/provider-driver/cell lifecycle chaos;
- load/leak/soak tests and dependency-update compatibility.

### Protected paid tier

- cheapest qualifying OpenAI, Anthropic and Google requests through the public Rust gateway using official clients;
- OpenRouter/channel smoke when credentials/contract exist;
- bounded external GPU allocation/runtime/cache/stream/preemption/cleanup qualification;
- staging Aurora/Valkey/EKS/Temporal recovery drills.

Paid jobs have explicit secret presence, spend cap, timeout, concurrency cap, synthetic prompts, cleanup assertion and sanitized artifacts. Missing optional credentials skip with a classified result; they never weaken deterministic CI.

## Core property suites

### Identity and tenancy

- signup yields one organization owner and exactly one Default workspace;
- all workspace/member/key/trace queries remain within organization lineage;
- invitation acceptance/retry/expiry cannot create duplicate membership;
- revoked/expired keys and removed members cannot authorize;
- role checks are monotonic and deny unknown actions.
- self-service organization deletion suspends admission immediately, cannot duplicate refunds/purge, cannot resurrect revoked keys and leaves only allowed pseudonymous financial evidence.

### REST, OpenAPI and MCP

- every route has stable operation ID, auth/idempotency classification, success/errors and descriptions for every exposed field;
- generated OpenAPI, TypeScript client, Scalar/agent docs and MCP manifest come from the same route registry and have no drift;
- mutation retries under the same idempotency key return one result; conflicting inputs fail;
- browser cookies require CSRF/origin checks while OAuth bearer calls preserve actor/organization scope;
- MCP can invoke only explicitly exposed operations through REST middleware; destructive/sensitive routes remain unreachable;
- MCP annotations match route metadata but server authorization remains decisive.

### Ledger and top-ups

- every ledger transaction balances to zero in USD;
- business key/source identity is idempotent;
- top-up credit follows one verified Stripe event regardless of duplicate/reordered delivery;
- refunds/chargebacks/corrections preserve history and balance rebuild equality;
- `organization_balances` equals fixed ledger account balance after arbitrary valid sequences;
- workspace/key monthly limits constrain organization credit but never create a wallet.

Use a reference in-memory fixed-chart model and generate commands such as create intent, receive event, reserve, settle, refund, chargeback, correct, retry and crash at transaction boundaries.

### Valkey admission and billing

- auth + reserve + concurrency acquisition is atomic;
- rejected requests spend nothing and leak no slot;
- accepted requests cannot exceed available credit plus explicitly bounded reservation exposure;
- low balance applies the stricter concurrency cap atomically;
- settle/refund is idempotent under duplicate/reordered terminal events;
- timeout/cancel/provider failure follows frozen pre/post-output charge rules;
- snapshot epoch rebuild never makes stale policy newer;
- financial stream replay produces one PostgreSQL transaction.

Run the same model against pure Rust state and a real Valkey script/function. Inject connection loss before/after acknowledgement to prove fail-closed uncertainty and reconciliation.

### Protocol and provider adapters

- OpenAI Responses Create and Anthropic Messages official-client profiles pass streaming/non-streaming, tools, structured output/reasoning where qualified, usage and native errors;
- streaming and non-streaming canonical outputs agree;
- chunk ordering/finish/usage/errors are valid under arbitrary provider chunk boundaries;
- unsupported capabilities fail before provider spend;
- direct model/provider identity never changes;
- Grad alias resolves only to an active qualified immutable release;
- cancellation/deadline/backpressure cannot double settle;
- arbitrary headers/tool payloads do not leak to logs or traces outside allowlist.
- Responses `store: true`/stateful fields and unsupported Anthropic beta/hosted-tool fields reject before reserve at launch.

Use official wire fixtures plus generated canonical requests. Each adapter declares capabilities and must pass a shared conformance suite; no adapter-specific exception silently weakens semantics.

### Traces and intelligence

- no-retention produces usage metadata but no payload/trace-stream/S3 object;
- retained content is encrypted before leaving gateway memory and credentials are stripped;
- trace list/detail/export/delete is tenant/grant/retention constrained;
- tombstone/key destruction denies detail before object cleanup converges;
- trace-stream outage/backpressure cannot consume protected billing headroom;
- PostgreSQL analytics equal authoritative sampled usage and remain bounded by tenant/time;
- recommendation state cannot publish routing; replay is unbilled; canary cannot exceed authority/budget/stops.

There is no ClickHouse/projector test matrix. Add one only with the reintroduction ADR.

### Catalog and releases

- release digest fixes capabilities, prices, direct endpoints/owned marker, retry count and artifact refs;
- alias canary assignment is deterministic and reversible;
- unpublished effort/speed combinations fail explicitly;
- release endpoint must be qualified for exact release/capabilities;
- rollback changes alias, never mutates a release;
- settled usage retains the admitted release/price despite later catalog changes.

### Owned inference and fleet

- no ready/routable cell without short-lived allocation identity and exact-release signed attestation;
- one-use bootstrap tokens cannot replay; certificate renewal requires current identity and active allocation;
- router cannot dispatch across release digest or to draining/expired cells;
- provider acquire/release is idempotent under timeout after side effect;
- lease fencing prevents two reconcilers from creating untracked capacity;
- cleanup is never `confirmed` without provider proof; uncertainty freezes acquisition;
- provider/Kubernetes discovery is absent from request path;
- interruption retries only before output and settles once;
- KV cache key includes tenant/channel/release/retention-class and cache-layout epoch; no-retention still hits cache but persists no content.
- a multi-node cell is never ready until every unique rank joins and exact topology/fabric/collective checks pass;
- partial acquire, duplicate rank, member loss and uncertain per-member cleanup fence the whole cell and cannot leak a provider resource;
- gateway/router behavior is identical for one- and multi-node cells and never exposes ranks/provider members.

Test provider-independent state first, then fake native/managed-Kubernetes APIs. Kind tests only the latter; no fleet CRDs exist.

### Research factory

- program/hypothesis/campaign/spec/run/evidence transitions respect authority/version/budget;
- experiment specs are immutable once run; sealed evidence cannot change;
- identical canonical manifests produce identical digests across Python/TS/Rust;
- Temporal workflow replay is deterministic and activity side effects are idempotent;
- cancellation/crash seals or classifies work and cleans resources within timeout;
- negative results retain scope/provenance and are queryable;
- tensor/operator transformations preserve declared shape/dtype/numerical/error properties;
- qualification covers exact bundle/runtime/hardware and alone can make a release proposal eligible;
- Temporal history, derived rankings or agent opinions cannot approve a release.

Tiny deterministic models/fixtures run in ordinary CI. Real GPU tests are protected and scope results to exact hardware/runtime/intervention.

## End-to-end scenarios

Fake CI must cover:

1. signup -> Default workspace -> top-up webhook -> key -> funded direct request -> ledger/trace UI;
2. low balance with concurrent requests -> bounded admissions -> exact refunds/settlement;
3. no-retention request -> cache use -> no payload object -> usage visible;
4. provider stream cancel/failure before and after output -> frozen retry/charge outcome;
5. control/Aurora outage -> existing snapshot serving -> financial replay convergence;
6. Grad alias -> exact cell -> preemption -> safe retry/failure -> one settlement;
7. provider-driver timeout/orphan -> observation/sweeper -> no leaked untracked resource;
8. research negative experiment -> sealed evidence -> no promotion;
9. qualified challenger -> operator approval -> canary alias -> rollback;
10. OpenRouter channel request -> isolated admission/cache/trace -> statement reconciliation.
11. owner requests organization deletion -> admission closes -> usage drains -> balance refunds -> traces cryptographically delete -> access cannot return.
12. exact multi-node Grad release -> all-rank readiness -> worker loss -> cell fence/pre-output retry or post-output failure -> one settlement -> zero-orphan cleanup.

## CI workflow

```text
checkout
  -> devex/path/secret scan
  -> parallel TS / Rust / Python / contracts / infra bounded jobs
  -> fake E2E
  -> build SBOM + sign immutable artifacts on main
  -> update GitOps digest after qualification
  -> optional protected provider/GPU/recovery jobs
```

Main pushes are the normal workflow. Required checks run before deployment; failures stop promotion and create actionable artifacts. Real-provider keys are environment secrets unavailable to untrusted code. Prompts are synthetic and responses are not uploaded except minimal redacted conformance facts.

## Coverage discipline

Coverage percentage is not the gate. Each changed invariant/state transition requires an example and, where combinatorial, a property/model test. Mutants or fault injection should demonstrate that critical tests fail when balance checks, tenant predicates, release checks, retention gates, lease fencing or cleanup proof are removed.

Flaky tests are product defects: quarantine only with issue, owner, diagnosis artifact and expiry. Timeouts are bounded; resource cleanup is asserted even on failure.

## Agent commands

```sh
grad test unit
grad test pbt --seed <seed>
grad test e2e --profile fake
pnpm verify:ts
cargo nextest run --workspace
uv run --project research/factory pytest
pnpm contracts:check
grad infra check
grad helm check
```

Until commands are implemented, agents invoke and record the exact underlying tools. The owner is not expected to run anything locally.
