# Product architecture handoff

## Current decision

Build the direct paid gateway first as a premium curated inference and migration product, while making owned serving independently OpenAI-compatible and eligible for external-gateway distribution. Customers may call Grad directly or put a workspace key behind their existing gateway; selected native listings use separate channel credentials/receivables. The control plane is Vite React plus Hono/tRPC Node; the data plane is Rust. An organization is the customer/billing boundary and workspaces isolate keys, data/model policy, limits, membership and usage.

The model surface has two lanes. Curated direct IDs (`openai/...`, `anthropic/...`, `google/...`) preserve exact provider/model identity so an existing workload can often move by changing only base URL/key. First-party `grad/<effort>/<speed>` products run only on our inference; effort is `low|medium|high|max`, speed is `flex|standard|fast|turbo`, and the default is `grad/medium/standard`. Stable family heads such as `grad/glm-5.2/fast` stay inside a declared family compatibility envelope; `@release` pins are immutable. Preview `slow` may alias `flex` but is not another speed lane. There are no customer provider arrays or hidden moves from direct traffic to Grad.

The research factory produces the custom architecture in the broad sense: weights/model code, custom operators, kernels/runtime, scheduler/cache, topology and hardware mapping are one signed content-addressed `ModelStackBundle`. Fable supplies hypotheses/functional-twin/model-surgery inputs; Sol supplies immutable experiment, controls, fidelity and claim-admission discipline. An independent qualification plane tests the exact bundle through model, runtime, protocol, measured system, distributed cell, security and soak gates. Production consumes that same digest through a human-approved `RouteRelease`; it does not recreate the architecture manually. Temporal orchestrates campaigns, Kueue/JobSet handles Kubernetes research execution, and native providers remain behind honest execution adapters. None is on the request path.

Product Intelligence retains bounded encrypted request/response/tool traces by default for history, workload analytics, replay and Grad migration recommendations. Private/No Retention is a workspace or stricter request mode. Retention is not training consent. Recommendations move through metadata opportunity, replay candidate, evaluator/shadow verified and live-canary ready; the customer explicitly starts experiments and performs the final model change.

Owned Grad serving uses an AWS-hosted inference edge and disposable cells across curated external GPU capacity providers. The gateway selects only signed exact-release cell targets from Redis; the edge/cell router handles transport, queueing and cache affinity. PostgreSQL owns desired capacity, budgets and lease history. A Grad fleet API in AWS EKS projects that state into `CapacityPool`, `CapacityAllocation`, and `InferenceCell` resources; isolated controllers reconcile native APIs or managed-Kubernetes cells. Native allocations are not fake Nodes/Pods, and no cluster spans providers. The target projector—not a provider controller or cell—signs ready Redis targets. Every generative Grad release keeps active and prefix KV caching enabled, including Private/No Retention; salted cache state is ephemeral and never becomes a trace or durable data-store object.

Creating an organization atomically creates a hidden Default workspace and owner memberships. PostgreSQL owns the customer ledger, distribution-channel receivables, model/release, desired capacity/leases, authorization, trace-registry/tombstone and workload/experiment control state. Private S3 stores encrypted trace payloads. ClickHouse Cloud stores only a content-free, replayable analytical projection used for trace lists/charts/workload/model/evaluation summaries. The gateway's only synchronous internal state/control dependency is Redis for versioned policy/catalog/release/price, atomic reservations/limits and separate billing/trace streams; model APIs and the inference edge are upstream serving dependencies. Workers project/reconcile money, drain encrypted traces, project analytics, enforce retention/delete and derive recommendations.

## Non-negotiable behavior

