# Kimi K3 provider launch plan

- status: current implementation authority
- date: 2026-08-15
- architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

## Outcome

Gradiated will host Kimi K3 on one 8x NVIDIA B300 node with SGLang and sell that inference through two channels:

1. OpenRouter, as the first distribution channel;
2. Gradiated accounts, where a customer creates an API key and calls the same inference data plane directly.

The launch does not include a general model gateway. A request names one exact hosted model. Gradiated does not select another provider, substitute an alias, or fall back to a different model. Adding a model later means adding one explicit model declaration and one SGLang deployment, not adding a routing platform.

## Launch scope rules

The durable service boundaries and the trigger for introducing shared routing are
in [ARCHITECTURE.md](ARCHITECTURE.md). For this launch, they mean one TypeScript
codebase running `api` and `worker`, one Rust `gateway`, and one external
SGLang deployment for one exact Kimi K3 release. PostgreSQL owns product and
deployment-registry state, while Git owns the infrastructure declaration that
creates the SGLang workload.

Explicit first-launch non-goals:

- model aliases or quality/price routing;
- fallback to third-party inference providers;
- a provider marketplace or generic capacity-driver framework;
- custom Kubernetes operators or fleet CRDs;
- a service mesh, Kafka, Temporal, KEDA, or self-managed Karpenter;
- prefill/decode disaggregation, distributed KV cache, or multi-node Kimi K3;
- direct support for Anthropic Messages or OpenAI Responses before demand;
- a second internal API description language beside Zod.

## System boundary

```text
                                      +-----------------------------+
browser ----------------------------> | TypeScript api              |
                                      | Vite + Hono + Zod + Drizzle |
                                      +--------------+--------------+
                                                     |
                                                     v
                                      PostgreSQL / Valkey / ClickHouse

                                      +-----------------------------+
                                      | TypeScript worker           |
                                      | projection/ingest/settle    |
                                      +--------------+--------------+
                                                     |
                                                     v
                                      PostgreSQL / Valkey / ClickHouse

direct API key client ----+
                          |
OpenRouter channel key ----+--------> public ALB
                                           |
                                           v
                                +------------------------+
                                | Rust gateway           |
                                | auth/admission/SSE     |
                                | exact model dispatch   |
                                +-----------+------------+
                                            |
                                 private or restricted TLS
                                            |
                                            v
                                +------------------------+
                                | SGLang: Kimi K3        |
                                | external provider K8s  |
                                | one 8x B300 node       |
                                +------------------------+
```

This is launch topology rather than a separate service specification. There are
three Gradiated processes from two codebases, not a set of domain microservices:

- `api`: TypeScript HTTP API and built Vite assets in EKS;
- `worker`: PostgreSQL/Valkey reconciliation, generation ingestion and billing
  settlement in EKS, using the same TypeScript image as `api`;
- `gateway`: Rust public inference data plane.

SGLang runs on the external provider's B300 node, not in EKS. Its private
Kubernetes Service is only a stable network address for `gateway`. PostgreSQL
and the load balancer are managed services.

## Local development contract

The canonical local path follows the repository's existing native-service
workflow. Docker Compose runs only PostgreSQL, Valkey and ClickHouse. A
checked-in `mprocs.yaml`, normally entered through `pnpm dev`, starts:

- PostgreSQL, Valkey and ClickHouse through Docker Compose;
- the TypeScript API and worker in watch mode;
- the Vite app in watch mode;
- the Rust gateway with `cargo watch`;
- a pinned native SGLang process through a checked-in mise/uv task;
- contract generation/drift checks in a visible pane.

On the supported Apple Silicon profile, native SGLang uses Metal/MLX and a
pinned quantized `mlx-community/Qwen3-0.6B-4bit` release. The local PostgreSQL
model and deployment rows plus their Valkey projections use a separate
truthful exact ID such as `mlx-community/qwen3-0.6b-4bit`; they never label Qwen
as Kimi K3. The gateway connects to SGLang at `http://127.0.0.1:30000`, exercising the
real SGLang health, Chat Completions, SSE, usage and cancellation boundary. The
gateway tokenizes locally from the same deployment-record tokenizer artifact;
local conformance proves its token IDs and counts match this SGLang release.

