# Inference gateway product

Grad is a revenue-first curated inference gateway plus owned inference product:

1. customers call an OpenAI-compatible endpoint with a workspace key and prepaid organization credit;
2. customer gateways such as LiteLLM/Cloudflare/Portkey/Helicone use that same endpoint/key;
3. OpenRouter may natively list selected Grad-owned releases and call the same gateway with an isolated channel credential.

Direct model IDs preserve exact provider/model identity. Owned products use sparse `grad/<effort>/<speed>` aliases beginning with `grad/medium/standard`. Product Intelligence retains encrypted traces by default for usage/workload/recommendation features; no-retention is an explicit tighter mode and still uses isolated ephemeral KV cache.

## Reduced system

```text
Vite/shadcn -> Hono/tRPC control roles -> PostgreSQL
                           |              authoritative business, fleet,
                           +-> Stripe     research and seed analytics state
                           +-> S3         encrypted traces/artifacts
                           +-> Valkey projections

OpenAI-compatible clients -> Rust gateway -> curated direct provider
                                  |  |
                                  |  +-> Valkey reserve/settle only
                                  +-> inference router -> external GPU cell

Python research roles -> Temporal activities -> CPU/GPU providers
                      -> PostgreSQL evidence + S3/ECR bundle
                      -> independent qualification -> Node release approval
```

The seed has PostgreSQL, Valkey and S3/ECR as internal durable services, with Temporal dedicated to research execution. Terragrunt, KEDA, Kueue/JobSet where needed and a small Kyverno policy set reduce custom operations code without owning product state. ClickHouse, fleet CRDs, self-managed Karpenter and a universal event model are deliberately absent; their reintroduction requires measured evidence in [the simplicity review](../docs/SIMPLICITY_REVIEW.md).

## Planned source layout

```text
product/
  apps/
    web/                  Vite/React/Tailwind/shadcn
    control/              Hono/tRPC and api/financial/intelligence/trace-access roles
  services/
    gateway/              public Rust serving/admission/provider modules
    inference-router/     private external-cell connection/dispatch
    fleet/                SQL planner and curated provider drivers
    cell-agent/           bundle/runtime/cache/local scheduler
  packages/
    domain/ db/ authz/ contracts/ crypto/ testkit/ ui/
  proto/                  only cross-language hot serving/Redis contracts
  schemas/                public protocol and bundle JSON schemas
  tests/                  conformance, PBT and official-client E2E

research/factory/         Python API/workflow/activity/evaluator, PyTorch/Triton lab,
                          bundle construction and qualification
```

## Read order

1. [Startup architecture](../docs/STARTUP_ARCHITECTURE.md)
2. [Simplicity review, dependency budget and minimal model](../docs/SIMPLICITY_REVIEW.md)
3. [Coverage ledger](../docs/IMPLEMENTATION_COVERAGE.md)
4. [Product architecture](docs/ARCHITECTURE.md)
5. [API/data contracts](docs/API_AND_DATA_CONTRACTS.md)
6. [Control plane](docs/CONTROL_PLANE_IMPLEMENTATION.md)
7. [Gateway](docs/GATEWAY_IMPLEMENTATION.md)
8. [Owned inference](docs/OWNED_INFERENCE_IMPLEMENTATION.md)
9. [Research factory](docs/RESEARCH_FACTORY_IMPLEMENTATION.md)
10. [Distribution](docs/DISTRIBUTION_IMPLEMENTATION.md)
11. [Delivery plan](docs/DELIVERY_PLAN.md)
12. [Testing/CI](docs/TESTING_AND_CI.md) and [handoff](HANDOFF.md)

Dated spikes/audits and ADRs remain evidence/history. Where they conflict with the current simplicity review or implementation blueprints, the current documents above win.

## Agent verification contract

```sh
pnpm verify:ts
pnpm test:pbt
uv run --project research/factory pytest
cargo nextest run --workspace
pnpm contracts:check
pnpm test:conformance
pnpm test:e2e:fake
grad infra check
grad helm check
```

Protected jobs add real provider/client/GPU tests only with secrets, budgets and cleanup contracts. Failed properties emit seed, shrink path and a one-command replay.
