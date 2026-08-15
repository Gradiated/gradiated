# ADR-0010: Direct inference product with OpenRouter as the first channel

- status: accepted
- GitHub issue: pending implementation issue
- owner: product and infrastructure workstreams
- date: 2026-08-15

## Decision

Build Gradiated as an exact-model inference provider, not a general inference gateway.

Customers retain the core product: a Vite/React/shadcn application, a TypeScript/Node control API, organizations/workspaces, account API keys, usage and billing. Direct customers and OpenRouter call the same Rust inference data plane with different credential principals. Requests name an exact hosted model; Gradiated does not route to third-party model providers, substitute aliases or silently fall back.

Use TypeScript/Hono for the product application and every PostgreSQL-backed workflow. PostgreSQL owns one global model catalog, including customer pricing, public metadata and availability. Exact model and tokenizer paths and immutable revisions are required fields in the reviewed Git deployment manifest, even when model and tokenizer identities are equal. Low-volume control mutations synchronously project the latest committed PostgreSQL state to Valkey before reporting success, while an in-process reconciler repairs partial failures and rebuilds state. Restrictive changes block the affected Valkey scope first and fail closed. No PostgreSQL projection queue is used. Author every Gradiated HTTP API with described Zod schemas and generate OpenAPI 3.1, Scalar docs, agent Markdown, the browser client and checked Rust contract artifacts from that source.

Use Rust for everything on the inference hot path. Use SGLang for model execution. Host Kimi K3 first on one 8x NVIDIA B300 node in an external managed Kubernetes cluster. Run product and inference API workloads on EKS and use RDS PostgreSQL as durable application authority. Before any inference traffic is enabled, the TypeScript control application builds the serving projection in Amazon ElastiCache Serverless for Valkey. OpenRouter and direct customers use the same Valkey-backed path and differ only in billing mode. Valkey is the inference path's only synchronous internal state dependency; PostgreSQL and ClickHouse are never queried by an inference request.

Use one Valkey Stream for the terminal-generation handoff and no Kafka at launch. Rust atomically applies the terminal charge and appends `GenerationSettled`; one TypeScript consumer-group role acknowledges each entry only after ClickHouse confirms ingestion. It assigns every event in a Stream-ID time bucket the same global chronological five-minute settlement slot. A separate TypeScript role processes slots in order, collapses exact ClickHouse retries by generation ID, groups each slot by organization and posts one idempotent aggregate usage transaction per nonzero organization. Conflicting duplicates block settlement; insert-token retention is not a financial correctness dependency. Each PostgreSQL source ID is `<settlement_slot_id>:<organization_id>`. The worker resumes the latest PostgreSQL slot inclusively, uses a session advisory lock for single-leader execution and requires no settlement checkpoint or manifest table.

Represent every internal price, charge and balance as checked integer nano-USD while keeping concise field names such as `cost`, `unit_price`, `amount`, `charge`, `balance` and `balance_after`. Convert OpenRouter decimal USD strings and Stripe cents only at system boundaries; do not use floating-point money or a per-generation rounding policy.

Apply PostgreSQL-originated top-ups, payments, refunds, chargebacks, credits and adjustments to the operational Valkey balance with one atomic transaction-ID guard. A per-organization Valkey set retains applied PostgreSQL transaction IDs without TTL; the Lua projection changes the balance only for a newly added ID. Valkey-originated generation usage never enters this set or echoes back into Valkey. A full rebuild drains usage and reconstructs both the account balance and the low-volume ID set from PostgreSQL before reopening admission.

Use Docker Compose for the complete local stack and mprocs for source-mode development. Use Terraform with shallow Terragrunt units for cloud resources and Argo CD for Kubernetes desired state.

The implementation authority is [the Kimi K3 provider launch plan](../implementation/KIMI_K3_PROVIDER_LAUNCH_PLAN.md).

## Context and constraints

The initial revenue opportunity is Kimi K3 traffic through OpenRouter. The product must later host more exact models and must also retain a direct account/API-key experience. Previous plans expanded this into a universal gateway, external provider routing, branded model aliases, multiple public protocols, a separate inference router and generalized fleet control. Those components add latency and operating surface before the first model is online.