Required command:

```sh
pnpm dev
```

The native SGLang source/package revision, model revision and tokenizer
revision are pinned, while downloaded artifacts live in an ignored local
cache. Startup migrates and seeds disposable development state and supports a
signup/key/chat smoke test without cloud credentials or paid services.
Deterministic HTTP errors, malformed payloads, truncated streams and timeouts
are covered through the gateway's in-process `ModelRuntime` test double rather
than a separately deployed fake server. Local Kubernetes, LocalStack and a
local observability platform are not required. Production conformance remains
a separate gate against the pinned CUDA SGLang and exact Kimi K3 release.

## Language and ownership boundaries

### TypeScript product application

Use the stack already selected in the repository:

- Node LTS and strict TypeScript;
- Hono;
- Zod v4 and `@hono/zod-openapi`;
- Drizzle over `node-postgres`;
- Vite, React, TanStack Router and Query;
- Tailwind and shadcn/ui;
- Better Auth for human sessions;
- Stripe when direct billing is enabled.

The TypeScript application owns:

- users, organizations, workspaces and memberships;
- creating, listing and revoking API keys;
- product model catalog and workspace model access;
- billing, balance and invoice/top-up workflows;
- usage views and account administration;
- publishing the small gateway record consumed by Rust;
- writing durable product and usage state to PostgreSQL.

The browser never talks to PostgreSQL. It uses only the generated API client.

### Rust inference data plane

Rust owns only hot-path behavior:

- authenticate a direct customer key or OpenRouter channel key;
- resolve an exact advertised model ID;
- enforce request/body/context/output/concurrency bounds;
- reject unsupported parameters before GPU work;
- return an early `429` instead of building a long queue;
- proxy non-streaming and streaming Chat Completions to SGLang;
- preserve cancellation and backpressure;
- normalize errors and authoritative token usage;
- emit bounded usage/telemetry events;
- expose liveness, readiness and metrics.

Rust does not own customer CRUD, PostgreSQL repositories, Stripe, model purchasing, GPU provisioning, a web API, or an admin UI.

### Hot-path state

The authoritative serving-state, billing, generation and settlement contracts
are in [DATA_MODEL.md](DATA_MODEL.md). In summary, inference reads Valkey only;
PostgreSQL and ClickHouse are not on the request path. Launch settlement uses
Valkey leases and a terminal stream, ClickHouse generations, and global
five-minute slots reconciled idempotently to PostgreSQL. There is no projection
queue, Kafka, second cache or monetary reservation system at launch. Prices,
charges and balances use integer nano-USD values with unitless field names.

## API contract rule

[ARCHITECTURE.md](ARCHITECTURE.md) owns the durable Zod/OpenAPI contract rule.
The launch-specific surfaces and conformance requirements are:

Every Gradiated HTTP API is authored from described Zod schemas and a route manifest. The generation chain is:

```text
Zod v4 schemas + route metadata
  -> runtime TypeScript validation
  -> OpenAPI 3.1
  -> Scalar reference
  -> generated Markdown/llms.txt
  -> generated TypeScript browser client
  -> checked Rust data-plane contract artifacts
```

The committed OpenAPI document is generated output. CI must regenerate it and fail on drift, missing descriptions, duplicate operation IDs, undocumented errors, or a breaking change.

The Rust gateway cannot execute Zod, so the TypeScript contracts package is the authoring source and produces checked-in OpenAPI/JSON Schema plus fixtures. Rust validates the same accepted subset and must pass cross-language golden tests. Rust may use handwritten streaming machinery, but it may not invent fields outside the generated contract.

Initial public surfaces:

| Surface         | Owner      | Launch routes                                                                 |
| --------------- | ---------- | ----------------------------------------------------------------------------- |
| product control | TypeScript | `/api/v1/session`, organizations, workspaces, keys, models, usage and billing |
| generated docs  | TypeScript | `/api/openapi.json`, `/api/docs`, `/api/llms.txt`                             |
| inference       | Rust       | `POST /v1/chat/completions`, `GET /v1/models`                                 |
| operations      | Rust       | `/health/live`, `/health/ready`, `/metrics`                                   |

