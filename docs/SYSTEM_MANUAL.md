# Grad system manual

Status: canonical seed implementation contract

Audience: founder reviewers, implementation agents, operators and security reviewers

This manual defines the complete system that the first implementation must produce. It is the entry point for implementation. Detailed subsystem documents remain authoritative for algorithms and field-level behavior, but they may not contradict this manual, the accepted ADRs or the current simplicity review.

The words **must**, **must not**, **required** and **forbidden** are acceptance criteria. “Later” means absent from the seed code, schema and infrastructure unless a named work package explicitly introduces it.

## 1. Document authority and reading order

When documents disagree, use this precedence:

1. accepted ADRs, with explicit supersession notes applied;
2. [the simplicity review](SIMPLICITY_REVIEW.md), which is the seed dependency and persistent-field authority;
3. this manual and [the contract catalog](implementation/CONTRACT_CATALOG.md);
4. current implementation blueprints under `product/docs` and `infra/docs`;
5. dated research, spikes and historical deep dives.

An agent must stop and open an architecture issue when two sources at the same level disagree. It must not silently choose one. Dated documents that describe ClickHouse, fleet CRDs, tRPC, Chat Completions or Embeddings as seed requirements are historical unless a current blueprint explicitly restores them.

Implementation starts with:

- [System diagrams](SYSTEM_DIAGRAMS.md)
- [Contract catalog](implementation/CONTRACT_CATALOG.md)
- [Document status and precedence](implementation/DOCUMENT_STATUS.md)
- [Physical data model](implementation/DATA_MODEL.md)
- [Package boundaries and core interfaces](implementation/PACKAGE_BOUNDARIES.md)
- [Parallel path ownership registry](implementation/PATH_OWNERSHIP.md)
- [Work package catalog](implementation/WORK_PACKAGES.md)
- [Verification and launch matrix](implementation/VERIFICATION_MATRIX.md)
- [Operations manual](implementation/OPERATIONS_MANUAL.md)
- [Product implementation blueprints](../product/README.md)
- [Infrastructure implementation blueprints](../infra/README.md)

## 2. Company and product outcome

Grad is a prepaid AI inference gateway and an owned inference provider.

The seed earns revenue by giving developers one smooth endpoint for a curated set of direct model providers. It learns from customer-authorized traces and recommends compatible Grad-owned releases. Grad-owned inference is also available through other gateways, beginning with OpenRouter, so adoption does not require replacing a customer’s existing router.

The first release is successful only when a new organization can:

1. sign in and receive one Default workspace;
2. add prepaid USD credit through Stripe;
3. create a workspace API key;
4. call Models, OpenAI Responses or Anthropic Messages;
5. receive a streamed response with correct usage and exactly-once settlement;
6. inspect usage and, in Product Intelligence mode, authorized encrypted trace detail;
7. opt into Private/No Retention without disabling ephemeral KV/prefix cache;
8. set workspace/key limits and observe fail-closed enforcement;
9. delete the organization without support;
10. later call a qualified `grad/<effort>/<speed>` release directly or through OpenRouter.

## 3. Seed scope

### 3.1 Required customer surface

- Better Auth email/password sign-up/sign-in, email verification, session and recovery through SES; OAuth 2.1 provider support is for MCP. Social login is deferred.
- Organizations, organization membership and invitations.
- Exactly one non-deletable Default workspace per organization.
- Additional workspaces, workspace membership, data policy and limits.
- Terminal archival of non-Default workspaces with key revocation and retained financial evidence.
- Display-once workspace API keys with revoke and expiration.
- Organization-level prepaid USD credit, top-ups, refunds and immutable ledger history.
- Optional monthly workspace/key spend caps and concurrency caps.
- Curated direct-provider models with exact provider/model identity.
- First-party published `grad/<effort>/<speed>` model aliases.
- `GET /v1/models`, `POST /v1/responses` and `POST /v1/messages`, including streaming.
- Usage, cost, latency and trace views backed by PostgreSQL and encrypted S3 objects.
- Product Intelligence retention choices of 7 or 30 days, defaulting visibly to 30 days; No Retention emits no payload object.
- Explicit migration recommendations and bounded evaluations; never automatic traffic replacement.
- Self-service organization deletion.
- Generated OpenAPI 3.1, Scalar docs, TypeScript client, agent Markdown and allowlisted MCP tools.
- Configuration recipes for customer gateways and one native OpenRouter distribution channel.
- Public pricing, service status, support/security contacts, Terms, Privacy and Acceptable Use documents before accepting paid traffic.