- A raw API key resolves to one organization and one workspace. Top-ups and ledger entries are organization-scoped; usage and configurable limits are also attributed to workspace/key.
- A top-up credits the organization only from a verified, idempotently processed Stripe webhook, never from a browser redirect.
- No upstream call begins unless one Redis operation authenticates, checks organization/workspace/key status, reserves worst-case organization spend, reserves all nested limits, increments permitted concurrency, creates a lease, and appends the reservation event.
- Insufficient organization credit returns `402 insufficient_credits`. Low organization credit activates an organization-wide in-flight cap in addition to workspace/key caps; excess requests return `429 low_balance_concurrency_limit`.
- Redis failure before admission is fail-closed. PostgreSQL is not queried by the gateway.
- Settlement and stream consumption are idempotent. PostgreSQL ledger corrections are append-only.
- Internal TS/Rust contracts are Protobuf-generated and checked for drift. External OpenAI/Anthropic/Google JSON/stream behavior is fixture-tested separately.
- Billing and authorization logic require PBT state machines in fast-check and proptest, with seeds/replay artifacts emitted by CI.
- Direct requests never cross provider/model/version. Grad requests never leave owned inference or change effort/speed; capacity fails early instead of silently downgrading.
- Unsupported capability/data-policy/context behavior fails before spend. Every provider model and Grad cell requires scope-matched qualification and immutable fixed-price release.
- Eligible no-usable-output requests receive exactly one append-only customer sell credit; provider buy evidence remains intact.
- No-retain payload never reaches Redis/S3; Product Intelligence ciphertext never falls back to plaintext. Trace load cannot starve billing events.
- No-retain still uses tenant-isolated active/prefix KV cache. Cache loss affects latency only; cache cannot cross workspace/channel/release/retention-class or persist into traces/backups.
- External GPU cells receive no customer API key, billing state, provider credential, trace key, or database access. Spot loss is assumed abrupt and cannot change the exact release/speed.
- Use `model provider` for OpenAI/Anthropic/Google, `capacity provider` for GPU infrastructure, and `distribution channel` for OpenRouter/other gateways. Direct endpoints and Grad cells/targets are separate entities.
- Fleet CRDs are rebuildable runtime actuation/status, not business authority. Argo owns schemas/controllers, fleet services own dynamic specs/status, and provider finalizers are backed by durable lease tags plus an independent orphan sweeper.
- Distribution-channel admission uses a separate Redis `ChannelAccountProjection`, credentials, receivable exposure, price book, trace policy and cache scope. It can never debit organization credit.
- ClickHouse never receives raw content and never becomes auth/ledger/retention truth. Hono scopes every analytical query; PostgreSQL tombstones/key revocation deny detail before S3/ClickHouse cleanup converges; ClickHouse outage can delay analytics only.
- No recommendation/experiment state can automatically rewrite the customer's requested model.
- Research agents cannot publish production targets, alter hidden evaluators, approve their own release or promote simulated/component-only evidence; production cells attest the exact qualified bundle digest.
- Family heads cannot cross their compatibility envelope, managed effort/speed heads cannot leave their product envelope, immutable pins never move, and alias movement never changes an in-flight request.

## Implementation order

1. Scaffold pnpm/Rust workspaces, Buf contracts, CI, fake providers, PBT replay tools, and local/CI containers.
2. Implement PostgreSQL organization/workspace memberships, keys, budgets, and organization ledger invariants.
3. Implement Vite/shadcn UI, Hono/tRPC API, Better Auth sessions, and organization/workspace authorization.
4. Implement Stripe top-ups, transactional outbox, Redis projector, stream consumer, and reconciliation.
5. Implement Rust Redis admission/settlement scripts and state-machine tests before provider dispatch.
6. Add Chat Completions, Anthropic Messages, stateless Responses and Embeddings with explicit capability conformance.
7. Add curated OpenAI/Anthropic/Google identities/aliases and Grad effort/speed qualification/releases.
8. Build the inference edge/two-AZ relay and cell contracts, fleet CRDs/fake controllers/Kind PBT, pinned vLLM runtime with always-on salted prefix cache, one native capacity-provider controller, then compare one managed-Kubernetes cell and qualify diversified spot capacity.
9. Add encrypted Product Intelligence trace ingestion/S3 retention, content-free ClickHouse projection/query/delete/rebuild, Private/No Retention and workload/recommendation/experiment state machines.
10. Complete provider-migration and Grad quickstarts, protected real-provider/owned CI and operations, then run measured OpenRouter provider conformance/soak/economics.
11. Ship the shared open-distribution harness and P0 LiteLLM/Cloudflare/Portkey/Helicone/Vercel AI SDK recipes; pursue OpenRouter first and Hugging Face second as native listings after their channel gates pass.
12. Build the research factory in RF-00 through RF-08: contracts, evidence authority, bundle supply chain, Temporal/execution adapters, Fable/Sol adapters, independent qualification, release registry/UI, then one no-public-alias dry-run vertical candidate.

