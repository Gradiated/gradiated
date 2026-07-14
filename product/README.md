# Inference gateway product

Grad is a revenue-first curated inference gateway plus owned inference product:

1. customers call an OpenAI-compatible endpoint with a workspace key and prepaid organization credit;
2. customer gateways such as LiteLLM/Cloudflare/Portkey/Helicone use that same endpoint/key;
3. OpenRouter may natively list selected Grad-owned releases and call the same gateway with an isolated channel credential.

Direct model IDs preserve exact provider/model identity. Owned products use sparse `grad/<effort>/<speed>` aliases beginning with `grad/medium/standard`. Product Intelligence retains encrypted traces by default for usage/workload/recommendation features; no-retention is an explicit tighter mode and still uses isolated ephemeral KV cache.

## Reduced system

```text
Vite/shadcn -> Hono REST/OpenAPI roles -> PostgreSQL
                           |              authoritative business, fleet,
                           +-> Stripe     research and seed analytics state
                           +-> S3         encrypted traces/artifacts
                           +-> Valkey projections

Responses/Messages clients -> Rust gateway -> curated direct provider
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
    control/              Hono REST/OpenAPI and api/financial/intelligence/trace-access/MCP roles
  services/
    gateway/              public Rust serving/admission/provider modules
    inference-router/     private external-cell connection/dispatch
    fleet/                SQL planner and curated provider drivers
    cell-agent/           one/multi-node bundle/runtime/cache/local scheduler
  packages/
    api-contracts/ control-client/ domain/ db/ authz/ contracts/ crypto/ testkit/ ui/
  openapi/                generated control OpenAPI 3.1 artifact
  proto/                  only cross-language hot serving/Redis contracts
  schemas/                public protocol and bundle JSON schemas
  tests/                  conformance, PBT and official-client E2E

research/factory/         Python API/workflow/activity/evaluator, PyTorch/Triton lab,
                          bundle construction and qualification
```

## Read order

1. [Canonical system manual](../docs/SYSTEM_MANUAL.md) and [Mermaid system views](../docs/SYSTEM_DIAGRAMS.md)
2. [Cross-system contracts](../docs/implementation/CONTRACT_CATALOG.md), [physical data model](../docs/implementation/DATA_MODEL.md), [package boundaries](../docs/implementation/PACKAGE_BOUNDARIES.md), [work packages](../docs/implementation/WORK_PACKAGES.md), [verification](../docs/implementation/VERIFICATION_MATRIX.md) and [operations](../docs/implementation/OPERATIONS_MANUAL.md)
3. [Simplicity review, dependency budget and minimal model](../docs/SIMPLICITY_REVIEW.md)
4. [Coverage ledger](../docs/IMPLEMENTATION_COVERAGE.md)
5. [Product architecture](docs/ARCHITECTURE.md) and [API/data contracts](docs/API_AND_DATA_CONTRACTS.md)
6. [Control plane](docs/CONTROL_PLANE_IMPLEMENTATION.md)
7. [REST/OpenAPI/MCP](docs/REST_OPENAPI_MCP_IMPLEMENTATION.md), [organization deletion](docs/ORGANIZATION_DELETION.md) and [public protocols](docs/PUBLIC_INFERENCE_PROTOCOLS.md)
8. [Gateway](docs/GATEWAY_IMPLEMENTATION.md), [owned inference](docs/OWNED_INFERENCE_IMPLEMENTATION.md) and [multi-node inference](docs/MULTI_NODE_INFERENCE.md)
9. [Research factory](docs/RESEARCH_FACTORY_IMPLEMENTATION.md)
10. [Distribution](docs/DISTRIBUTION_IMPLEMENTATION.md)
11. [Testing/CI](docs/TESTING_AND_CI.md), [delivery plan](docs/DELIVERY_PLAN.md) and [handoff](HANDOFF.md)

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
