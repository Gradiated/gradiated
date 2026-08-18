# Architecture

- status: current implementation authority
- date: 2026-08-15
- data model: [DATA_MODEL.md](DATA_MODEL.md)
- launch context: [KIMI_K3_PROVIDER_LAUNCH_PLAN.md](KIMI_K3_PROVIDER_LAUNCH_PLAN.md)

This document defines the deployed services, their dependencies and their
ownership boundaries for the exact-model product. [DATA_MODEL.md](DATA_MODEL.md)
is authoritative for schemas, keys, event payloads and storage invariants. The
Kimi K3 launch plan is authoritative for provider onboarding, launch sequencing
and model-specific operating parameters.

The seed system has three Gradiated processes and one external model runtime.
`api` and `worker` use one TypeScript codebase and image; `gateway` is the Rust
hot path. SGLang runs on the external provider's GPU node, not in EKS.

```text
browser ---> api (TypeScript/Node; also serves built Vite assets)
               |       |       |
               v       v       v
         PostgreSQL  Valkey  ClickHouse

worker (TypeScript/Node) ---> PostgreSQL / Valkey / ClickHouse

direct API key or OpenRouter key (`api.gradiated.com/openai/*`)
  |
  v
public ALB path rule ---> gateway (Rust, EKS) ---> private/restricted TLS
                    |                              |
                    v
                  Valkey
                                                   v
                                    SGLang pod on 8x B300
                                    external provider cluster
```

There is no general gateway, provider router, model alias layer, fallback
graph, third-party inference adapter or fleet service. A request names one
exact hosted model. Direct customers and OpenRouter use the same Rust gateway
and the same Valkey-backed authentication, admission and settlement path.

## Service inventory

| Component        | Runtime/deployment                                                                   | Depends on                                                                                              | Owns or performs                                                                                                                                           | Must not do                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `console`        | Static Vite/React deployment at `console.gradiated.com`                              | `api.gradiated.com`                                                                                     | customer product UI and generated API client                                                                                                               | access datastores, hold server secrets, proxy inference                                                                 |
| `api`            | TypeScript/Node Kubernetes Deployment on EKS CPU nodes                               | RDS PostgreSQL; Valkey for serving-relevant mutations; ClickHouse for usage views; Stripe               | human sessions, organizations, workspaces, invitations, API keys, model catalog, billing operations, usage views and generated API/docs                    | serve inference, serve console assets, run asynchronous settlement loops, authenticate hot-path keys, own Rust behavior |
| `worker`         | TypeScript/Node Kubernetes Deployment using the same image as `api`                  | RDS PostgreSQL; Valkey; ClickHouse Cloud                                                                | periodic PostgreSQL-to-Valkey reconciliation/rebuild, `GenerationSettled` ingestion into ClickHouse and global-slot settlement into PostgreSQL             | expose a network API, write PostgreSQL per generation, retain prompts or completions                                    |
| `gateway`        | Rust deployment on EKS CPU nodes, exposed through the public ALB                     | Valkey; the selected SGLang endpoint; generated contract fixtures; local Git-pinned deployment manifest | API-key authentication, exact model lookup, bounds/admission, streaming proxy, cancellation, usage normalization, terminal finalization and health/metrics | query PostgreSQL/ClickHouse, run product CRUD, process Stripe, select providers, provision GPUs, persist prompts        |
| `sglang-kimi-k3` | SGLang pod on the external provider's 8x B300 Kubernetes node; never an EKS workload | pinned model/tokenizer artifacts, pinned SGLang image, GPU node and provider networking                 | execute one exact Kimi K3 release and expose a private OpenAI-compatible runtime endpoint to `gateway`                                                     | authenticate customers, charge balances, expose a public endpoint, choose another model/provider                        |

`api` and `worker` are two commands from one TypeScript application and image,
not independently versioned domain services. Keeping them in separate EKS
Deployments prevents a ClickHouse outage or settlement query from affecting the
public API. `worker` runs one replica at launch and supervises each loop with an
independent timeout, backoff and health state. Its protocols remain safe to
split or scale later: Valkey consumer groups divide ingestion, PostgreSQL
advisory locking elects settlement, and projection is level-triggered and
idempotent. Do not create separate projection, ingestion or billing services.

## Dependency and authority rules

### PostgreSQL / RDS

RDS PostgreSQL is the durable authority for Better Auth records,
organizations, workspaces, API keys, the global model catalog, billing account
balances and immutable balance transactions. Only the TypeScript application
and its background roles use PostgreSQL repositories. Rust has no PostgreSQL
driver or product repository.

PostgreSQL is not on the inference request path. A successful product mutation
that affects serving must commit its authoritative row, reload the current row
from the primary, synchronously update Valkey and only then report success.
Periodic reconciliation repairs partial projection failures. Restrictive
operations fail closed or leave the affected Valkey scope blocked if projection
cannot be confirmed.

The settlement role writes one idempotent `balance_transactions` row per
nonzero organization/global-slot group. `(source_type, source_id)` and the
PostgreSQL session advisory lock make retries and multiple pods safe. No
per-generation PostgreSQL row is created.

### Valkey / ElastiCache Serverless

Valkey is the only synchronous internal state dependency for inference. It
contains the serving projection described in [DATA_MODEL.md](DATA_MODEL.md):

- `GatewayAccount` records, including the operational balance;
- `GatewayWorkspace` records;
- `GatewayCredential` records indexed by API-key digest;
- exact `GatewayModel` records;
- per-organization in-flight generation leases;
- the dedicated `GenerationSettled` stream;
- applied PostgreSQL balance-transaction IDs.

Rust reads Valkey for every request and fails closed when required state is
missing or unavailable. It never falls back to PostgreSQL or ClickHouse.

The finalization Lua script atomically removes the in-flight lease, subtracts
the captured actual charge and appends one terminal generation event. The
shared settlement hash tag keeps the account, in-flight and stream keys in one
Valkey Cluster hash slot. There is one seed settlement shard; changing shard
assignment is a drained migration.

Valkey is operational state and a transport, not the durable financial ledger
or generation archive. The launch accepts bounded loss of an unacknowledged
event if Valkey fails before ClickHouse has confirmed it. Do not add Kafka,
CDC, an outbox, another queue or a second cache without measured evidence that
this tradeoff is unacceptable.

### ClickHouse Cloud

ClickHouse stores immutable terminal `generations` rows. The full
versioned `GenerationProperties` JSON is authoritative for generation facts;
only query-critical dimensions are materialized columns. It stores no prompts,
completions, credentials or mutable billing state.

The generation-ingest role consumes Valkey stream entries and performs
acknowledged asynchronous inserts. ClickHouse combines individual inserts
server-side; the application does not need a separate batching queue. It uses
generation-ID insert deduplication as a retry optimization, while the
generation ID and conflict detection preserve billing correctness.

The settlement role queries ClickHouse for eligible global five-minute slots,
collapses exact generation retries, groups charges by organization and writes
the resulting PostgreSQL balance transactions. It resumes the latest posted
slot inclusively and does not need a checkpoint table. ClickHouse retains
generations indefinitely at launch; ClickHouse Cloud durability and backups
are sufficient initially.

### Git and deployment manifests

Git owns environment-specific `ModelDeploymentManifest` configuration:
exact model and tokenizer paths/revisions, SGLang image/profile, secret
references, GPU shape, measured capacity, region and compliance declarations.
The served release digest covers the immutable runtime identities and canonical
launch configuration.

PostgreSQL owns the customer-facing global `models` catalog: public ID/name,
properties, pricing, advertised capacity and availability. Rust combines the
Valkey `GatewayModel` with its locally loaded Git deployment manifest. A
catalog status change is projected to Valkey; an unavailable or retired model
is rejected before GPU work.

## Application service details

### `console`

The customer console is a Vite/React app using TanStack Router/Query,
Tailwind and shadcn/ui. It uses only the generated TypeScript client for the
API service. It does not share database types directly and never receives
secret API-key material after the one-time creation response.

Production hosts the console at `console.gradiated.com` and all public API
traffic at `api.gradiated.com`. Local development runs Vite on port 3000 and
proxies API requests to port 3001. On the public ALB, `/openai/*` routes to the
Rust gateway and every other path routes to the TypeScript API service. The
console does not proxy inference requests through the API service. The static
host must return `index.html` for console routes so browser refreshes preserve
client-side routing.

### `api`

The API service is a single TypeScript/Node codebase using Hono,
Zod, `@hono/zod-openapi`, Drizzle over `node-postgres`, Better Auth and Stripe
webhook/checkout integration when direct billing is enabled.

Its HTTP API owns:

- human authentication and sessions;
- organization membership and invitations;
- workspace creation, archival and selection;
- one-time API-key creation, listing and revocation;
- global model catalog and availability administration;
- prepaid top-ups, invoiced credit adjustments and billing views;
- usage and account views queried from ClickHouse and PostgreSQL.

Every route starts from a Zod schema and route manifest. OpenAPI 3.1,
Scalar/reference docs, `llms.txt`, the browser client and Rust contract
fixtures are generated outputs. CI regenerates and rejects drift.

The API service may use Valkey synchronously for serving-sensitive mutations,
but it does not use Valkey as its general application database. Product reads
come from PostgreSQL; usage analytics come from ClickHouse; gateway records
are read from Valkey only when validating or repairing serving state.

### `worker`

The worker uses the same TypeScript packages, schemas, repositories,
configuration and container image as `api`, but starts a non-HTTP command. It
runs three independently supervised loops:

1. reconcile and rebuild PostgreSQL serving state in Valkey;
2. consume `GenerationSettled` from Valkey into ClickHouse;
3. settle eligible ClickHouse slots into PostgreSQL balance transactions.

One worker pod runs at launch. Each loop has its own timeout, bounded backoff,
lag metrics and failure state so one unavailable dependency cannot terminate or
stall the others. The pod is live while the supervisor is running; readiness
and alerts report each loop separately. It has no Kubernetes `Service` because
it accepts no inbound traffic.

### `gateway`

The Rust service exposes the launch inference contract:

- `POST /v1/chat/completions`, streaming and non-streaming;
- `GET /v1/models` with only exact currently advertised model IDs;
- `/health/live`, `/health/ready` and `/metrics`.

For each request it authenticates the API-key digest, resolves the exact model
record, checks organization/workspace status, applies the operational
positive-balance rule and an atomic balance-derived concurrency ceiling, and
rejects parameters not advertised by the exact model before contacting
SGLang. It renders and tokenizes the qualified request locally on CPU using the
exact tokenizer revision declared by the Git-owned deployment manifest, then
enforces the model's context bound before admission. The gateway keeps only a
small typed request envelope; the model's Valkey-projected
`passthrough_parameters` map qualifies the remaining JSON fields without a
gateway-wide model schema. Each concurrency slot represents
a configured amount used only to make concurrency fall proportionally with
the remaining balance. It is not a reservation or worst-case request-cost
limit. The gateway forwards only qualified fields to the model runtime,
preserving cancellation, backpressure and streaming semantics.
Every exact model maps to one SGLang deployment. SGLang owns runtime admission;
the gateway normalizes downstream overload to `429` and does not queue, retry,
or select another deployment.

The request captures the effective model pricing and served release digest at
admission. On terminal success, failure, cancellation or abandonment, Rust
normalizes authoritative token usage, calculates the integer nano-USD charge,
constructs the closed generation properties document and invokes the Valkey
finalization script. A lost process may leave an expired, unbilled generation;
there is no durable in-progress request table at launch.

Rust does not implement human sessions, customer CRUD, Stripe, OpenRouter
onboarding, model purchasing, provider APIs or GPU provisioning.

### `sglang-kimi-k3`

The initial runtime is one SGLang pod scheduled directly onto the external
provider's 8x B300 GPU node, using TP8 and a pinned Kimi K3-capable SGLang image
and model revision. It is not deployed to or joined with EKS. A private
Kubernetes `Service` (or the provider's equivalent private endpoint) gives the
EKS gateway a stable upstream address over private connectivity or restricted
TLS.

The deployment exposes readiness only after model load and qualified serving
checks. It uses explicit B300 placement, large shared memory, persistent local
model/compile caches, conservative restart behavior and measured capacity
limits, including bounded `max_running_requests` and `max_queued_requests`.
It does not implement customer authentication or billing. A second model is a
second explicit catalog row, manifest and SGLang deployment; it is not a reason
to introduce a routing layer. This one-deployment-per-exact-model rule applies
to every hosted model, not only Kimi K3.

## External services and infrastructure

| Dependency                    | Used by                      | Purpose                                                                | Launch boundary                                                                                                  |
| ----------------------------- | ---------------------------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| RDS PostgreSQL                | `api`, `worker`              | durable product and financial state                                    | private subnets, Multi-AZ, PITR and deletion protection                                                          |
| ElastiCache Serverless Valkey | `api`, `worker`, `gateway`   | serving projection, leases and generation stream                       | managed Multi-AZ; fail closed when unavailable                                                                   |
| ClickHouse Cloud              | `api`, `worker`              | immutable generations, settlement queries and product usage views      | AWS-aligned region through PrivateLink in production; no prompt retention; indefinite launch retention           |
| Stripe                        | `api`                        | direct prepaid top-ups and payment events                              | webhook signature verification; no Stripe call from Rust                                                         |
| OpenRouter                    | external distribution client | calls the same exact-model endpoint using its channel organization/key | invoiced organization; onboarding/auth contract configured in api/infra                                          |
| external Kubernetes provider  | `sglang-kimi-k3`             | B300 GPU capacity                                                      | provider-owned cluster/node pool; separate from EKS                                                              |
| ECR                           | CI/Argo                      | immutable api/worker and gateway images                                | image digest deployment only                                                                                     |
| Secrets Manager               | EKS and deployment bootstrap | database, channel, upstream and remote-cluster credentials             | secrets are injected at runtime, never committed                                                                 |
| Route 53 / ACM / ALB          | `api`, `gateway`             | DNS, TLS and Gateway API path routing on `api.gradiated.com`           | AWS Load Balancer Controller owns one public ALB with IP targets; `/openai/*` to gateway; all other paths to API |
| S3 / CloudFront               | `console`                    | static console hosting and SPA fallback                                | no application API or inference proxy                                                                            |
| CloudWatch / AWS Budgets      | platform                     | AWS control-plane logs, alarms and cost limits                         | infrastructure and billing signals remain in AWS                                                                 |
| Prometheus / Grafana          | platform                     | Kubernetes and application metrics, dashboards and alert evaluation    | Argo-managed inside the EKS cluster; private access only at launch                                               |

Terraform owns foundational AWS resources, IAM, EKS, managed services,
ACM, the Route 53 zone, controller prerequisites and the minimum Argo
bootstrap. Argo CD owns Kubernetes workloads, AWS Load Balancer Controller,
ExternalDNS and Gateway API desired state after bootstrap. AWS Load Balancer
Controller owns the ALB, listeners, target groups, security-group
reconciliation and IP target registration; ExternalDNS owns only selected
application records derived from Gateway status. The external provider's
cluster and node-pool resources remain provider/Terraform-owned; Argo owns only
the namespaced SGLang workload if remote-cluster management is supported
cleanly.

## Request and event paths

### Browser control path

```text
browser -> public product edge -> API service -> PostgreSQL
                                      |
                                      +-> Valkey projection for serving mutations
                                      +-> ClickHouse for usage views
                                      +-> Stripe for billing workflow/webhooks
```

The API service returns success for a serving-sensitive mutation only after the
authoritative PostgreSQL commit and required Valkey acknowledgement. It does
not wait for ClickHouse because ClickHouse contains terminal inference history,
not control-plane authority.

### Inference path

```text
client/OpenRouter
  -> public ALB
  -> Rust authentication and admission in Valkey
  -> SGLang exact model endpoint
  -> Rust streaming/error/usage normalization
  -> atomic Valkey finalization
  -> client response
```

PostgreSQL and ClickHouse are not contacted by any inference request. Admission
uses an expiring per-organization in-flight lease and current operational
Valkey balance. Actual charge is applied only at terminal finalization, allowing
final in-flight generations to move the balance below zero. Subsequent
admission remains blocked until the balance becomes positive again.

### Settlement path

```text
Rust finalization
  -> Valkey GenerationSettled stream
  -> worker generation-ingest loop
  -> ClickHouse generations
  -> worker settlement loop, global five-minute slots
  -> PostgreSQL grouped balance transaction
  -> Valkey idempotent balance projection
```

The ClickHouse consumer and PostgreSQL settlement role can be redeployed or
run on multiple pods. The consumer group, `XAUTOCLAIM`, ClickHouse generation
identity, global slot ordering, PostgreSQL advisory lock and source-id
idempotency make recovery safe. There is no separate queue or checkpoint
service.

## Deployment units and local parity

The minimum production deployment units are:

1. `api` TypeScript Deployment and ClusterIP Service in EKS, including the
   built Vite assets;
2. `worker` TypeScript Deployment in EKS, with no Kubernetes Service;
3. `gateway` Rust Deployment and ClusterIP Service in EKS;
4. one SGLang model Deployment and private Service on the external GPU cluster;
5. PostgreSQL, Valkey and ClickHouse managed services.

Local development preserves these process and network boundaries without
reproducing production packaging. Docker Compose runs PostgreSQL, Valkey and
ClickHouse only. `mprocs` runs Vite, `api`, `worker`, `gateway` and SGLang as
native host processes. On the supported Apple Silicon profile, SGLang uses its
Metal/MLX backend and a pinned small local model; the local model has its own
truthful exact catalog ID and deployment manifest rather than masquerading as
Kimi K3. The gateway reaches SGLang over its normal HTTP interface on
localhost, so Chat Completions, streaming, usage and cancellation cross the
same runtime boundary as production. Gateway-local tokenizer parity is checked
against that pinned SGLang release; pre-admission tokenization itself does not
make an SGLang request.

Deterministic runtime failures that a real model server cannot safely induce
use the gateway's in-process `ModelRuntime` test double. There is no deployed
fake-SGLang process. Local development does not require Kubernetes, LocalStack,
AWS credentials, NVIDIA capacity, OpenRouter credentials or Stripe
credentials. Final release conformance still runs against the pinned CUDA
SGLang and Kimi K3 deployment because MLX and the small local model prove the
protocol integration, not production model equivalence.

## Implementation rules and complexity gates

- Use one TypeScript application codebase and one Rust hot-path codebase.
- Keep all asynchronous roles in one `worker` process from the `api` codebase
  and image. Split a role into another Deployment only after measured scaling
  or isolation requirements.
- Keep exact model dispatch finite and explicit. Do not add routing or provider
  abstractions for hypothetical capacity.
- Let each model's single SGLang deployment own runtime admission. Normalize
  overload to `429`; do not queue, retry, or fall back in the gateway.
- Keep PostgreSQL, Valkey and ClickHouse as separate authorities with no hidden
  cross-store source of truth.
- Do not add Kafka, CDC, an outbox, a service mesh, Temporal, KEDA, Karpenter,
  RDS Proxy or a custom operator at launch.
- Add a second model through a catalog row, Git manifest, SGLang deployment,
  capacity measurement and conformance fixtures.
- Introduce a routing/platform layer only after at least two real hosted models
  create a measured shared-routing requirement that cannot be represented by
  the exact-model catalog.
- Introduce more workers or services only when a measured SLO, throughput,
  isolation or recovery requirement cannot be met within the existing service.

The architecture is intentionally narrow until production evidence requires
another boundary.
