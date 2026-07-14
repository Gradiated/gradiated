# Product architecture handoff

## Current design

Grad starts as a prepaid OpenAI-compatible gateway with organizations, a Default workspace, workspace keys/limits and one curated direct model. Billing is organization-level through an immutable fixed-chart double-entry ledger. The Rust gateway depends synchronously only on Valkey for versioned snapshots, atomic reservations/concurrency and bounded streams; PostgreSQL is durable authority and Stripe webhooks are top-up authority.

Product Intelligence retains encrypted traces by default in S3 with PostgreSQL metadata/analytics. No-retention is an explicit tighter mode and still uses ephemeral tenant-salted KV cache. ClickHouse is absent until a measured PostgreSQL benchmark fails.

Owned Grad inference uses immutable `grad/<effort>/<speed>` aliases, signed bundles/runtime images, a private inference router and isolated external GPU cells. PostgreSQL owns allocation leases; Rust provider drivers reconcile native or managed-Kubernetes providers directly. There are no fleet CRDs.

The research factory is Python/PyTorch/Triton with a private API and Temporal workflows/activities. PostgreSQL/S3 own programs, hypotheses, experiments, evidence and artifacts; Temporal owns execution history only. Independent qualification precedes Node-controlled release publication.

OpenRouter and later routers call the same public Grad gateway with isolated channel credentials. They do not bypass Grad admission or use customer prepaid balances.

## Important retained tools

- Durable double-entry ledger: product correctness, not optional complexity.
- Temporal: avoids a bespoke durable research scheduler/retry engine.
- KEDA: scales workers from queue/stream age with static correctness floors.
- Terragrunt: reduces environment/module repetition without owning runtime state.
- Kueue/JobSet: only for research jobs that genuinely need Kubernetes quota/gang scheduling.
- Kyverno: small runtime-safety policy set, never business policy.

## Important removals

- ClickHouse/projector and named analytics subsystem;
- fleet CRDs/custom Kubernetes application state;
- self-managed Karpenter when EKS Auto Mode qualifies;
- workspace wallets and arbitrary billing periods;
- universal principal/event schemas and duplicated model/product/pricebook layers;
- persisted derived research queues/frontiers/open-question arrays;
- runtime-language modes and speculative provider/route optionality.

## Read and build order

1. [Simplicity review](../docs/SIMPLICITY_REVIEW.md)
2. [Product architecture](docs/ARCHITECTURE.md)
3. [API/data contracts](docs/API_AND_DATA_CONTRACTS.md)
4. [Control](docs/CONTROL_PLANE_IMPLEMENTATION.md), [gateway](docs/GATEWAY_IMPLEMENTATION.md), [owned inference](docs/OWNED_INFERENCE_IMPLEMENTATION.md), [research](docs/RESEARCH_FACTORY_IMPLEMENTATION.md), [distribution](docs/DISTRIBUTION_IMPLEMENTATION.md)
5. [Delivery packages](docs/DELIVERY_PLAN.md) and [testing](docs/TESTING_AND_CI.md)
6. Infrastructure [platform blueprint](../infra/docs/PLATFORM_IMPLEMENTATION.md)

First milestone is WP-00–04: a funded request through one direct model with exact ledger reconciliation and official-client CI. Do not make owned inference, a router listing or research automation block that milestone.

## Required verification

```sh
python3 tools/devex/check.py
pnpm verify:ts
pnpm test:pbt
cargo nextest run --workspace
uv run --project research/factory pytest
pnpm contracts:check
pnpm test:e2e:fake
git diff --check
```

Protected jobs add the cheapest real-provider requests and bounded GPU qualification when secrets/budgets exist. Every PBT failure records a replay seed and shrink path.
