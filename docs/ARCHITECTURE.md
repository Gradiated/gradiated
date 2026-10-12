# Architecture

- status: current implementation authority
- date: 2026-08-15
- data model: [DATA_MODEL.md](DATA_MODEL.md)

This document defines the deployed services, their dependencies, and their
ownership boundaries. [DATA_MODEL.md](DATA_MODEL.md) is authoritative for
schemas, keys, event payloads, and storage invariants.

The seed system has three Gradiated processes and one external model runtime.
`api` and `worker` use one TypeScript codebase and image; `gateway` is the Rust
hot path. SGLang runs on the external provider's GPU node, not in EKS.

```text
browser ---> api (TypeScript/Node; also serves built Vite assets)
               |       |       |
               v       v       v
         PostgreSQL  Valkey  ClickHouse

worker (TypeScript/Node) ---> PostgreSQL / Valkey / ClickHouse
temporal-worker (TypeScript/Node) ---> Temporal Cloud / PostgreSQL / S3

direct API key or OpenRouter key (`api.gradiated.com`)
  |
  v
public ALB ---> proxy ---> gateway (Rust, EKS) ---> private/restricted TLS
                             |                         |
                             v                         v
                           Valkey          selected SGLang model runtime
                                           external provider cluster
```

There is no general gateway, provider router, model alias layer, fallback
graph, third-party inference adapter or fleet service. A request names one
exact hosted model. Direct customers and OpenRouter use the same Rust gateway
and the same Valkey-backed authentication, admission and settlement path.

The one exception is the customer-key proxy in `product/services/proxy`, which
the [proxy feature plan](PROXY_FEATURE_PLAN.md) governs. It relays requests to
Anthropic or OpenAI with the customer's own provider key and forwards hosted
requests to the gateway. It is built and tested but not yet deployed; the plan's
rollout moves the public inference paths from the gateway to the proxy.

## Service inventory

| Component        | Runtime/deployment                                                                      | Depends on                                                                                 | Owns or performs                                                                                                                                           | Must not do                                                                                                             |
| ---------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `console`        | Static Vite/React deployment at `console.gradiated.com`                                 | `api.gradiated.com`                                                                        | customer product UI and generated API client                                                                                                               | access datastores, hold server secrets, proxy inference                                                                 |
| `api`            | TypeScript/Node Kubernetes Deployment on EKS CPU nodes                                  | RDS PostgreSQL; Valkey for serving-relevant mutations; ClickHouse for usage views; Stripe  | human sessions, organizations, workspaces, invitations, API keys, model catalog, billing operations, usage views and generated API/docs                    | serve inference, serve console assets, run asynchronous settlement loops, authenticate hot-path keys, own Rust behavior |
| `worker`         | TypeScript/Node Kubernetes Deployment using the same image as `api`                     | RDS PostgreSQL; Valkey; ClickHouse Cloud                                                   | periodic PostgreSQL-to-Valkey reconciliation/rebuild, `GenerationSettled` ingestion into ClickHouse and global-slot settlement into PostgreSQL             | expose a public/application API, write PostgreSQL per generation, retain prompts or completions                         |
| `temporal-worker` | Separate TypeScript/Node Kubernetes Deployment using the product image | Temporal Cloud; RDS PostgreSQL; S3/KMS | encrypted training workflows and activities | run ingestion or settlement loops, connect to Valkey or ClickHouse |
| `collector` | Rust deployment on EKS CPU nodes | S3; local spool; RDS PostgreSQL for task registration | generation-content batches and manifests, idempotent task registration with background retry | wait for PostgreSQL before accepting traces, create Temporal schedules |
| `proxy`          | Rust deployment on EKS CPU nodes; not yet deployed                                      | read-only PostgreSQL; the gateway; Anthropic and OpenAI                                    | relay with customer provider keys, Gradiated key checks for relays, forwarding hosted requests to the gateway, draining and health/metrics                 | charge balances, translate or parse payloads, store provider keys, hold Valkey or ClickHouse clients                    |
| `gateway`        | Rust deployment on EKS CPU nodes, exposed through the public ALB                        | Valkey; the selected SGLang endpoint; generated contract fixtures                          | API-key authentication, exact model lookup, bounds/admission, streaming proxy, cancellation, usage normalization, terminal finalization and health/metrics | query PostgreSQL/ClickHouse, run product CRUD, process Stripe, select providers, provision GPUs, persist prompts        |
| `metabase`       | One Metabase Open Source pod on EKS at `metabase.gradiated.com`                         | dedicated RDS PostgreSQL state database; read-only product PostgreSQL and ClickHouse users | internal analytics, saved questions, dashboards, and Google Sign-In for `gradiated.com`                                                                    | write product data, serve public shares, or become a product data authority                                             |
| `sglang-runtime` | SGLang runtime on the external provider's GPU Kubernetes cluster; never an EKS workload | pinned model/tokenizer artifacts, pinned runtime image, GPU node and provider networking   | execute one exact released model and expose a private OpenAI-compatible runtime endpoint to `gateway`                                                      | authenticate customers, charge balances, expose a public endpoint, choose another model/provider                        |