The team wants a small language boundary: TypeScript where application and web ecosystem speed matters; Rust where streaming, backpressure, admission and inference performance matter. API documentation and clients must not drift from runtime validation.

## Alternatives considered

1. **Chosen: TypeScript product application plus one Rust exact-model data plane.** Keeps the direct product, reuses the existing Vite/shadcn and Zod/OpenAPI plans, and limits Rust to the path where it is valuable.
2. **One all-Rust system.** Rejected because it slows product/UI/control-plane work and loses the strongest TypeScript contract-generation ecosystem without improving PostgreSQL-backed application workflows.
3. **One all-TypeScript system.** Rejected because the inference path needs predictable streaming, cancellation, bounded memory and future low-level serving work.
4. **Retain the universal gateway design.** Rejected because provider fallback, model aliases, multiple upstream adapters and a separate inference router do not help serve the first owned model.
5. **OpenRouter-only endpoint with no direct product.** Rejected because direct customer accounts and API keys remain a core product requirement.
6. **PostgreSQL or static configuration on inference requests.** Rejected because credentials, revocation, balance admission, in-flight concurrency and settlement need one atomic hot-path failure model. OpenRouter and direct customers use the single Valkey projection from their first request and never fall back to PostgreSQL or a separate static channel path.

## Consequences

- positive: only two Gradiated runtime services at seed: TypeScript `control` and Rust `inference-api`;
- positive: OpenRouter and direct users exercise the same serving implementation;
- positive: global PostgreSQL model rows and exact deployment declarations allow additional hosted models without a routing platform;
- positive: Zod remains the single HTTP contract authoring source across browser, docs and Rust fixtures;
- positive: local development has one reproducible Compose stack and one mprocs supervisor;
- positive: ClickHouse is the durable generation history and PostgreSQL settlement can recover from either worker's restart without a second broker or checkpoint table;
- negative: the TypeScript/Rust boundary requires generated artifacts and cross-language fixtures;
- negative: launch requires one carefully qualified Valkey admission projection;
- negative: ElastiCache Serverless is highly available but the Valkey Stream is not a zero-loss financial archive; launch accepts rare bounded generation-event loss until measured risk justifies a stronger broker;
- negative: one B300 node is an initial availability boundary;
- migration: extract retained auth/admission/streaming requirements from the old gateway blueprint into the new data-plane implementation, then remove active gateway/routing instructions while preserving dated evidence and direct-product requirements;
- rollback: SGLang, model and Rust releases are immutable GitOps digest changes; database migrations are forward-compatible and forward-fixed; Terraform state is never rolled back as an application release.

## Evidence

- vendor-reported: [OpenRouter provider requirements](https://openrouter.ai/docs/guides/community/for-providers) require a models endpoint, Chat Completions streaming, usage reporting, payment integration and reliability/performance behavior;
- vendor-reported: [OpenRouter provider application](https://openrouter.ai/providers/apply) requires OpenAI-compatible streaming, usage in stream and non-stream responses, pricing/model metadata, invoicing and privacy/retention disclosure;
- vendor-reported: [SGLang's Kimi K3 cookbook](https://docs.sglang.io/cookbook/autoregressive/Moonshotai/Kimi-K3) defines B300 as a one-node/eight-GPU deployment shape;
- vendor-reported: [CoreWeave's B300 specification](https://docs.coreweave.com/platform/instances/gpu/b300-8x) lists eight 270 GB B300 GPUs, 4 TB host RAM and 61.44 TB local storage;
- repository design input: [REST/OpenAPI blueprint](../../product/docs/REST_OPENAPI_MCP_IMPLEMENTATION.md) and [control-plane blueprint](../../product/docs/CONTROL_PLANE_IMPLEMENTATION.md) already specify Hono, Zod v4, generated OpenAPI/client/docs, Vite and shadcn/ui.

No Kimi K3 production performance, stability, capacity or margin claim is measured yet. Those are launch gates, not assumptions.

## Reversal trigger

Revisit the exact-model/no-gateway boundary only after at least two real hosted models demonstrate a shared routing requirement that cannot be represented by the finite exact model catalog. Revisit the TypeScript/Rust boundary only if measured cross-language contract cost exceeds its separation benefit. Revisit single-node Kimi K3 when measured uptime, saturation or margin supports a second node or a more complex SGLang topology.