`POST /v1/chat/completions` must support streaming and non-streaming responses. The final streaming event and the non-streaming response must contain input, output and total token usage. Unsupported fields fail explicitly; they are never silently dropped.

## Exact model registry

The canonical PostgreSQL and Valkey schemas are in
[DATA_MODEL.md](DATA_MODEL.md). The launch has one global Kimi K3 model row and
one or more available `model_deployments` rows. Rust resolves the requested
model ID and selects the first available projected deployment. It rejects
unknown, unavailable, retired, or missing routes; there is no request-path
scoring, discovery, retry, fallback, or alias resolution. A second model
repeats the same catalog, deployment-row, SGLang and conformance workflow
without adding a new service or database authority.

## OpenRouter provider contract

The implementation must follow OpenRouter's current provider schema rather than the repository's older spike:

- publish `/v1/models` using the current provider schema (currently schema version 2.4);
- declare identity, Hugging Face ID, modalities, exact capabilities, pricing, capacity, data centers, compliance and `is_ready`;
- implement OpenAI-compatible `/v1/chat/completions` with streaming;
- return usage tokens for streaming and non-streaming calls;
- support automated monthly invoicing;
- publish a privacy policy and explicit prompt retention/training policy;
- return early `429` under saturation and send SSE keep-alive comments during long reasoning pauses;
- maintain at least 95% successful-request uptime for normal routing priority.

The OpenRouter `is_ready` response field is derived from `models.status = 'available'`; it is not a second availability authority.

Provider endpoint authentication details are agreed during onboarding and are not fully specified by the public provider documentation. Implement rotating Bearer credentials with two-key overlap. Add source-IP allowlisting or mTLS only if OpenRouter supplies a stable supported contract; do not guess it.

Advertise only capabilities that pass conformance. Kimi K3 reasoning and tool calling use SGLang's `kimi_k3` parsers, but they do not become public claims until tested through the OpenRouter-shaped request and response.

## AWS control and product infrastructure

Use one AWS workload account and one region aligned as closely as possible with the chosen B300 region. Do not create the old four-account topology for the seed.

Terraform/Terragrunt units:

```text
infra/
  bootstrap/
    state/
    github-oidc/
  modules/
    network/
    dns/
    eks/
    postgres/
    public-ingress/
    registry/
    secrets/
  environments/
    prod/us-east-1/
      terraform/
        root.hcl
        network/
        dns/
        eks/
        postgres/
        cache/
        public-ingress/
        registry-secrets/
        platform-iam/
        argocd-bootstrap/
      kubernetes/
        platform/
        workloads/
          api/
          worker/
          gateway/
          models/kimi-k3/
  charts/
    api/
    worker/
    gateway/
    sglang-model/
```

Initial AWS resources:

- one three-AZ VPC with public ingress subnets, private EKS subnets and database subnets with no default route;
- one EKS cluster;
- one fixed managed CPU node group across three AZs; no Karpenter or EKS Auto Mode initially;
- RDS PostgreSQL Multi-AZ with encryption, PITR and deletion protection;
- ECR repositories for the TypeScript and Rust images;
- Secrets Manager for database, channel and upstream credentials;
- a Terraform-owned Route 53 zone and ACM certificate, plus one AWS Load Balancer Controller-owned public ALB for `api.gradiated.com` and static hosting for `console.gradiated.com`;
- CloudWatch logs, alarms and AWS budgets, plus Argo-managed Prometheus and Grafana inside EKS;
- one Amazon ElastiCache Serverless cache using Valkey, provisioned before any inference traffic is enabled.

Do not add RDS Proxy, a service mesh, a separate ingress proxy, a data warehouse, or a workflow engine without a measured trigger.

## Terraform, Terragrunt and GitOps

Keep Terragrunt because the repository already uses it and the AWS/provider split creates repeated state and identity wiring. Keep it shallow: one unit owns one state object and Terragrunt contains no business logic or hidden hooks.

Terraform owns foundational AWS resources, IAM, EKS, ACM, the Route 53 zone, controller prerequisites and the minimum Argo CD bootstrap. Terraform installs only Argo CD and its root application. Argo CD owns Kubernetes workloads, AWS Load Balancer Controller, ExternalDNS and Gateway API objects after bootstrap. AWS Load Balancer Controller owns the physical ALB, listeners, target groups, security-group reconciliation and IP target registration derived from those objects.