`api`, `worker` and `temporal-worker` are separate TypeScript applications packaged in one image,
not independently versioned domain services. Keeping them in separate EKS
Deployments prevents a ClickHouse outage or settlement query from affecting the
public API. `worker` runs one replica at launch and supervises each loop with an
independent timeout, backoff and health state. Its protocols remain safe to
split or scale later: Valkey consumer groups divide ingestion, PostgreSQL
advisory locking elects settlement, and projection is level-triggered and
idempotent. Do not create separate projection, ingestion or billing services.

The separate `temporal-worker` application hosts encrypted Temporal training
workflows and activities. The API starts and cancels workflows and directly
updates per-task schedules after saving task settings. Schedule update failures
are logged; users can retry by resubmitting settings. Scheduled workflows check
workspace and organization eligibility before starting training. PostgreSQL owns tasks,
runs, stage events and versions. S3 owns captured traces and large artifacts.
The opt-in `qwen-sft` executor runs a pinned Qwen3-0.6B LoRA recipe on dedicated
RunPod H100s through Nomad. It retains the mock executor for local tests and old
histories. Published adapters remain unavailable until serving qualification. The [training run contract](TASK_FINE_TUNING_RUN_CONTRACT.md)
defines admission, cancellation, retries and workflow compatibility. Temporal
Cloud receives encrypted payloads and failures, and only internal IDs in workflow
metadata. GPU hosts never receive Temporal credentials.
The worker checks pending and running training jobs once per minute and requests
Nomad shutdown when their exact Temporal execution has closed. This also cleans
up queued jobs after workflow timeout or termination, when workflow cleanup cannot run.

## Agent access to production

`product/services/ops-mcp` is the managed MCP interface for agents accessing
Gradiated operations. Its HTTPS endpoint, `https://ops.gradiated.com/mcp`,
requires Gradiated Google login through Dex and scoped MCP OAuth tokens. The
public HTTPS ingress removes Tailscale as a requirement for MCP read tools. Host
registration requires the separate localhost administrative listener, reached
through an authorized port-forward to the private Kubernetes API over Tailscale,
as well as MCP OAuth. The application trusts listener provenance, not caller
headers; Kubernetes administrators retain privileged access. Claude Tag,
Cursor and OpenAI clients share the same Streamable HTTP transport and OAuth
boundary, with exact hosted callback allowlists and loopback support for local agents.

Current tools read alerts, metrics, bounded service logs, dashboard links and EKS
status across tenants. The sole mutation, `register_instance`, enrolls a GPU host
and requires private administrative ingress. Tools expose no general shell, exec,
arbitrary HTTP or database access. Kubernetes permissions remain limited to pod/node listing.
OAuth registration is stateless; hashed token families persist on a single-writer
PVC with refresh rotation, revocation and a fixed 30-day authorization lifetime.
Argo reconciles the service under `operations/` through `platform/ops-mcp.yaml`.

Future administrative operations belong here as individually scoped tools, rather
than a generic admin UI or command executor. Reads require no server-side action
confirmation. Writes must enforce authorization and, when required by the action,
a human approval bound to the exact proposed operation before execution. MCP
annotations and agent instructions describe this policy but cannot enforce it.
The [service README](../product/services/ops-mcp/README.md) defines the approval
contract, client installation and public rollout sequence.

## Dependency and authority rules

### PostgreSQL / RDS

RDS PostgreSQL is the durable authority for Better Auth records,
organizations, workspaces, API keys, the global model catalog, concrete model
deployments, billing account balances and immutable balance transactions. Only the TypeScript application
and its background roles use PostgreSQL repositories. Rust has no PostgreSQL
driver or product repository.

