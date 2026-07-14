# Product architecture

## Product shape

Grad is a revenue-first inference provider and gateway:

1. An organization prepays credit and gets a Default workspace.
2. A workspace creates API keys, limits and data policy.
3. OpenAI-compatible clients call curated direct models or `grad/<effort>/<speed>` aliases.
4. Direct requests preserve the selected provider/model; Grad aliases route only to qualified owned releases.
5. Encrypted traces are retained by default for analytics/recommendations; no-retention is opt-in and still uses ephemeral tenant-salted KV cache.
6. Selected owned releases are also distributed through OpenRouter and later curated routers, using isolated channel credentials through the same public gateway.

The first paid slice is one direct model through the Grad gateway. Owned inference and channel listings follow after billing/admission correctness is proven.

## Authority map

| Concern | Authority | Projection/execution |
| --- | --- | --- |
| identity/session | Better Auth tables in PostgreSQL | browser session cookie |
| org/workspace/key policy | PostgreSQL | versioned Valkey snapshot |
| credit/top-ups/usage | PostgreSQL double-entry ledger | balance snapshot + Valkey reservation state |
| model/release/alias | PostgreSQL | signed/versioned Valkey catalog |
| traces/retention/grants | PostgreSQL metadata + encrypted S3 payload | indexed PostgreSQL queries |
| fleet intent/leases/cells | PostgreSQL | Rust provider reconciliation + router live state |
| research evidence/releases | PostgreSQL + signed S3/ECR artifacts | Temporal execution history |
| operational health | metrics/logs | dashboards/alerts |

Valkey contains only rebuildable hot policy/catalog/balance projections, active reservations, concurrency and bounded streams. Temporal contains research execution history but cannot approve evidence or releases. Kubernetes owns no business object. ClickHouse and fleet CRDs are absent.

## Deployables

```text
web: static Vite/React/shadcn artifact

control Node image:
  api | financial | intelligence | trace-access roles

Rust images:
  gateway | inference-router | fleet | cell-agent

research Python image:
  api | temporal-workflow/activity | evaluator

qualified model runtime:
  signed OCI image + content-addressed bundle
```

Roles share an image only when code/dependencies align; identities, deployments and scaling remain separate where IAM or failure domain differs.

## Request path

```text
client
  -> Rust gateway
     -> validate protocol/model/policy
     -> atomic Valkey authenticate + reserve + concurrency acquire
     -> direct provider OR private inference router
     -> normalize streaming/usage
     -> atomic settle/refund + concurrency release
     -> append billing event
     -> optionally append encrypted trace envelope
financial role -> idempotent PostgreSQL ledger transaction
trace role -> encrypted S3 payload + PostgreSQL metadata
```

The gateway cannot query PostgreSQL or call Stripe. If Valkey reservation is unavailable or uncertain, admission fails closed. It never routes a requested direct model to another model/provider, and never routes a Grad alias outside its immutable qualified release set.

Low-balance protection is atomic admission policy, not an asynchronous flag. The snapshot includes available credit plus workspace/key concurrency/monthly limits. The Lua/function transaction computes a stricter low-balance concurrency cap and reserves worst-case cost before provider spend.

## Billing

Billing is organization-level. Workspaces/keys constrain spend but have no wallet. A fixed-chart double-entry ledger records top-ups, usage, refunds, chargebacks and corrections as immutable balanced transactions. `organization_balances` is a locked/rebuildable projection used to publish Valkey credit.

Stripe checkout creates a `topup_intent`; only a verified, idempotently processed webhook posts credit. Gateway reservation is not revenue. Settlement produces one authoritative usage record and ledger transaction; retries/reordered/duplicate events converge. Custom daily/weekly/lifetime periods are absent. Seed limits are optional monthly workspace/key caps plus concurrency.

## Catalog and routing

`model_definitions` represent customer-visible direct or Grad IDs. `model_releases` freeze capabilities, context/output limits, prices and bounded pre-output retry count by digest. `release_endpoints` bind direct releases to qualified provider endpoints; `capacity_targets` express owned placement. `model_aliases` map each stable model definition to immutable releases with deterministic canary allocation.

Direct example:

```text
openai/gpt-<curated-id>
anthropic/claude-<curated-id>
google/gemini-<curated-id>
```

Owned examples begin sparsely:

```text
grad/medium/standard
grad/low/fast
grad/high/quality
```

The grammar may support more effort/speed values than the published catalog. An unpublished combination returns an explicit model-not-found/capability response. Release promotion never mutates an existing digest; it publishes a new release and updates an alias after qualification.