### 3.2 Required internal capability

- Atomic Valkey authentication, policy, reserve, concurrency, reservation lease and billing-event append.
- Append-only balanced PostgreSQL ledger and rebuildable balance projections.
- Reconciliation and conservative Valkey projection rebuild.
- Encrypted asynchronous trace capture and cryptographic deletion.
- Immutable catalog releases, aliases, exact pricing and rollback.
- Private inference router and authenticated external GPU serving cells.
- Single-node and multi-node cell topology support.
- Native and managed-Kubernetes capacity-provider driver paths.
- Tenant-salted active-sequence KV cache and cross-request prefix reuse for every generative Grad release.
- Python-first always-on research factory, immutable bundles, independent qualification and human public promotion.
- AWS/EKS platform, Terraform/Terragrunt, Argo CD/Helm, KEDA, protected CI and recovery drills.

### 3.3 Explicitly absent from seed

- tRPC, handwritten browser clients or a second MCP business implementation;
- Chat Completions, Embeddings, images, audio, batches, files or hosted provider tools;
- arbitrary provider marketplace, BYOK, route builder or customer-configured fallback graph;
- per-workspace wallets, arbitrary currencies or custom billing periods;
- ClickHouse, Kafka, a generic event bus or an analytics microservice;
- fleet CRDs, fake Kubernetes Nodes, a cross-provider cluster, Karmada, Crossplane or a service mesh;
- self-managed Karpenter unless EKS Auto Mode qualification fails;
- automatic public model promotion or automatic customer migration;
- durable prompt/KV cache storage or payload use for training without separate explicit consent.

## 4. Product concepts and invariants

| Concept | Meaning | Authority |
| --- | --- | --- |
| User | Human identity owned by Better Auth. | Better Auth PostgreSQL tables |
| Organization | Customer, tenant and billing boundary. | PostgreSQL |
| Workspace | Access, key, model policy, data mode, usage attribution and limit boundary. | PostgreSQL; Valkey serving projection |
| API key | Display-once workspace credential resolving exactly one organization/workspace. | PostgreSQL digest; Valkey lookup projection |
| Credit | Organization-level prepaid USD liability. | Balanced PostgreSQL ledger |
| Direct model | Curated exact provider/model/version identity. | Immutable model release |
| Grad model | Owned immutable release addressed by effort/speed alias. | Release/alias rows and signed bundle |
| Trace | Optional encrypted request/response evidence for customer features. | PostgreSQL authorization metadata + S3 ciphertext |
| Distribution channel | External router that authenticates and settles under its own commercial account. | PostgreSQL channel ledger/domain |
| Capacity provider | Infrastructure vendor supplying GPU resources. | PostgreSQL fleet state + one Rust driver |
| Serving cell | One exact-release routing, failure and cache unit containing one or more nodes. | Authenticated router registry; PostgreSQL lifecycle evidence |
| Bundle | Content-addressed complete model/runtime/topology artifact. | S3/ECR bytes + PostgreSQL record |

Non-negotiable invariants:

- An organization owns money; a workspace never has an independent balance.
- A request is never sent upstream before a durable atomic reservation succeeds.
- Money uses checked signed integer micro-USD. Floating point is forbidden.
- The gateway’s only synchronous internal state dependency is Valkey.
- Direct requests never change provider/model/version.
- Grad requests never leave owned inference or silently change effort/speed/release.
- Unsupported capabilities fail before reservation and provider spend.
- Product Intelligence is default; a request may tighten but never loosen retention policy.
- No-retention suppresses durable payload capture, not ephemeral execution or KV cache.
- PostgreSQL owns durable business state. Kubernetes owns no business object.
- Research can propose and qualify; only release authority can move a public alias.
- Every external GPU allocation has a budget, owner, expiry, cleanup proof and orphan sweep.

