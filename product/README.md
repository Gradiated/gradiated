# Inference gateway product

This workstream specifies a revenue-first inference product with two distribution paths sharing one serving system:

1. customers send OpenAI- or Anthropic-compatible traffic to our gateway and prepay an organization credit pool;
2. external gateways such as OpenRouter list our models and send provider traffic to the same serving API.

The direct gateway is the seed product because it creates an immediate payment surface, customer relationship, and observability loop. Provider integrations follow as distribution adapters, not as a separate product.

## System shape

```text
Vite React console ──tRPC──> Hono control API ──> PostgreSQL ledger/config
       │                         │       │
       │                         │       └──> Stripe top-ups
       │                         └──> Redis projections
       │
OpenAI/Anthropic SDKs ──> Rust gateway ──> owned inference / OpenAI / Anthropic / OpenRouter
                              │
                              └──> Redis only
                                   auth + config + balance reservations
                                   concurrency + Redis Streams usage events

Hono reconciliation worker: Redis Streams ──> PostgreSQL ledger ──> Redis repair
External gateways ──provider protocol──> the same Rust serving surface
```

PostgreSQL is authoritative for organization credits. Every organization has a Default workspace and may create more workspaces with separate keys, members, model/routes, budgets, and concurrency limits. Redis is a durable, versioned projection and the gateway's only internal dependency. The gateway atomically reserves organization credit and nested workspace/key limits before dispatch, restricts organization concurrency near depletion, settles actual usage, and emits an idempotent event to a Redis Stream.

## Planned repository layout

```text
product/
  apps/
    web/                 Vite, React, Tailwind, shadcn/ui
    control-api/         Hono on Node, Better Auth, tRPC, REST/OpenAPI
    control-worker/      Stripe, outbox, Redis projection, reconciliation
  services/
    gateway/             Rust/Axum/Tower gateway and provider adapters
  packages/
    authz/               workspace membership and role policy
    billing/             ledger, top-up, projection, reconciliation domains
    contracts/           checked-in generated TypeScript Protobuf types
    db/                  PostgreSQL schema and migrations
    testkit/             generators, models, fake providers, replay helpers
    ui/                  shadcn configuration and shared app components
  proto/                 canonical internal Protobuf schemas and Buf config
  schemas/               public OpenAPI/JSON Schema and wire fixtures
  tests/
    client-e2e/           official OpenAI and Anthropic SDK tests
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
- [OpenRouter product/architecture spike](docs/OPENROUTER_SPIKE.md)
- [Delegation plan](docs/DELIVERY_PLAN.md)
- [Evidence and decisions](docs/EVIDENCE_AND_DECISIONS.md)
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
