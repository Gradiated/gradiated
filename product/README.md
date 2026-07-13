# Inference gateway product

This workstream specifies a revenue-first, curated inference product with three access modes sharing one serving system:

1. customers send OpenAI-, Anthropic-, or Google-compatible traffic to our gateway and prepay an organization credit pool;
2. customers point an existing gateway such as LiteLLM, Cloudflare, Portkey or Helicone at the same OpenAI-compatible endpoint using their workspace key;
3. external routers such as OpenRouter or Hugging Face natively list selected Grad inference and send traffic with a dedicated distribution-channel credential.

The direct gateway is the seed product because it creates an immediate payment surface, customer relationship, trace/intelligence loop, and migration path. Customers can keep an explicitly curated direct provider/model (`openai/...`, `anthropic/...`, `google/...`) or select first-party owned inference as `grad/<effort>/<speed>`, with effort `low|medium|high|max` and speed `flex|standard|fast|turbo`. It is not a provider marketplace.

## System shape

```text
Vite React console ──tRPC──> Hono control API ──> PostgreSQL authority
       │                         │       ├──> ClickHouse trace analytics
       │                         │       │
       │                         │       └──> Stripe top-ups
       │                         └──> Redis projections
       │
OpenAI/Anthropic/Google SDKs ──> Rust gateway ──> direct providers
                              │       │                 └──> OpenRouter upstream (operator-only)
                              │       └──> AWS inference edge ──> external GPU cells
                              │
                              └──> Redis only for internal state/control
                                   auth + config + balance reservations
                                   route releases + concurrency + usage events

Hono reconciliation worker: Redis Streams ──> PostgreSQL ledger/outbox ──> Redis repair
Trace analytics projector: PostgreSQL outbox ──> ClickHouse Cloud ──> Hono trace/workload UI
Encrypted trace worker: Redis trace stream ──> private S3 payload ──> workload/recommendation processor
Customer gateways ──workspace key──────> the same Rust serving surface
Native listings ────channel credential─> the same Rust serving surface
```

PostgreSQL is authoritative for organization credits, distribution-channel receivables, authorization, model qualification, route releases, desired capacity/lease history, trace registry/tombstones and workload/experiment control state. Encrypted raw traces live in private lifecycle-managed S3; ClickHouse Cloud is a replayable, content-free analytical projection for trace lists, charts and workload/model summaries. Every organization has a hidden Default workspace and may create more with separate keys, members, model/data policy, budgets and concurrency. Redis is the gateway's only synchronous internal state/control dependency; direct model APIs and the AWS inference edge are upstream serving dependencies. Direct requests stay on their exact curated model provider/model; Grad requests stay on the exact owned release in their effort/speed cell. Grad fleet CRDs/controllers in AWS EKS reconcile native or managed-Kubernetes capacity providers without fake Nodes or a global cluster. Product Intelligence retains bounded encrypted traces by default and suggests—but never performs—evidence-backed migrations to Grad. Private/No Retention is available per workspace/request and suppresses durable payload traces while retaining tenant-isolated ephemeral KV/prefix caching.

The model research factory continuously explores the entire Grad stack: weights and factory-produced architecture, custom operators, kernels/runtime, serving/cache policy, parallelism/topology and hardware mapping. Its unit of promotion is one signed content-addressed `ModelStackBundle`, not a checkpoint. Fable supplies fast hypotheses and functional-twin/model-surgery tooling; Sol supplies fail-closed experiment/evidence discipline. Independent qualification runs the exact bundle through full-stack and production-like cell gates before a human-approved `RouteRelease` can move a stable family head such as `grad/glm-5.2/fast` or a managed head such as `grad/medium/standard`. Immutable `@release` pins remain reproducible; live requests never consult research systems.

## Planned repository layout