GitHub Actions uses OIDC, not AWS access keys:

- pull request: format, validate, lint, policy checks and changed-unit plans;
- merge to `main`: rebuild an exact plan, apply changed non-destructive units in dependency order, then smoke test;
- production data/destructive changes: protected GitHub environment approval;
- application build: test, build one immutable image, scan/sign it and push to ECR;
- application release: update the GitOps image digest in a reviewed commit; Argo deploys it.

CI does not routinely run `kubectl apply`. Argo does not call AWS directly, but its reconciled AWS Load Balancer Controller and ExternalDNS objects deliberately create the ALB resources and selected application DNS records.

## External B300 Kubernetes plane

The first provider must offer:

- one schedulable 8x B300 node with NVLink and at least the model recipe's host memory/storage needs;
- managed Kubernetes or a Kubernetes cluster we can operate without joining it to EKS;
- GPU drivers compatible with the pinned SGLang image;
- local NVMe suitable for model and compile caches;
- a supported private connection to AWS, or a TLS load balancer with source restriction for the benchmark phase;
- on-demand capacity before production traffic;
- observable preemption, node and GPU health.

CoreWeave is the concrete first candidate: its `b300-8x` instance has 8x 270 GB B300 GPUs, 4 TB host RAM, 61.44 TB local storage, NVLink and InfiniBand. The current SGLang Kimi K3 cookbook identifies B300 as a one-node, eight-GPU deployment shape.

Do not build a generic capacity-provider API before choosing the provider. If CoreWeave is selected, implement only the CoreWeave cluster/node-pool Terraform needed. If the provider API cannot safely be automated, record cluster/node-pool creation as a narrow bootstrap runbook and keep the SGLang workload in Argo.

One Argo CD instance in EKS may manage the external model namespace using a namespace-scoped remote credential. Provider cluster/node-pool resources remain Terraform/provider-owned; Argo owns only the namespaced SGLang workload. If namespace-scoped remote management is not supported cleanly, run Argo only for EKS and use the provider's native GitOps facility rather than adding a second custom controller.

## Kimi K3 SGLang baseline

Start with the simplest official one-node B300 profile:

- one pod, one node, all 8 GPUs, TP8;
- pinned Kimi K3-capable SGLang image digest;
- `moonshotai/Kimi-K3` pinned to an immutable revision;
- `kimi_k3` reasoning and tool parsers;
- metrics enabled;
- large `/dev/shm` and persistent node-local compile/model caches;
- a startup probe that permits the full model load, a readiness probe for serving, and a liveness probe for a wedged process;
- `Recreate` deployment strategy and explicit B300 node selector/toleration.

First establish a stable unified TP8 baseline. Do not initially enable DSpark speculative decoding, hierarchical cache, prefill/decode disaggregation, or an unverified long-context profile. Benchmark those one at a time after correctness, memory headroom and restart behavior are measured. A reported B300 DSpark/long-context crash is a specific reason to keep the first launch conservative even though that issue has since been closed.

Spot is permitted only for setup and benchmarks. Switch to on-demand capacity before OpenRouter production testing. A single node is acceptable for the first launch but is a known availability boundary; add a second same-model node only after traffic or uptime proves the need.

## Data-model boundary

[DATA_MODEL.md](DATA_MODEL.md) is the canonical source for the launch schema.
This plan does not repeat its table definitions. The launch needs the existing
control-plane identity, workspace, key, model and billing state plus ClickHouse
`generations` and the Valkey serving projection. Do not add fleet, routing,
trace-intelligence, experiment or provider-pricebook tables for Kimi K3.

## Delivery phases

### P0 — Documentation and contract reset

Outcome: the repository has one active launch plan and no active general-gateway plan.