## 5. System planes

### 5.1 Experience plane

The static React/Vite application is served by CloudFront from private S3. It uses shadcn/ui and Tailwind and calls only the generated OpenAPI client. It contains no business rules beyond display, input assistance and optimistic state that is revalidated by the API.

The seed navigation is Overview, API keys, Models, Usage and Billing, with organization/workspace settings. The Default workspace stays visually implicit until another workspace exists. The UI must make exact model identity, actual charged amount, data mode, trace capture state and failure reason visible without exposing routing machinery.

### 5.2 Control plane

The Hono control image has role commands rather than separate codebases:

| Role | Responsibility | Durable dependencies |
| --- | --- | --- |
| `api` | REST, Better Auth integration, RBAC, product commands/queries, Stripe endpoint, research BFF and transactional email | PostgreSQL; bounded calls to Stripe, SES, research and Valkey publisher |
| `financial` | billing stream posting, outbox publication, reconciliation and projection rebuild | PostgreSQL + Valkey + Stripe where needed |
| `intelligence` | trace ciphertext persistence, retention and recommendation jobs | PostgreSQL + Valkey trace stream + S3/KMS |
| `trace-access` | authorize and decrypt exactly one trace object | PostgreSQL + S3/KMS + single-use Valkey nonce |
| `mcp` | OAuth-authenticated Streamable HTTP adapter over REST | REST API only |

Domain packages do not import Hono, React, Drizzle, Redis, Stripe or AWS SDK types. Transport validates input, application services enforce use-case policy, domain code owns state transitions, repositories own scoped persistence, and adapters own external protocols.

### 5.3 Serving plane

The Rust public gateway:

1. bounds and parses one supported public protocol;
2. resolves the credential and immutable release from Valkey;
3. validates policy and capability;
4. computes conservative maximum sell exposure;
5. atomically reserves credit/exposure and concurrency;
6. invokes an exact direct adapter or the private inference router;
7. streams while metering protocol-native events;
8. settles once or permits lease-based terminal recovery;
9. optionally appends an already-encrypted trace envelope.

It cannot reach PostgreSQL, Stripe, S3, KMS decrypt, Kubernetes, research services or capacity-provider APIs.

### 5.4 Owned inference plane

The AWS-hosted private inference router maintains an in-memory registry of authenticated cell connections and heartbeats. External coordinators open outbound long-lived mTLS HTTP/2 connections to a dedicated cell-connect endpoint; cells require no inbound public port. The router dispatches only to ready cells attested for the exact admitted release. It never allocates capacity and never queries PostgreSQL per request.

Each external cell contains a coordinator/cell agent and one or more runtime members. The cell agent verifies the signed bundle and topology, starts the runtime, owns local replica scheduling and cache trust domains, reports readiness and drains on interruption. A required member loss fences the complete cell for the seed.

Fleet planner, provider drivers, enrollment and sweeper are slow-path Rust roles. PostgreSQL allocation/member leases are durable authority. One driver owns each capacity source and calls only that provider’s lifecycle API. Native resources remain native; managed-Kubernetes providers use ordinary provider-local Kubernetes resources after capacity acquisition.

### 5.5 Research plane

The Python research service is the sole normal writer of research domain state. Temporal owns durable timers, retries, cancellation and workflow replay, but cannot approve evidence or releases. S3/ECR own immutable artifacts, not lifecycle decisions.

The perpetual loop is observe, hypothesize, preregister, run at the cheapest adequate fidelity, measure, preserve evidence, build a bundle, independently qualify, propose and—only with release-owner approval—promote. Fable and Sol are evidence sources, not runtime dependencies.

### 5.6 Infrastructure and operations plane