```text
product/
  apps/
    web/                 Vite, React, Tailwind, shadcn/ui
    control-api/         Hono on Node, Better Auth, tRPC, REST/OpenAPI
    control-worker/      Stripe, outbox, Redis projection, reconciliation
    trace-worker/        encrypted trace drain, retention, deletion, export
    trace-projector/     PostgreSQL outbox to ClickHouse analytical facts
    recommendation-worker/ workload profiles, replay, migration experiments
    trace-access/        one-object audited decrypt/read service
    fleet-controller/    PostgreSQL intent, fleet CRDs, broker/target projection
    research-worker/     Temporal campaigns, agent leases, execution and cleanup
  services/
    gateway/             Rust/Axum/Tower gateway and model-provider adapters
    inference-edge/      stable Rust streaming edge for owned Grad serving
    cell-agent/          external-cell bootstrap, router, runtime lifecycle
    capacity-provider/   isolated native/managed-K8s allocation reconcilers
  packages/
    authz/               workspace membership and role policy
    billing/             ledger, top-up, projection, reconciliation domains
    contracts/           checked-in generated TypeScript Protobuf types
    db/                  PostgreSQL schema and migrations
    workloads/           trace metadata, profiles, recommendations, experiments
    research-domain/     campaigns, specs, evidence, candidates and qualification
    research-artifacts/  S3 CAS, canonical bundles, OCI and attestations
    research-testkit/    factory state models, fakes, generators and replay
    testkit/             generators, models, fake providers, replay helpers
    ui/                  shadcn configuration and shared app components
  proto/                 canonical internal Protobuf schemas and Buf config
  schemas/               public OpenAPI/JSON Schema and wire fixtures
  tests/
    client-e2e/           official OpenAI, Anthropic, and Google SDK tests
    conformance/          protocol fixtures
    properties/           cross-language golden and model traces
  docs/                  product, architecture, operations, and work packets
```

## Documents

- [Product specification](docs/PRODUCT_SPEC.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API, data, and contract design](docs/API_AND_DATA_CONTRACTS.md)
- [Billing, Redis admission, and reconciliation](docs/BILLING_AND_REDIS.md)
- [Testing and CI](docs/TESTING_AND_CI.md)
- [Security and operations](docs/SECURITY_BILLING_OPERATIONS.md)
- [Gateway and provider integrations](docs/INTEGRATIONS.md)
- [Open distribution targets, packages, and harnesses](docs/DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md)
- [Model lanes, Grad effort/speed, traces, and migration](docs/MODEL_LANES_AND_MIGRATION.md)
- [Owned Grad inference architecture](docs/OWNED_INFERENCE_ARCHITECTURE.md)
- [Model research factory to production](docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md)
- [Multi-provider GPU fleet evidence](docs/MULTI_PROVIDER_GPU_EVIDENCE_2026-07-13.md)
- [Kubernetes capacity-provider abstraction](docs/KUBERNETES_PROVIDER_ABSTRACTION_2026-07-13.md)
- [Full architecture audit](docs/ARCHITECTURE_AUDIT_2026-07-13.md)
- [ClickHouse trace analytics decision and evidence](docs/CLICKHOUSE_TRACE_ANALYTICS_DECISION.md)
- [OpenRouter complete feature inventory and decisions](docs/OPENROUTER_FEATURE_DECISIONS.md)
- [OpenRouter product/architecture spike](docs/OPENROUTER_SPIKE.md)
- [Delegation plan](docs/DELIVERY_PLAN.md)
- [Evidence and decisions](docs/EVIDENCE_AND_DECISIONS.md)
- [Current model/data architecture decision](../docs/decisions/0003-provider-grad-effort-speed-and-traces.md)
- [ClickHouse trace analytics ADR](../docs/decisions/0004-clickhouse-trace-analytics.md)
- [Multi-provider inference ADR](../docs/decisions/0005-multi-provider-spot-inference.md)
- [Kubernetes provider abstraction ADR](../docs/decisions/0006-kubernetes-provider-abstraction.md)
- [Research-to-production model lifecycle ADR](../docs/decisions/0007-research-production-model-lifecycle.md)
- [AWS infrastructure, Kubernetes, CI/CD, local stack, and `grad` plan](../infra/README.md)
- [Current handoff](HANDOFF.md)

## One-command agent verification

The implementation must provide these root commands and run them in GitHub Actions. They are an agent interface, not work delegated to the product owner.

```sh
pnpm verify:ts
pnpm test:pbt
cargo nextest run --workspace
cargo test -p gateway-pbt
pnpm contracts:check
pnpm test:conformance
pnpm test:e2e:fake
grad infra check
grad helm check
```

Protected main/nightly workflows add `pnpm test:e2e:providers`. Failed properties upload seed, shrink path, generated command trace, and a copy-paste replay command.