- Keep the account, organization/workspace, API-key, billing, Vite/shadcn, Hono/Zod/OpenAPI and deletion requirements.
- Replace the old gateway blueprint with an inference data-plane document.
- Replace old Responses/Anthropic launch scope with Chat Completions plus `/v1/models`.
- Remove active plans for third-party provider routing, `grad/<effort>/<speed>` aliases, fleet CRDs, generalized capacity drivers and a separate inference router.
- Mark dated research/audits as historical evidence rather than implementation authority.

Acceptance:

- the root README and architecture document point here;
- no active implementation document instructs an agent to build a general gateway;
- retained product requirements are linked, not deleted.

### P1 — Contract-first vertical slice with native SGLang

Outcome: a direct key and an OpenRouter channel key can make streamed and
non-streamed requests through the gateway to a real native SGLang process
locally.

- scaffold the TypeScript monorepo, Rust workspace and generated contracts;
- add the datastore Compose stack, native SGLang mise/uv task and `mprocs.yaml` before feature work;
- define Zod/OpenAPI Chat Completions and provider `/v1/models` profiles;
- generate the TypeScript client/docs and Rust fixtures;
- implement Rust auth, exact model lookup, bounds, streaming, cancellation and usage against native SGLang;
- cover deterministic runtime error cases through the `ModelRuntime` test boundary;
- implement the minimal TypeScript account/key/model routes against local PostgreSQL;
- build the first Vite/shadcn pages for sign-in, workspace, keys, models and usage.

Acceptance:

- generated artifacts have no diff after regeneration;
- official OpenAI clients pass streaming and non-streaming tests against the Rust gateway;
- unsupported parameters produce no upstream request;
- a revoked test key is denied and cross-workspace access properties pass;
- browser code imports only the generated API client.
- `pnpm dev` starts the datastore containers and native services, and the local end-to-end smoke passes against real SGLang.

### P2 — AWS foundation and GitOps

Outcome: EKS, RDS, ECR, Secrets Manager, DNS/TLS and Argo CD are online from Terraform/Terragrunt.

- implement bootstrap/state/OIDC and the five shallow production units;
- deploy Argo CD root app;
- deploy `api`, `worker` and `gateway`; keep public inference closed until the external Kimi K3 runtime is qualified;
- run schema migrations as an explicit release job;
- configure logs, alarms, budgets, backups and restore smoke tests.

Acceptance:

- a clean account can be rebuilt from bootstrap instructions;
- pull requests plan and merge applies use GitHub OIDC;
- no database is public and no static AWS key exists;
- Argo reports healthy and rollback changes only image/config digests;
- public TLS Chat Completions smoke passes through the ALB.

### P3 — External B300 and Kimi K3

Outcome: one external Kubernetes B300 node serves pinned Kimi K3 through the Rust gateway.

- select provider/region and prove networking to the aligned AWS region;
- provision the external Kubernetes cluster/node pool;
- deploy the SGLang chart with the conservative TP8 profile;
- pre-stage weights/caches, record cold start and prove restart behavior;
- run correctness, tool/reasoning, context, memory, TTFT, throughput, concurrency and overload tests;
- derive the advertised capacity and early-429 threshold from measurements.

Acceptance:

- exact hardware, driver, image and model revisions are recorded;
- no request can address a different model or unauthenticated SGLang port;
- streaming cancellation stops upstream work;
- final usage matches the qualified tokenizer within the defined contract;
- a 24-hour soak has no unclassified 5xx, GPU error or stuck stream;
- the node can be released with no provider resource left running.

### P4 — OpenRouter onboarding

Outcome: Kimi K3 is accepted and receives bounded OpenRouter production traffic.

- submit the provider application with endpoint, model schema, pricing, capacity, region, privacy/retention policy and status page;
- confirm the onboarding authentication and invoice contract;
- stage with model `status = 'unavailable'`;
- pass OpenRouter baseline tests, then enable bounded traffic;
- switch GPU capacity from Spot to on-demand before going live;
- monitor TTFT, throughput, uptime, 429 and invoice-versus-usage reconciliation.

Acceptance:

- streaming and non-streaming usage are present;
- advertised capabilities match tested behavior;
- successful-request uptime remains at or above 95%;
- saturation returns early 429 rather than queued timeouts;
- no prompts or credentials appear in logs;
- OpenRouter and Gradiated usage totals reconcile within an agreed tolerance.

### P5 — Direct account launch