PostgreSQL is not on the inference request path. A successful product mutation
that affects serving must commit its authoritative row, reload the current row
from the primary, synchronously update the corresponding Valkey state and only
then report success. Credentials, workspaces, models, and nonmonetary account
fields are replaceable projections. `GatewayAccount.balance` is the exception:
ordinary operation applies PostgreSQL-originated monetary transactions as
idempotent deltas and never overwrites the balance with the PostgreSQL row,
because Valkey also contains finalized usage not yet posted to PostgreSQL.
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
- exact route-ready `GatewayModel` records containing their deployments;
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

### Model deployments and GitOps

PostgreSQL owns both the customer-facing global `models` catalog and the
durable `model_deployments` registry. Each deployment row names one private
SGLang URL and one closed exact runtime/model/tokenizer release. The TypeScript
control plane projects each model and all of its deployments as one complete
`GatewayModel` document in Valkey; Rust never reads PostgreSQL or a local
routing manifest.

Git still owns the Kubernetes/SGLang workload declaration, image digest and
provider infrastructure that create the endpoint. The deployment workflow
registers a ready endpoint in PostgreSQL and drains the previous row explicitly.
This avoids a second Git-owned routing authority while retaining reviewed,
reproducible infrastructure. Volatile health and free capacity are observations,
not PostgreSQL model metadata.

## Application service details

### `console`

The customer console is a Vite/React app using TanStack Router/Query,
Tailwind and shadcn/ui. It uses only the generated TypeScript client for the
API service. It does not share database types directly and never receives
secret API-key material after the one-time creation response.

Production hosts the console at `console.gradiated.com` and all public API
traffic at `api.gradiated.com`. Local development runs Vite on port 3000 and
proxies API requests to port 3001. On the public ALB, `/api`, `/health`, `/docs`
and the runtime ingest paths `/v1/deployment-status` and `/v1/profiling-events`
route to the TypeScript API service. Every other path, including the
legacy `/openai/v1/*` route, goes to the Rust proxy, which forwards hosted
requests to the gateway inside the cluster. The console does not proxy
inference requests through the API service. The static host must return
`index.html` for console routes so browser refreshes preserve client-side
routing.

Infrastructure endpoints use `/api/internal/` and authenticate independently
of customer sessions. Both the served and generated public OpenAPI documents
exclude this namespace centrally, so the API reference cannot advertise these
routes even if an individual route omits `hide` metadata. The prefix controls
documentation visibility; it does not replace authentication.

### `website` and developer docs

The public Vite website runs at `gradiated.com`. Its docs use the generated
Management API client and the same Better Auth service as the console. The docs
can create workspace API keys through the TypeScript API. A one-time key secret
stays in browser memory and is not persisted.

The docs show inference examples but do not send inference requests from the
browser. The TypeScript API does not proxy inference.

The developer docs information architecture, action rules, and writing standard
are defined in [DEVELOPER_DOCS.md](DEVELOPER_DOCS.md).

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

Management routes follow resource-oriented REST. Existing workspace resources
use `/api/v1/workspaces/{workspace_id}` for updates, deletion, API keys, usage
and generations. The server resolves organization ownership from the workspace
and verifies membership; clients do not supply an organization ID for these
operations. Workspace creation and listing remain organization collections at
`/api/v1/organizations/{organization_id}/workspaces`, alongside organization
billing and balance transactions. The shared model catalog and current-user
resource are outside workspace scope.

Use query parameters for collection filters, such as `generations?task_id=...`,
and `PATCH` on a resource to change its fields. Feature-specific routes are
reserved for intentional workflows such as wizard onboarding, or protocol
boundaries such as authentication, webhooks, health probes and inference.

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

Worker replicas run the idempotent/leader-elected protocols described below.
Each loop has its own timeout, bounded backoff,
lag metrics and failure state so one unavailable dependency cannot terminate or
stall the others. The pod is live while the supervisor is running; readiness
and alerts report each loop separately. It has no application `Service`; a
private PodMonitor scrapes its dedicated metrics listener on port 9464.

### `gateway`

The Rust service exposes the launch inference contract:

- `POST /v1/chat/completions`, streaming and non-streaming;
- `POST /v1/systemone`, non-streaming native Kev pointer inference;
- `GET /v1/models` with only exact currently advertised model IDs;
- `/health/live`, `/health/ready` and `/metrics`.

For each request it authenticates the API-key digest, converts the model ID to
ASCII lowercase, resolves the exact canonical model record, checks
organization/workspace status, applies the operational prepaid
balance/concurrency rule when applicable, and rejects parameters not advertised
by the exact model before contacting SGLang. Invoiced organizations are not
gated or concurrency-limited by their accounting balance. Chat deployments own
prompt rendering, tokenization, and input/context validation; the gateway forwards
qualified messages without a local tokenizer dependency. Native token-ID deployments
require the gateway to prepare their actual input IDs with the pinned tokenizer
and enforce bounds on that payload before admission. The gateway keeps only a
small typed request envelope; the model's Valkey-projected text-output
`supported_parameters` and request-scoped `passthrough_parameters` maps qualify the remaining JSON fields without a
gateway-wide model schema. Each concurrency slot represents
a configured balance amount used to scale prepaid concurrency above a floor of
20 concurrent generations. It is not a reservation or worst-case request-cost
limit. All organizations have a default maximum of 500 concurrent generations;
an explicit lower organization cap takes precedence over the prepaid floor.
Prepaid admission requires a positive balance. Invoiced organizations bypass
balance checks but use the same organization concurrency cap. The gateway forwards only qualified
fields to the model runtime,
preserving cancellation, backpressure and streaming semantics.
For Chat Completions, the optional `service_tier` request field accepts `flex`, `default`, or `fast`.
It defaults to `default`. Chat deployments serve every tier from shared
capacity. The gateway maps `fast` to runtime priority `-10`, `default` to `0`,
and `flex` to `10`. It rejects caller-supplied runtime priority controls. A
retry keeps the requested tier. Successful responses return the effective tier
in `x-gradiated-service-tier`, and browser CORS exposes this header.
An exact model may have multiple available runtime deployments. Each deployment
sends status to Valkey every second through the private telemetry endpoint. The
gateway uses fresh status, a shared concurrency lease, and rendezvous hashing to
select a deployment. A session ID or request-prefix hash keeps related requests
on one deployment when it has capacity. Without a session ID, chat routing hashes
the first 16 KiB of serialized messages; native routing hashes up to 4,096 actual
input IDs. SystemOne hashes the first 16 KiB of serialized state, excluding
questions. Route keys are scoped to workspace, model and served release, with
separate hash domains for state, messages and token IDs. Routing never requires
a second rendering of a chat deployment's prompt. The gateway does not queue. It returns
`429` when all healthy deployments are busy. It returns `503` when no fresh,
healthy deployment exists. It retries once on another deployment only when no
usable output reached the client.

The request captures the tier-adjusted effective model pricing and served release digest at
admission. On terminal success, failure, cancellation or abandonment, Rust
normalizes authoritative token usage, calculates the integer nano-USD charge,
constructs the closed generation properties document and invokes the Valkey
finalization script. A lost process may leave an expired, unbilled generation;
there is no durable in-progress request table at launch.

Native SystemOne accepts an exact model, text/object/array state and 1..64
named `choice`, `noul` or `score` questions with JSON instructions and criteria.
Optional `noul` criteria accept only `false` and `true` keys; unsupported
outcomes are rejected rather than silently discarded by the runtime.
Its closed envelope rejects streaming, output-token controls, caller priority
and unknown fields. Only the default service tier is implemented; `fast` and
`flex` fail before dispatch. Optional session IDs are non-null strings of
1..256 UTF-16 code units. A deployment release declaring `protocol: "system_one"`
selects the native `/v1/systemone` transport and cannot serve chat; an absent
`protocol` means the ordinary OpenAI chat transport.
It shares the existing admission and settlement path. Runtime identity and
answers are validated before rewriting the response model to the public ID.
Authoritative usage counts prefill input and cached input, with output,
cache-write and reasoning tokens fixed at zero. Serialized answers are not
generated model tokens.

The model runtime owns prompt normalization and reports authoritative token usage.
Gateway-local token counts must not veto chat dispatch, abort a response, or
substitute for engine counts in billing. The gateway still validates usage
arithmetic, supported integer ranges, cached/reasoning token bounds, stable input
counts and monotonic counters within a stream, and terminal stream completeness.
Native token-ID transports additionally validate counts against the actual input
and output IDs crossing their boundary; those are measured payloads, not a second
reconstruction of the runtime's prompt.