AWS contains one isolated workload account/VPC per environment. Private EKS runs stateless roles and bounded research jobs. Aurora PostgreSQL, qualified durable Valkey, S3, ECR, KMS, Secrets Manager, SES and AWS Private CA provide managed state, email and identity. CloudWatch is the seed logs/metrics/alarm system and the slow-path aggregate signal for fleet capacity; it is not business authority. Terraform/Terragrunt owns cloud resources and Argo CD owns post-bootstrap Kubernetes desired state. KEDA scales application roles; it never changes billing or tenant admission.

## 6. Deployable inventory

| Deployable | Language | Public ingress | Stateful authority | Scale signal | Failure effect |
| --- | --- | --- | --- | --- | --- |
| web | TypeScript static | CloudFront/WAF | none | CDN | console unavailable only |
| control `api` | TypeScript/Hono | control ALB/WAF | PostgreSQL | HTTP concurrency/latency | no control mutations; projected serving continues |
| control `financial` | TypeScript | none | PostgreSQL | billing stream lag | posting/projection lag; protected stream must not overflow |
| control `intelligence` | TypeScript | none | PostgreSQL/S3 metadata | trace backlog | trace features degrade; billing continues |
| control `trace-access` | TypeScript | narrow control route | none | HTTP concurrency | trace detail unavailable |
| control `mcp` | TypeScript | `/mcp` | none | MCP sessions/requests | agent management unavailable |
| gateway | Rust | gateway ALB/WAF | Valkey hot state only | requests/streams/CPU | inference unavailable if no replicas |
| inference router | Rust | private gateway API plus dedicated mTLS cell-connect endpoint | in-memory registry | streams/connections | owned inference unavailable; direct unaffected |
| fleet | Rust | narrow enrollment only | PostgreSQL fleet rows | target deficit/reconcile queue | no new cells; ready cells continue |
| cell | Rust + runtime image | private mTLS tunnel/endpoint | ephemeral cache | cell-local queue/KV pressure | one cell removed; exact release may lose capacity |
| research API/workers | Python | private BFF only | PostgreSQL + Temporal execution | task queues/campaigns | research pauses; serving unaffected |
| Temporal services | official pinned images | private | separate Aurora database/role | workflow load | research execution pauses/replays |

## 7. Durable and ephemeral state

| Store | Required content | Forbidden content | Recovery source |
| --- | --- | --- | --- |
| Aurora PostgreSQL | identity, tenancy, ledger, usage, catalog, trace metadata, fleet, research, audit/outbox | plaintext trace payload, KV cache, Temporal history copies | PITR/snapshot + invariant checks |
| Valkey | versioned serving snapshots, reservations, concurrency, bounded billing/trace streams, grant nonces | business authority, plaintext trace, durable artifact | PostgreSQL projections + conservative uncertain holds |
| trace S3 | envelope-encrypted bounded trace objects | provider credentials, plaintext object, ledger | object versions/lifecycle plus wrapped-key authority |
| artifact S3 | content-addressed manifests, reports, model artifacts | mutable tag authority | immutable digest reconstruction |
| ECR | signed runtime/application images | mutable production tags | digest-pinned rebuild/provenance |
| Temporal DB | workflow histories, timers and activity state | evidence truth, release approval, customer billing | database backup + workflow replay/reconciliation |
| router memory | authenticated ready cell registry and live streams | durable allocation authority | reconnect/heartbeat from cells |
| cell GPU/RAM | active KV and prefix cache | durable trace or cross-tenant cache | cold rebuild |