Outcome: a customer can sign up, fund an account, create a workspace key and call Kimi K3 directly.

- finish Better Auth and organization/workspace flows;
- add Stripe/prepaid ledger workflows retained from the product specification;
- provision Amazon ElastiCache Serverless for Valkey and publish gateway key, policy, and balance records;
- run synchronous projection plus periodic reconciliation and prove fail-closed, rebuild and propagation behavior;
- enable Rust atomic balance/concurrency admission and terminal settlement for direct keys;
- run the ClickHouse ingestion consumer and chronological PostgreSQL settlement worker, and prove crash, replay and multi-pod leadership behavior;
- expose balance, keys, models and usage in the Vite/shadcn app;
- run duplicate, cancellation, failure and reconciliation state-machine tests.

Acceptance:

- no GPU request starts without authenticated, bounded paid admission;
- PostgreSQL remains financial authority and balances reconcile to Valkey projections;
- key secrets are shown once and revocation takes effect within the stated SLO;
- the browser completes the signup-to-first-stream flow using generated APIs only;
- OpenRouter channel accounting is isolated from customer prepaid balances.

### P6 — Add the second model

Outcome: the architecture proves it can add a model without becoming a gateway platform.

- add one PostgreSQL model row, one `model_deployments` row and one SGLang deployment;
- add exact capability/pricing/capacity fixtures;
- expose it through the same `/v1/models` and Chat Completions endpoint;
- retain exact-ID dispatch and independent overload limits.

Acceptance:

- no model fallback or alias behavior appears;
- failure or saturation of one model does not consume the other's capacity;
- adding the model does not add a new Gradiated service or database authority.

## Launch order and dependencies

```text
P0 -> P1 -> P2 -> P3 -> P4
             |             |
             +-----------> P5
P4 or P5 ----------------> P6
```

OpenRouter is the first revenue path, so P4 precedes the full direct billing launch. P1 still builds the direct-key contract and account skeleton so OpenRouter does not become a separate architecture.

## Build order after this plan is accepted

We will implement this together in small vertical steps:

1. repository toolchain, generated contracts, datastore Compose, mprocs and native SGLang;
2. Vite/React/shadcn app shell and the signup/workspace/key/model/usage screens against generated mock handlers;
3. TypeScript/Hono API and worker, PostgreSQL schema and generated OpenAPI/client/docs;
4. Rust gateway against native local SGLang;
5. AWS/Terragrunt/Argo foundation;
6. external B300 Kimi K3 deployment and OpenRouter onboarding;
7. direct paid admission and billing hardening.

The UI is built against the generated contract rather than waiting for the backend. The TypeScript API service implementation then replaces mocks route by route. Rust consumes the same fixtures, so data-plane work cannot silently diverge from the API documentation.

## Complexity triggers

Add complexity only when one of these measured conditions occurs:

| Candidate                           | Trigger                                                                              |
| ----------------------------------- | ------------------------------------------------------------------------------------ |
| second Kimi K3 node                 | uptime below target, sustained early 429s, or profitable demand above one node       |
| autoscaler                          | at least two homogeneous nodes and manual capacity changes miss the response SLO     |
| multi-region                        | measured customer latency/residency demand and a funded data-replication plan        |
| RDS Proxy                           | measured connection exhaustion after ordinary pooling is tuned                       |
| additional protocol                 | signed customer/channel demand that Chat Completions cannot serve                    |
| distributed cache/PD disaggregation | controlled benchmark shows enough unit-cost gain to repay complexity                 |
| analytics store                     | PostgreSQL usage queries miss their SLO after indexes/rollups are measured           |
| generic provider abstraction        | a second selected provider has a real implementation and shared code is demonstrated |

## Current external references

- [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers)
- [OpenRouter provider application requirements](https://openrouter.ai/providers/apply)
- [SGLang Kimi K3 cookbook](https://docs.sglang.io/cookbook/autoregressive/Moonshotai/Kimi-K3)
- [SGLang Kimi K3 roadmap](https://github.com/sgl-project/sglang/issues/32607)
- [CoreWeave 8x B300 specification](https://docs.coreweave.com/platform/instances/gpu/b300-8x)
