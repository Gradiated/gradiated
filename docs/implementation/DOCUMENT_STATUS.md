# Architecture document status

Status: canonical precedence and reading map

This map prevents an implementation agent from treating dated exploration as a current build contract. When two documents disagree, use the highest applicable row below and open a contract issue rather than blending them.

## Precedence

1. Accepted ADRs as amended by their explicit supersession notes.
2. [System manual](../SYSTEM_MANUAL.md), [contract catalog](CONTRACT_CATALOG.md), [physical data model](DATA_MODEL.md), [package boundaries](PACKAGE_BOUNDARIES.md), [work packages](WORK_PACKAGES.md), [verification matrix](VERIFICATION_MATRIX.md), and [operations manual](OPERATIONS_MANUAL.md).
3. Current subsystem blueprints listed below.
4. Evidence, spikes and dated audits, which may inform a new ADR but are not implementation authority.

The [simplicity review](../SIMPLICITY_REVIEW.md) is the amendment that removes seed dependencies/state/fields from older accepted decisions. ADR-0008 replaces tRPC with Hono REST and adds generated MCP/self-service organization deletion. ADR-0009 makes multi-node topology launch-critical for owned releases that require it.

## Current subsystem blueprints

| Area | Current implementation documents |
| --- | --- |
| product and journeys | `product/docs/PRODUCT_SPEC.md`, `product/docs/ARCHITECTURE.md` |
| control plane and API | `product/docs/CONTROL_PLANE_IMPLEMENTATION.md`, `product/docs/REST_OPENAPI_MCP_IMPLEMENTATION.md`, `product/docs/API_AND_DATA_CONTRACTS.md` |
| public inference | `product/docs/PUBLIC_INFERENCE_PROTOCOLS.md`, `product/docs/GATEWAY_IMPLEMENTATION.md`, `product/docs/INTEGRATIONS.md` |
| billing/admission | `product/docs/BILLING_AND_REDIS.md` |
| traces/intelligence/deletion | `product/docs/MODEL_LANES_AND_MIGRATION.md`, `product/docs/ORGANIZATION_DELETION.md` |
| owned inference | `product/docs/OWNED_INFERENCE_ARCHITECTURE.md`, `product/docs/OWNED_INFERENCE_IMPLEMENTATION.md`, `product/docs/MULTI_NODE_INFERENCE.md` |
| research lifecycle | `product/docs/RESEARCH_FACTORY_IMPLEMENTATION.md`; active code/handoff under `research/factory/` remains its workstream's authority |
| distribution | `product/docs/DISTRIBUTION_IMPLEMENTATION.md`, `product/docs/INTEGRATIONS.md` |
| testing/release | `product/docs/TESTING_AND_CI.md`, `product/docs/DELIVERY_PLAN.md` |
| AWS/Terraform/Kubernetes | all undated files under `infra/docs/`; `infra/docs/DELIVERY_PLAN.md` sequences them |

## Evidence and historical documents

These files remain valuable evidence but must not be copied into implementation without reconciling them against the canonical set:

| Document | Use only for | Known superseded content |
| --- | --- | --- |
| `product/docs/OPENROUTER_SPIKE.md` | dated vendor feature research | breadth/current vendor behavior may have changed |
| `product/docs/OPENROUTER_FEATURE_DECISIONS.md` | keep/simplify/defer product rationale | canonical launch protocol and data choices win |
| `product/docs/DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md` | provider/distribution research and harness references | signed partner contracts and required protocol breadth remain unvalidated |
| `product/docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md` | research lifecycle design evidence | current Python factory and simplified persistent model win |
| `product/docs/MULTI_PROVIDER_GPU_EVIDENCE_2026-07-13.md` | provider capability evidence | fleet CRD proposal removed |
| `product/docs/KUBERNETES_PROVIDER_ABSTRACTION_2026-07-13.md` | rejected abstraction history | no fleet CRDs/central provider API |
| `product/docs/CLICKHOUSE_TRACE_ANALYTICS_DECISION.md` | ClickHouse reintroduction evidence | PostgreSQL is seed analytics authority |
| `product/docs/SECURITY_BILLING_OPERATIONS.md` | historical threat/runbook prompts | arbitrary risk modes/periods, ClickHouse and old trace pipeline removed |
| `product/docs/ARCHITECTURE_AUDIT_2026-07-13.md` | prior gap inventory | canonical coverage ledger replaces it |
| `product/docs/EVIDENCE_AND_DECISIONS.md` | dated evidence ledger | accepted ClickHouse/fleet details superseded |

Research reports under `research/sol/` and `research/fable/` are measured/analytical workstream evidence, not product architecture authority. Their nearest `AGENTS.md`, handoff, and report govern continued research execution.

## Explicit seed exclusions

An occurrence in a historical file does not authorize any of these:

- tRPC, ClickHouse, Kafka, a service mesh, Crossplane, fleet CRDs, a stretched Kubernetes cluster, or self-managed Karpenter;
- Chat Completions, Embeddings, Google GenerateContent, hosted stateful OpenAI resources, arbitrary provider marketplace/BYOK, or customer-defined routing graphs;
- custom billing periods, adaptive risk profiles, per-workspace wallets, mutable release price/state, a second user table, or generic metadata/event/principal models;
- direct third-party-router access to cells, bypass of Grad gateway admission, or public inference-router/cell credentials;
- automated research-to-public promotion without independent exact-scope qualification and human authorization.

Reintroduction requires the trigger defined in the simplicity review, measured evidence, an ADR, an owned work packet, and updates to contracts/tests/runbooks.