Detailed ownership and acceptance checks are in `docs/DELIVERY_PLAN.md`.

## Infrastructure decision

The AWS/EKS plan is specified under `../infra/`. Each environment has an isolated account/VPC/private EKS cluster. Vite is served by S3/CloudFront; separate ALBs front Hono and the gateway. Aurora owns financial/configuration/trace authority; a purpose-separated KMS S3 bucket owns encrypted trace payloads; ClickHouse Cloud is reached through PrivateLink for derived trace analytics; financial, trace, analytics-projector and recommendation workers have distinct identities. Production admission targets qualified node-based ElastiCache Valkey 9; billing-stream headroom is protected from the separate trace stream. Serverless Valkey remains limited to disposable environments until equivalent durability evidence exists.

Terraform modules plus Terragrunt implicit stacks use versioned/KMS S3 state with native lock files. Argo CD pulls Helm desired state, KEDA scales pods, Karpenter supplies bounded nodes, and GitHub OIDC avoids static AWS credentials. Docker Compose and mprocs/dekit sit behind a Rust `grad` CLI so agents can run and verify the stack without owner-local execution. See `../infra/docs/DELIVERY_PLAN.md` and `../docs/decisions/0001-aws-eks-platform.md`.

AWS GPUs are not normal serving capacity. The external fleet design, spot lifecycle, provider qualification, and Kubernetes management abstraction are in `docs/OWNED_INFERENCE_ARCHITECTURE.md`, `docs/KUBERNETES_PROVIDER_ABSTRACTION_2026-07-13.md`, `../infra/docs/MULTI_PROVIDER_GPU_FLEET.md`, ADR-0005 and ADR-0006. The cross-product audit and remaining measured gates are in `docs/ARCHITECTURE_AUDIT_2026-07-13.md`.

## OpenRouter feature decision

Current official public docs describe a much broader surface than routing alone: Chat/Messages/Responses/embeddings/media, provider and cross-model routing, Auto/Pareto/variant routers, workspaces/budgets/BYOK, privacy/logging/caching, plugins/hosted tools, agent SDKs, administration and provider onboarding. The repository now classifies that complete surface as keep, simplify, defer, reject, or operator-only. We retain protocol, reliability, billing and privacy fundamentals while removing marketplace and plugin/agent complexity from first use. See `docs/OPENROUTER_FEATURE_DECISIONS.md` and [ADR-0002](../docs/decisions/0002-opinionated-inference-product.md).

ADR-0003 and `docs/MODEL_LANES_AND_MIGRATION.md` supersede ADR-0002's five-product names and no-payload-retention boundary. ADR-0004 and `docs/CLICKHOUSE_TRACE_ANALYTICS_DECISION.md` define the ClickHouse/PostgreSQL/S3 split. The curated-not-marketplace, strict capability, fixed-price release, prepaid and downstream-distribution decisions remain.

## Open distribution decision

Grad inference is a first-class OpenAI-compatible endpoint, not a feature available only through Grad's own customer experience. Customer-configured gateways forward a workspace key and remain ordinary prepaid organization traffic. Native OpenRouter/Hugging Face listings authenticate as dedicated distribution principals with channel catalogs, exposure/receivable accounting and contract privacy; they cannot touch customer credit or first-party traces. One Rust serving path and owned inference fleet serve all three modes.

P0 compatibility covers official OpenAI TypeScript/Python/Go clients, OpenAI's pinned `gpt-oss` tool/API-shape smoke, Vercel `@ai-sdk/openai-compatible`, a pinned LiteLLM proxy and reproducible Cloudflare/Portkey/Helicone recipes. OpenRouter SDKs are post-listing black-box test dependencies. The implementation-ready target/package/harness/CI plan is `docs/DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md`; WP-09 in `docs/DELIVERY_PLAN.md` owns delivery.