The complete migration-level PostgreSQL contract is [the physical data model](implementation/DATA_MODEL.md), derived from [the simplicity review](SIMPLICITY_REVIEW.md#minimal-persistent-model). An implementation may add housekeeping fields only when a concrete query, lock, uniqueness constraint or migration requires them and the same package tests that need them.

## 8. End-to-end behavior

### 8.1 Organization activation

Organization creation is one PostgreSQL transaction: organization, owner membership, Default workspace, owner workspace membership, audit and outbox. A Stripe checkout creates only a top-up intent. Credit becomes spendable only after a verified idempotent webhook posts one balanced ledger transaction and publishes a new versioned Valkey account snapshot.

Better Auth recovery and product invitations send through a single SES mail adapter using bounded templates. Email delivery is not identity authority: tokens and invitation state remain in PostgreSQL, sending can be safely retried, and request endpoints do not reveal whether an address exists.

### 8.2 Direct request

The gateway admits against the organization balance and all organization/workspace/key limits. The release fixes provider, upstream model, capabilities, prices and retries. Only eligible endpoints from that release may be attempted, and only before usable output. Settlement records actual usage and releases hold/concurrency in one Valkey transition. The financial worker posts exactly one usage record and balanced sell transaction before acknowledging the stream event.

### 8.3 Grad-owned request

Alias resolution deterministically selects stable or approved canary release before reservation. The immutable digest is part of reservation identity. After admission, the gateway asks the inference router for that exact digest. The router chooses only an authenticated ready cell with the matching attestation. No capacity acquisition, provider fallback or effort/speed downgrade occurs on the request path.

### 8.4 Trace and recommendation

For Product Intelligence, the gateway removes secrets, bounds content, encrypts with a random data key and wraps it to an ingest public key before appending ciphertext. Persistence is asynchronous and shed-able before billing capacity. Trace detail requires current authorization and a short-lived single-use grant. Recommendation creation is an evidence-producing read workflow; it cannot update alias or customer request routing.

### 8.5 Native distribution request

OpenRouter authenticates with a dedicated channel credential. The gateway uses a disjoint Valkey keyspace and channel exposure limit, then invokes the same owned release path. It does not receive or require the downstream customer’s Grad identity. Channel usage posts through the shared balanced transaction implementation into channel-scoped accounts and statements required by the signed contract.

### 8.6 Organization deletion

Deletion immediately marks the organization `deletion_pending`, projects admission suspension and revokes management mutation. During the fixed seven-day cancellation window, no irreversible purge runs. Execution drains/abandons reservations, reconciles usage, refunds eligible unused credit, destroys trace keys/objects, revokes keys and organization-scoped OAuth grants/memberships, invalidates that organization in active session context, and pseudonymizes legally retained financial evidence. The Better Auth user and unrelated organization sessions/memberships survive. Every stage is idempotent and crash/retry tested.

### 8.7 Research-to-production

Experiments consume immutable specifications and budgets. A result produces evidence, not a release. A complete candidate becomes a content-addressed bundle. Independent qualification exercises exact protocol, metering, single/multi-node topology, failure, security, quality, SLO and economics. A human release owner approves a signed proposal; activation creates or points an immutable release/alias. Rollback points the alias to a prior active digest without rebuilding or repricing in-flight requests.

## 9. Consistency, idempotency and time

- All timestamps are UTC; external APIs use RFC 3339 and database values use timezone-aware types.
- Public and internal IDs are opaque, sortable UUIDv7-compatible values unless an external provider supplies identity.
- HTTP mutations that may be retried declare an idempotency requirement in the route manifest.
- Stripe event ID, top-up intent idempotency key, ledger business key, request/reservation ID, billing-event ID, provider allocation identity and workflow ID each have a unique constraint at their authority.
- Snapshot/event consumers compare versions and reject regression. Duplicate equal events are success; same identity with different immutable input is conflict and alerts.
- At-least-once delivery is assumed for outbox, Valkey Streams, provider callbacks and Temporal activities. Exactly-once business effect comes from idempotent authority transactions.
- Clock time never proves money or identity. Leases use explicit epoch/token plus expiry and conservative recovery.

## 10. Error contract

Errors must be stable, machine-readable and safe. Public control APIs use RFC 9457-style problem details with stable `code`, request ID and field errors. Inference endpoints translate canonical classes into protocol-native errors without leaking provider bodies.

Required canonical classes are:

- authentication/authorization;
- validation and unsupported capability;
- model/release unavailable or ambiguous;
- insufficient credit, spend/concurrency/rate limit;
- idempotency conflict;
- provider capacity/rate/server failure;
- timeout/cancellation before or after usable output;
- dependency unavailable;
- internal invariant violation with incident ID.

Policy/authentication/capability errors are never retried. Provider retries are bounded, pre-output only and remain inside the exact release. An invariant violation fails closed, preserves evidence and suspends only the smallest safe authority scope.

## 11. Security and privacy model

### 11.1 Trust boundaries

- Browser sessions use secure HttpOnly cookies, CSRF protection and strict origin policy.
- Public inference uses hashed API/channel credentials and bounded TLS ingress.
- MCP uses OAuth authorization code + PKCE and calls REST only.
- Workload roles use EKS Pod Identity and purpose-scoped IAM/database roles.
- External cells enroll with one-use allocation/member tokens, generate private keys and receive short-lived AWS Private CA mTLS identities.
- Provider lifecycle credentials never enter gateway, router, cells, browser or research artifact.
- Gateway has trace encryption-only material; trace-access alone has scoped decrypt.

### 11.2 Data policy

Product Intelligence permits bounded encrypted payload retention for customer-visible features under workspace retention. It is not training consent. Private/No Retention emits no payload envelope or durable prompt/completion but still records minimum financial/security usage and uses ephemeral cache isolated by opaque workspace/channel, release and retention class.

No logs, metrics, traces, fixtures, CI artifacts, issue bodies or support bundles may contain credentials, prompts, completions, tool arguments/results or cache content. High-cardinality customer/request detail belongs in protected PostgreSQL operational queries, not metric labels.

### 11.3 Supply chain

Dependencies are locked. CI produces SBOMs, provenance and keyless signatures. Images and bundles deploy by immutable digest. Model source/license, checkpoint hashes, tokenizer/config, custom code, runtime, kernels and topology are part of qualification evidence. Production promotion never rebuilds mutable source.

## 12. Reliability and degradation

| Failure | Required behavior |
| --- | --- |
| control API/Aurora unavailable | existing projected serving continues within Valkey bounds; no control mutation/top-up completion |
| Valkey unavailable or durability uncertain | reject new paid requests; do not guess credit or dispatch upstream |
| billing consumer unavailable | admission continues only while protected stream capacity/SLO permits; alert and scale consumer |
| trace stream/S3/KMS unavailable | billing and serving continue when policy allows; mark capture skipped; never spill plaintext |
| direct provider unavailable | bounded pre-output retry only inside exact release; otherwise fail and settle correctly |
| inference router unavailable | Grad-owned requests fail; direct requests remain available |
| cell/member interrupted | fence cell, stop assignment, pre-output retry only if another exact cell is eligible |
| provider cleanup uncertain | freeze new acquisition for that source and run independent resource sweep |
| Temporal/research unavailable | pause/replay research; serving and release heads are unchanged |
| bad release | stop canary and atomically restore prior alias digest |
| ledger/projection mismatch | suspend affected account, reconcile, append corrections only; never rewrite history |

Initial SLOs and recovery objectives are hypotheses until measured. Their authoritative list and evidence gates are in [the verification matrix](implementation/VERIFICATION_MATRIX.md).

## 13. Environments and configuration

Local uses Docker Compose for PostgreSQL, Valkey, MinIO and deterministic fake Stripe/provider/cell services; research adds Temporal. `grad start` orchestrates source processes through mprocs and emits health/seed instructions. No real key is required for the default path.

CI uses disposable Testcontainers/Kind and fake services. Protected jobs receive scoped provider/AWS secrets with hard token, request, dollar and time caps.

AWS uses four seed accounts: management, security/log, non-production and production. Each workload environment has an isolated VPC, EKS, Aurora, Valkey, data buckets and KMS/IAM boundary. Configuration is typed and validated at startup. Secret values live in external secret stores and never in Git, Terraform variables committed to Git, command-line flags or generated documentation.

## 14. Build and release rules

The dependency-safe implementation waves are defined in [work packages](implementation/WORK_PACKAGES.md). Agents may work in parallel only when their packet inputs are already frozen and their owned paths do not overlap.

Every packet must include:

- one issue and active task packet;
- exact paths and one contract owner;
- inputs, outputs, migrations and compatibility behavior;
- deterministic examples plus property/state tests for invariants;
- fake integration tests before protected external tests;
- observable success/failure and a rollback/cleanup procedure;
- generated artifact checks where applicable;
- updated handoff and a commit containing only owned paths.

Main builds, tests, signs and deploys one immutable digest. Database/contracts expand before writers, readers tolerate mixed versions, and destructive contraction waits beyond leases/streams/rollback windows. Terraform is forward-fixed and never used as an application rollback.

## 15. Whole-system launch gates

The startup is not production-ready until all of these are evidenced:

1. Cross-language generation and golden fixtures are drift-free.
2. Tenant/RBAC and REST description/MCP allowlist properties pass.
3. Ledger balance, Stripe reorder/duplicate and Valkey reservation/settlement state models pass.
4. Fake official-client E2E passes for Responses and Messages, stream and non-stream.
5. Protected cheapest-model client tests pass without secret/body artifacts.
6. No request is observed upstream without a reservation; every terminal path settles or expires once.
7. Product Intelligence encryption/read/delete and no-retention non-capture/cache isolation pass.
8. Organization deletion crash/retry/refund/purge PBT passes.
9. Aurora restore and Valkey failover/projection rebuild preserve financial invariants.
10. Direct provider identity and Grad exact-release identity never drift under retries/failures.
11. One exact single-node and one exact multi-node bundle qualify through the same production contract.
12. Provider interruption and orphan sweep prove zero leaked owned resources.
13. OpenRouter channel auth, exposure, metering and reconciliation pass its harness and commercial gate.
14. Research workflow replay, budget stop, cleanup and independent qualification pass.
15. EKS rebuild, release rollback and credential/certificate rotation drills pass.
16. Security, legal/accounting, provider terms, pricing/margin and human release-owner gates are signed off.

Passing a test for one model, provider, hardware, region, protocol or topology never transfers qualification to another scope.

## 16. Implementation map

| Area | Canonical detailed source |
| --- | --- |
| product behavior | [Product specification](../product/docs/PRODUCT_SPEC.md) |
| control API/UI | [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md), [REST/OpenAPI/MCP](../product/docs/REST_OPENAPI_MCP_IMPLEMENTATION.md) |
| data model/contracts | [Contract catalog](implementation/CONTRACT_CATALOG.md), [physical data model](implementation/DATA_MODEL.md), [API and data contracts](../product/docs/API_AND_DATA_CONTRACTS.md) |
| billing/admission | [Billing and Valkey](../product/docs/BILLING_AND_REDIS.md), [Gateway](../product/docs/GATEWAY_IMPLEMENTATION.md) |
| public inference | [Protocol profiles](../product/docs/PUBLIC_INFERENCE_PROTOCOLS.md) |
| trace/intelligence | [Model lanes](../product/docs/MODEL_LANES_AND_MIGRATION.md), current sections only |
| distribution | [Distribution implementation](../product/docs/DISTRIBUTION_IMPLEMENTATION.md) |
| owned inference | [Owned inference implementation](../product/docs/OWNED_INFERENCE_IMPLEMENTATION.md), [multi-node](../product/docs/MULTI_NODE_INFERENCE.md) |
| research | [Research factory implementation](../product/docs/RESEARCH_FACTORY_IMPLEMENTATION.md) |
| testing | [Testing and CI](../product/docs/TESTING_AND_CI.md) |
| AWS/platform | [Platform implementation](../infra/docs/PLATFORM_IMPLEMENTATION.md) |
| Kubernetes/GitOps | [Kubernetes and Helm](../infra/docs/KUBERNETES_AND_HELM.md) |
| Terraform | [Terraform and environments](../infra/docs/TERRAFORM_AND_ENVIRONMENTS.md) |
| security/DR | [Infrastructure security and DR](../infra/docs/SECURITY_OPERATIONS_DR.md) |