The explicit Anthropic `count_tokens` endpoint still provides a local estimate;
it does not gate generation or settlement. The DeepSeek estimator mirrors the
pinned chat endpoint's normalization of malformed historical tool arguments to
an empty object. Exact deployment-side counting would require a separate runtime
counting contract; this endpoint must not be treated as billing authority.

Gateway-owned checks remain authentication/authorization, advertised product
parameters and output caps, release identity, fresh deployment health, capacity,
request/response size limits, timeouts, and wire-protocol validity. These validate
access and transport contracts rather than predict deployment behavior.

Rust does not implement human sessions, customer CRUD, Stripe, OpenRouter
onboarding, model purchasing, provider APIs or GPU provisioning.

### `sglang-runtime`

The runtime is one SGLang pod scheduled on the external provider's GPU cluster,
using a pinned image and model revision. It is not deployed to or joined with EKS. A private
Kubernetes `Service` (or the provider's equivalent private endpoint) gives the
EKS gateway a stable upstream address over private connectivity or restricted
TLS.

The deployment exposes readiness only after model load and qualified serving
checks. It uses explicit B300 placement, large shared memory, persistent local
model/compile caches, conservative restart behavior and measured capacity
limits, including bounded `max_running_requests` and `max_queued_requests`.
SGLang enables priority scheduling with lower numeric values first. The native
runtime applies the same order before cache-affinity selection. The scheduler
can batch requests from different tiers after admission. It does not use a
different per-request batch size for each tier. A vLLM deployment must use its
priority scheduling policy. The gateway sends the same trusted `priority`
field to either OpenAI-compatible runtime.
It does not implement customer authentication or billing. A second model is a
second explicit catalog row, `model_deployments` row and SGLang deployment; it
is not a reason to introduce a separate routing layer. Additional deployments
are independent candidates for the exact model.

## External services and infrastructure

| Dependency                    | Used by                      | Purpose                                                                | Launch boundary                                                                                        |
| ----------------------------- | ---------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| RDS PostgreSQL                | `api`, `worker`              | durable product and financial state                                    | private subnets, Multi-AZ, PITR and deletion protection                                                |
| RDS PostgreSQL for Metabase   | `metabase`                   | Metabase users, settings, questions and dashboard state                | private subnets, Single-AZ `db.t4g.small`, 20 GiB gp3, PITR and deletion protection                    |
| ElastiCache Serverless Valkey | `api`, `worker`, `gateway`   | serving projection, leases and generation stream                       | managed Multi-AZ; fail closed when unavailable                                                         |
| ClickHouse Cloud              | `api`, `worker`              | immutable generations, settlement queries and product usage views      | AWS-aligned region through PrivateLink in production; no prompt retention; indefinite launch retention |
| Stripe                        | `api`                        | direct prepaid top-ups and payment events                              | webhook signature verification; no Stripe call from Rust                                               |
| OpenRouter                    | external distribution client | calls the same exact-model endpoint using its channel organization/key | invoiced organization; onboarding/auth contract configured in api/infra                                |
| external Kubernetes provider  | `sglang-runtime`             | dedicated GPU capacity                                                 | provider-owned cluster/node pool; separate from EKS                                                    |
| ECR                           | CI/Argo                      | immutable api/worker and gateway images                                | image digest deployment only                                                                           |
| Secrets Manager               | EKS and deployment bootstrap | database, channel, upstream and remote-cluster credentials             | secrets are injected at runtime, never committed                                                       |
| Route 53 / ACM / ALB          | `api`, `proxy`, `metabase`   | DNS, wildcard TLS and Gateway API routing                              | AWS Load Balancer Controller owns one public ALB; host and path routes select the target service       |
| S3 / CloudFront               | `console`                    | static console hosting and SPA fallback                                | no application API or inference proxy                                                                  |

Production delivery follows [DEPLOYMENT.md](DEPLOYMENT.md). GitHub Actions
builds the product image, gateway image and console from one source revision.
It stages hashed console assets, records immutable image digests in one
release commit directly to `main` after source CI passes, then waits for Argo CD. It publishes the console entry
point only after the backend is healthy. Argo CD does not build images or write
console files.
| CloudWatch / AWS Budgets | platform | AWS control-plane logs, alarms and cost limits | infrastructure and billing signals remain in AWS |
| Prometheus / Grafana | platform | Kubernetes and application metrics, dashboards and alert evaluation | Argo-managed inside the EKS cluster; private access only at launch |

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
Valkey account state. Actual charge is applied only at terminal finalization.
Final in-flight prepaid generations may move their balance below zero, which
blocks subsequent prepaid admission. An invoiced balance records the net
accounting position and does not block admission; organization suspension is
the explicit serving stop.

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
6. one Metabase Deployment and Service, plus its dedicated RDS PostgreSQL
   state database.

Local development preserves these process and network boundaries without
reproducing production packaging. Docker Compose runs PostgreSQL, Valkey and
ClickHouse only. `mprocs` runs Vite, `api`, `worker`, `gateway` and SGLang as
native host processes. On the supported Apple Silicon profile, SGLang uses its
Metal/MLX backend and a pinned small local model; the local model has its own
truthful exact PostgreSQL model and deployment rows rather than masking the
runtime behind a generic alias. The gateway reaches SGLang over its normal HTTP interface on
localhost, so Chat Completions, streaming, usage and cancellation cross the
same runtime boundary as production. The explicit local token-count estimator
is checked against the pinned SGLang release; chat inference itself does not
render or tokenize the prompt in the gateway.

Deterministic runtime failures that a real model server cannot safely induce
use the gateway's in-process `ModelRuntime` test double. There is no deployed
fake-SGLang process. Local development does not require Kubernetes, LocalStack,
AWS credentials, NVIDIA capacity, OpenRouter credentials or Stripe
credentials. Final release conformance runs against the pinned production
SGLang and model deployment because MLX and the small local model prove the
protocol integration, not production model equivalence.

## Implementation rules and complexity gates

- Use one TypeScript application codebase and one Rust hot-path codebase.
- Keep ingestion, settlement and reconciliation in one `worker` process from the `api` codebase
  and image. Split a role into another Deployment only after measured scaling
  or isolation requirements.
- Keep exact model dispatch finite and explicit. Use fresh status, one shared
  concurrency lease, and rendezvous hashing.
- Let the selected runtime own exact scheduler and KV admission. Normalize
  overload to `429`. Do not queue. Retry once before usable output.
- Keep PostgreSQL, Valkey and ClickHouse as separate authorities with no hidden
  cross-store source of truth.
- Do not add Kafka, CDC, an outbox, a service mesh, Karpenter, RDS Proxy or a
  custom operator at launch.
- Run multi-step training as Temporal Cloud workflows in `temporal-worker`, so a failed
  step retries without repeating completed steps. Encrypt every payload and
  failure in `temporal-worker` before it reaches Temporal Cloud.
- Add a second model through model and deployment rows, an SGLang deployment,
  capacity measurement and conformance fixtures.
- Keep provider deployments simple. Put global placement and retry logic in the
  gateway.
- Introduce more workers or services only when a measured SLO, throughput,
  isolation or recovery requirement cannot be met within the existing service.

The approved production scaling decision is to use KEDA for API, worker and
gateway replica counts, and Cluster Autoscaler for CPU node capacity. This
explicitly supersedes the launch restriction for these two controllers. The
initial demand targets are operating defaults, not measured throughput limits;
production burst/recovery calibration remains an operational follow-up.

KEDA manages API, worker and gateway replica counts using application demand plus
CPU and memory triggers. The worker requests 256 MiB with an 80% memory target,
above its observed idle working set, and retains a 512 MiB limit.
Argo owns the ScaledObjects; the generated HPAs own live
replica counts. Cluster Autoscaler adjusts the managed CPU node group between
3 and 20 nodes; Terraform owns those bounds and the initial count, while the
autoscaler owns subsequent desired capacity. Each service scales from 3 to 20
pods. Three low-priority placeholder pods reserve 4.05 CPU cores and 4,224 MiB
for fast scale-out; service pods preempt them and Cluster Autoscaler replenishes
the reservation within the node ceiling. See the
[workload operations](../infra/environments/prod/us-east-1/kubernetes/workloads/README.md)
for thresholds, failure handling and rollback.

The architecture is intentionally narrow until production evidence requires
another boundary.