## Protocols

The public gateway implements OpenAI-compatible `/v1/models`, chat/completions where required, responses and embeddings only when a listed model supports them. Anthropic-native compatibility is added only for proven customer demand; the first-party surface remains OpenAI-compatible.

Provider adapters normalize a closed canonical request/stream/usage/error model. Unsupported fields fail explicitly. No silent parameter dropping, prompt rewriting, response healing or privacy downgrade. Official OpenAI/Anthropic/Google clients exercise the public endpoint; gateway integrations use published base-URL/API-key recipes.

Cross-language Protobuf is limited to gateway hot projection/events, gateway-to-cell serving and research API refs/commands. Public OpenAPI/JSON fixtures remain separate wire authorities. TypeScript-only domain/outbox types do not become universal Protobuf events.

## Traces and intelligence

Product Intelligence is default. The gateway strips credentials, applies size/content allowlists, encrypts trace payload with a public key and appends ciphertext to a bounded Valkey stream. A least-privilege role stores ciphertext in S3 and metadata/grants/tombstones in PostgreSQL. Trace-access authorizes every detail request and decrypts only the selected object.

No-retention suppresses payload persistence before the trace stream, but usage/financial metadata and ephemeral KV cache remain. Deletion first revokes PostgreSQL access and destroys/tombstones wrapped keys, then removes S3 objects asynchronously. PostgreSQL lists/charts/workload summaries use bounded tenant/time queries; add measured rollups before considering another database.

Recommendations are evidence, never autonomous routing. A recommendation progresses through observed opportunity, replay/shadow/canary evidence and operator/customer approval. Replays are unbilled; canaries have explicit authority, budgets and stop conditions. No state transition silently changes production traffic.

## Owned inference

The gateway forwards an admitted immutable release to the private inference router. The router chooses a healthy exact-release cell from authenticated live state; it never queries provider lifecycle APIs. External cells can be native VMs, managed Kubernetes or managed endpoints but expose one cell-agent/runtime protocol.

PostgreSQL capacity sources/targets/allocations/cells are durable state. Rust provider drivers reconcile leases idempotently and use ownership tags; an independent sweeper detects orphans. Every cell verifies signed bundle/runtime digests, reports exact-release attestation, maintains tenant/channel/release/retention-class salted KV cache and returns authoritative usage.

Spot interruption permits retry only before output and within deadline/budget. After output, fail consistently and settle once. Unknown cleanup freezes new acquisition for that provider source.

## Research factory and release

Python owns research domain transitions and model/operator work. Temporal owns resumable workflows, timers, retries and cancellation. PostgreSQL stores programs, hypotheses, campaigns, experiment specs/runs, evidence, bundles and qualifications. S3/ECR store immutable artifacts/runtime images.

An always-on program selects experiments from explicit hypotheses and budgets, runs CPU/GPU activities, seals positive or negative evidence, constructs a bundle and sends it through independent qualification. Derived queues, Pareto fronts and open-question arrays are computed from primary rows, not persisted as competing truth.

The factory may change PyTorch model code, kernels, quantization, batching, cache layout and runtime implementation. Production consumes only the language-neutral signed OCI/local-protocol artifact. Qualification covers quality, protocols, hardware/runtime compatibility, cache, load, failure, security and cleanup. Node release authority alone publishes customer aliases.

## Security boundaries

- API keys are shown once, stored as peppered digests and scoped to one workspace.
- All tenant queries include organization/workspace predicates and database constraints.
- Provider/channel/customer credentials are purpose-separated and never logged.
- Channel traffic has isolated credentials, balance/receivable accounts, cache salt and trace policy.
- Images/bundles are digest-pinned and signed; promotion records qualification evidence.
- Gateway/provider/router/fleet enrollment/driver/research/trace roles have distinct IAM/network capabilities. External cells generate keys and receive short-lived AWS Private CA identity through one-use allocation-bound enrollment.
- Payloads, cache contents, secrets and high-cardinality customer identifiers are forbidden in telemetry.

## Simplicity constraints

The seed deliberately has no custom route-builder UI, arbitrary provider marketplace, per-workspace wallet, custom billing periods, generic event/principal schema, ClickHouse projector, fleet CRD, model-family/product/pricebook hierarchy, or runtime-language mode. Reintroduce only after a concrete consumer or measured failure meets [the trigger](../../docs/SIMPLICITY_REVIEW.md).
