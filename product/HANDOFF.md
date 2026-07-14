# Product architecture handoff

## Current design

Grad starts as a prepaid gateway with OpenAI Responses and Anthropic Messages, organizations, a Default workspace, workspace keys/limits and curated direct models. Billing is organization-level through an immutable fixed-chart double-entry ledger. The Rust gateway depends synchronously only on Valkey for versioned snapshots, atomic reservations/concurrency and bounded streams; PostgreSQL is durable authority and Stripe webhooks are top-up authority.

The control plane is Hono REST, not tRPC. Described Zod v4 contracts generate OpenAPI 3.1, Scalar/agent docs, the Vite client and an allowlisted OAuth MCP adapter. Organization deletion is self-service, immediately suspends admission and uses a durable refund/purge workflow.

Product Intelligence retains encrypted traces by default in S3 with PostgreSQL metadata/analytics. No-retention is an explicit tighter mode and still uses ephemeral tenant-salted KV cache. ClickHouse is absent until a measured PostgreSQL benchmark fails.

Owned Grad inference uses immutable `grad/<effort>/<speed>` aliases, signed bundles/runtime/topology images, a private inference router and isolated external GPU cells. A cell may contain one or many nodes but is always one routing/failure/cache unit. PostgreSQL owns allocation/member leases; Rust provider drivers reconcile native or managed-Kubernetes providers directly. There are no fleet CRDs.

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

1. [Canonical system manual](../docs/SYSTEM_MANUAL.md), [diagrams](../docs/SYSTEM_DIAGRAMS.md) and [parallel implementation manual](../docs/implementation/README.md)
2. [Contract catalog](../docs/implementation/CONTRACT_CATALOG.md), [physical data model](../docs/implementation/DATA_MODEL.md), [package boundaries](../docs/implementation/PACKAGE_BOUNDARIES.md), [work packages](../docs/implementation/WORK_PACKAGES.md), [verification](../docs/implementation/VERIFICATION_MATRIX.md) and [operations](../docs/implementation/OPERATIONS_MANUAL.md)
3. [Simplicity review](../docs/SIMPLICITY_REVIEW.md)
4. [Product architecture](docs/ARCHITECTURE.md) and [API/data contracts](docs/API_AND_DATA_CONTRACTS.md)
5. [Control](docs/CONTROL_PLANE_IMPLEMENTATION.md), [REST/OpenAPI/MCP](docs/REST_OPENAPI_MCP_IMPLEMENTATION.md), [organization deletion](docs/ORGANIZATION_DELETION.md), [gateway protocols](docs/PUBLIC_INFERENCE_PROTOCOLS.md), [owned inference](docs/OWNED_INFERENCE_IMPLEMENTATION.md), [multi-node](docs/MULTI_NODE_INFERENCE.md), [research](docs/RESEARCH_FACTORY_IMPLEMENTATION.md), [distribution](docs/DISTRIBUTION_IMPLEMENTATION.md)
6. Infrastructure [platform blueprint](../infra/docs/PLATFORM_IMPLEMENTATION.md)

The first revenue milestone is canonical waves W0–W4 through `INT-00`: funded Responses and Messages requests through curated direct models with exact ledger reconciliation and official-client CI. Do not make owned inference, a router listing or research automation block that revenue milestone. Multi-node is nevertheless required before public owned Grad inference.

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