## Environment names planned

```text
DATABASE_URL
REDIS_URL
BETTER_AUTH_SECRET
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
OPENAI_API_KEY
OPENAI_E2E_MODEL
ANTHROPIC_API_KEY
ANTHROPIC_E2E_MODEL
GOOGLE_API_KEY
GOOGLE_E2E_MODEL
GRAD_OPENAI_BASE_URL
TRACE_BUCKET
TRACE_KMS_KEY_ARN
TRACE_RETENTION_DAYS
TRACE_ACCESS_SIGNING_PRIVATE_KEY
TRACE_ACCESS_VERIFY_PUBLIC_KEY
CLICKHOUSE_URL
CLICKHOUSE_INSERT_USER
CLICKHOUSE_INSERT_PASSWORD
CLICKHOUSE_QUERY_USER
CLICKHOUSE_QUERY_PASSWORD
PBT_SEED
```

Secrets belong in deployment/GitHub environments only. Provider smoke tests must never print payloads or tokens.

## Coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/1
- Completed packet: `tasks/done/2026-07-13-gateway-architecture-revision.md`
- GitHub issue #1 is closed. GitHub Project mutation was unavailable to the current fine-grained token; the local scope has been released.
- Infrastructure plan issue: https://github.com/joshsny/gradiated/issues/2; completed packet: `tasks/done/2026-07-13-infrastructure-platform-plan.md`.
- Opinionated product strategy issue: https://github.com/joshsny/gradiated/issues/3 is closed; completed packet: `tasks/done/2026-07-13-opinionated-openrouter-feature-strategy.md`.
- Provider/Grad/trace/ClickHouse architecture: https://github.com/joshsny/gradiated/issues/4 is closed; completed packet: `tasks/done/2026-07-13-grad-effort-speed-provider-lanes.md`.
- Multi-provider spot GPU architecture: https://github.com/joshsny/gradiated/issues/7; completed packet: `tasks/done/2026-07-13-multi-provider-spot-inference.md`.
- Kubernetes provider abstraction and full architecture audit: https://github.com/joshsny/gradiated/issues/8; architecture commit `fe345f3`; completed packet: `tasks/done/2026-07-13-kubernetes-provider-abstraction-audit.md`.
- Open distribution integrations: https://github.com/joshsny/gradiated/issues/9; architecture commit `82bd779`; completed packet: `tasks/done/2026-07-13-open-distribution-integrations.md`.
- Research factory and model lifecycle: https://github.com/joshsny/gradiated/issues/10; completed packet: `tasks/done/2026-07-13-model-research-production-platform.md`.
- No code has been implemented and no provider request has been made in this planning task.

## Resume

```sh
python3 tools/devex/context.py
sed -n '1,260p' product/docs/DELIVERY_PLAN.md
sed -n '1,340p' product/docs/OWNED_INFERENCE_ARCHITECTURE.md
sed -n '1,520p' product/docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md
sed -n '1,340p' infra/docs/MULTI_PROVIDER_GPU_FLEET.md
sed -n '1,420p' product/docs/KUBERNETES_PROVIDER_ABSTRACTION_2026-07-13.md
sed -n '1,420p' product/docs/ARCHITECTURE_AUDIT_2026-07-13.md
sed -n '1,180p' product/docs/MULTI_PROVIDER_GPU_EVIDENCE_2026-07-13.md
sed -n '1,360p' product/docs/OPENROUTER_FEATURE_DECISIONS.md
sed -n '1,420p' product/docs/DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md
sed -n '1,420p' product/docs/MODEL_LANES_AND_MIGRATION.md
sed -n '1,420p' product/docs/CLICKHOUSE_TRACE_ANALYTICS_DECISION.md
sed -n '1,320p' infra/docs/DELIVERY_PLAN.md
```

Claim exactly one work package and its paths before implementation. Begin with product WP-00 and infrastructure I-00 as coordinated contract/toolchain work; no AWS mutation begins until the platform checkpoint inputs and authority in the infrastructure plan are satisfied.
