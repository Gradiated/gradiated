# End-to-end implementation coverage and architecture audit

> The 2026-07-14 [simplicity review](SIMPLICITY_REVIEW.md) is the current dependency and field authority. It preserves capability coverage while removing ClickHouse, fleet CRDs, self-managed Karpenter and duplicate/derived model and research projections. It retains the durable ledger, Temporal, Terragrunt, KEDA, Kueue/JobSet where needed and a small Kyverno policy set because they replace bespoke correctness or operations code.

> The deeper implementation handoff is now [the system manual](SYSTEM_MANUAL.md), [document status map](implementation/DOCUMENT_STATUS.md), [contract catalog](implementation/CONTRACT_CATALOG.md), [physical data model](implementation/DATA_MODEL.md), [package boundaries](implementation/PACKAGE_BOUNDARIES.md), [path registry](implementation/PATH_OWNERSHIP.md), [work package catalog](implementation/WORK_PACKAGES.md), [verification matrix](implementation/VERIFICATION_MATRIX.md), [operations manual](implementation/OPERATIONS_MANUAL.md), and [Mermaid system views](SYSTEM_DIAGRAMS.md). Together they assign every row below an interface owner, path-owned packet, failure behavior, test and launch gate.

## Audit contract

This is the coverage ledger for the startup architecture. It answers a narrower question than the product specification: **could a junior implementation agent build each part without inventing a source of truth, protocol, failure behavior, security boundary, deployment shape, or acceptance test?**

The audit covers the customer product, control plane, money path, public gateway, retained-data path, owned inference, research factory, external distribution, AWS platform, local development, CI/CD and operations. It excludes model-quality claims, provider economics and production capacity that require measured experiments.

The architecture is complete only when every row has:

1. one authoritative owner and durable source of truth;
2. typed input/output or command/event contracts;
3. transaction and idempotency boundaries;
4. deployment and dependency direction;
5. fail-open/fail-closed behavior;
6. security/data classification;
7. deterministic examples, properties and end-to-end acceptance;
8. an ordered work package and explicit external decision, if any.

### Evidence and falsification

- **Analytical:** coverage and simplification conclusions derived from the repository architecture.
- **Vendor-reported:** capabilities or requirements attributed to current official project/vendor documentation.
- **Unmeasured:** latency, durability, cost, provider supply, model quality and operational thresholds until a dated experiment records them.
- **Falsification rule:** if a junior agent must choose a new authority, add an unplanned synchronous dependency, infer a state transition, invent an error/field, or decide production policy to complete a work package, that row is not implementation-complete.

## Coverage result before this architecture freeze

The original plan had excellent invariant and system-boundary coverage, but only partial implementation coverage. Product intent, billing safety, route identity, retained-data boundaries, external GPU philosophy and research promotion were strong. The missing layer was a consistent component catalog: exact deployables, core interfaces, event envelopes, transaction ownership, configuration and per-package acceptance fixtures.

| Area | Prior decision coverage | Prior implementation coverage | Main gap closed by this freeze |
| --- | --- | --- | --- |
| Product/UX | strong | partial | exact routes, procedures, use cases, RBAC, UI states and staged seed surface |
| Organizations/workspaces/keys | strong | partial | aggregate/repository contracts, transactions, deletion and projection events |
| Payments/ledger | strong | strong-partial | named services/events, webhook transaction and operator repair interface |
| Redis admission/reconciliation | strong | strong-partial | exact request/result structs, function ownership, error map and epoch rules |
| Public gateway/protocols | strong | partial | crate dependency graph, lifecycle state object, adapter traits and stream ownership |
| Model catalog/releases | strong | partial | writer split among ModelOps, research and fleet; immutable projection contract |
| Traces/analytics/migration | strong | partial | encryption envelope, process ownership, outbox schemas and API read paths |
| Owned inference | strong | partial | edge/cell/runtime interfaces, process consolidation and exact readiness contract |
| External GPU fleet | strong | partial | provider-driver classes and direct PostgreSQL allocation/cell reconciliation commands |
| Research factory | strong after ADR-0007 | partial | concrete Python services/classes/workflows, artifacts and promotion API |
| Customer gateway recipes | strong | partial | repository package layout, fixture contract and release ownership |
| Native distribution channels | strong | partial | separate principal envelope, catalog endpoint, settlement lifecycle and onboarding gate |
| AWS/Terraform/EKS | strong | partial | module/chart values contracts, live units, workload identities and creation order |
| Local/CI/release | strong | partial | one canonical command graph, fixture topology and artifact ownership |
| Security/operations/DR | strong | partial | threat/control ownership, operator command catalog and launch evidence index |
| Legal/commercial operations | partial | missing-partial | explicit human-owned terms, tax, privacy, subprocessors and provider-contract gates |

## Coverage result after the implementation-depth pass

The implementation-depth pass closes the coordination layer that remained after the architecture freeze:

| Required implementation fact | Canonical source | Result |
| --- | --- | --- |
| complete product/system behavior and non-scope | [System manual](SYSTEM_MANUAL.md) | defined |
| process, state, deployment and dependency views | [System diagrams](SYSTEM_DIAGRAMS.md) | defined in Mermaid |
| public REST/inference, Protobuf, event, artifact and driver contracts | [Contract catalog](implementation/CONTRACT_CATALOG.md) | defined with ownership/versioning |
| physical tables, constraints, indexes, migrations and database roles | [Physical data model](implementation/DATA_MODEL.md) | defined to migration level |
| package graph, source layout, core classes/traits and forbidden dependencies | [Package boundaries](implementation/PACKAGE_BOUNDARIES.md) | defined for TS, Rust, Python and infrastructure |
| disjoint implementation paths and dependency-safe parallelism | [Path ownership](implementation/PATH_OWNERSHIP.md), [work packages](implementation/WORK_PACKAGES.md) | 71 packets defined from foundation through launch |
| PBT, E2E, load, security, recovery and staged launch evidence | [Verification matrix](implementation/VERIFICATION_MATRIX.md) | defined |
| dashboards, incidents, repairs, rotation, restore and operational handoff | [Operations manual](implementation/OPERATIONS_MANUAL.md) | defined |
| current versus historical source precedence | [System manual](SYSTEM_MANUAL.md#1-document-authority-and-reading-order) | defined; stale ClickHouse/CRD/protocol breadth marked historical |

This is still a plan, not evidence that product code or infrastructure exists. A junior agent no longer owns an architectural choice merely because implementation has not started; it follows the named packet and opens a contract gap when an input is absent.

## Capability coverage matrix after this freeze

`Blueprint` means the implementation contract is frozen in the linked detailed document. `Measured gate` means ordinary code can be built, but production enablement waits for the named evidence.

| Capability | Authority / source of truth | Implementing boundary | Detailed contract | Status |
| --- | --- | --- | --- | --- |
| Sign-in/session/recovery | Better Auth tables for identity/session/recovery; no duplicate product user table | Hono auth mount + Vite routes | [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md) | Blueprint |
| REST/OpenAPI/generated client/MCP | described Zod route registry and committed OpenAPI 3.1 | Hono API, generated client/docs and OAuth MCP REST adapter | [REST/OpenAPI/MCP](../product/docs/REST_OPENAPI_MCP_IMPLEMENTATION.md) | Blueprint |
| Organization/default workspace/memberships | PostgreSQL product domain | TS domain services/repositories | [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md) | Blueprint |
| Self-service organization deletion | PostgreSQL deletion workflow + ledger; S3/KMS payload custody | Hono owner API + financial/intelligence workers | [Organization deletion](../product/docs/ORGANIZATION_DELETION.md) | Blueprint; legal retention policy gate |
| Workspace policy/budgets | PostgreSQL; versioned Redis projection for serving | TS policy service + projector | [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md) | Blueprint |
| API-key lifecycle | PostgreSQL keyed digest; Redis lookup projection | TS key service + Rust auth resolver | [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md), [Gateway](../product/docs/GATEWAY_IMPLEMENTATION.md) | Blueprint |
| Top-up/refund/chargeback | PostgreSQL balanced ledger and Stripe event record | Hono webhook + financial worker | [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md) | Blueprint; fraud/tax human gate |
| Admission/reservation/settlement | Redis atomic projection and event stream; PostgreSQL eventual ledger authority | Rust gateway + Node financial worker | [Gateway](../product/docs/GATEWAY_IMPLEMENTATION.md), [API/data](../product/docs/API_AND_DATA_CONTRACTS.md) | Blueprint; managed-Valkey measured gate |
| Reconciliation/projection rebuild | PostgreSQL ledger/config plus fenced Redis epoch | financial worker/operator command | [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md), [Gateway](../product/docs/GATEWAY_IMPLEMENTATION.md) | Blueprint |
| Public Responses/Messages wire | versioned public schemas and conformance fixtures | Rust protocol modules | [Protocol contract](../product/docs/PUBLIC_INFERENCE_PROTOCOLS.md), [Gateway](../product/docs/GATEWAY_IMPLEMENTATION.md) | Blueprint; per-provider conformance gate |
| Principal authentication | credential lookup selects workspace or channel principal | Rust gateway admission | [Gateway](../product/docs/GATEWAY_IMPLEMENTATION.md) | Blueprint |
| Catalog/capability/model resolution | PostgreSQL model/release authority; Redis immutable projection | Node ModelOps + Rust resolver | [Gateway](../product/docs/GATEWAY_IMPLEMENTATION.md) | Blueprint |
| Direct provider dispatch | exact provider/model endpoint qualification | Rust provider adapter | [Gateway](../product/docs/GATEWAY_IMPLEMENTATION.md) | Blueprint; model/date-specific live gate |
| Owned Grad dispatch | exact route release and authenticated in-memory ready-cell registry | gateway -> inference router -> cell | [Owned inference](../product/docs/OWNED_INFERENCE_IMPLEMENTATION.md) | Blueprint; latency/capacity gate |
| Streaming/cancel/retry/usage | request attempt state in gateway; terminal event in Redis | Rust request coordinator | [Gateway](../product/docs/GATEWAY_IMPLEMENTATION.md) | Blueprint |
| Failed-request credit | immutable usage plus compensating PostgreSQL entry | financial worker | [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md) | Blueprint |
| Product Intelligence capture | gateway policy + encrypted envelope; S3 payload/PostgreSQL registry | Rust capture + trace worker | [Gateway](../product/docs/GATEWAY_IMPLEMENTATION.md), [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md) | Blueprint |
| Trace list/charts/detail/delete/export | PostgreSQL usage/trace metadata; S3 encrypted object | Hono + trace-access role | [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md) | Blueprint |
| Workload summary/recommendation/evaluation | PostgreSQL usage/recommendation state; S3 detail by grant | control intelligence role + Hono | [Control plane](../product/docs/CONTROL_PLANE_IMPLEMENTATION.md) | Blueprint; recommendation-value gate |
| Route release/alias/canary/rollback | PostgreSQL release authority; Redis projection | Node release authority + Rust gateway | [Owned inference](../product/docs/OWNED_INFERENCE_IMPLEMENTATION.md) | Blueprint |
| Inference router transport | mTLS exact-release cell attestation + ephemeral connection registry | Rust inference router | [Owned inference](../product/docs/OWNED_INFERENCE_IMPLEMENTATION.md) | Blueprint; direct/tunnel transport spike |
| Cell lifecycle/runtime/cache | signed bundle and observed placement | Rust cell agent supervising runtime child | [Owned inference](../product/docs/OWNED_INFERENCE_IMPLEMENTATION.md) | Blueprint; runtime-mode/cache gates |
| Capacity target/provider allocation | PostgreSQL target/allocation/cell state | fleet planner + provider-scoped drivers | [Owned inference](../product/docs/OWNED_INFERENCE_IMPLEMENTATION.md) | Blueprint; provider-specific gates |
| Multi-node topology/members | signed runtime topology plus PostgreSQL allocation members | provider driver + coordinator/worker cell agent | [Multi-node inference](../product/docs/MULTI_NODE_INFERENCE.md) | Blueprint; exact two-node GPU measured gate |
| Model program/hypothesis portfolio | PostgreSQL research domain | private Python research control | [Research factory](../product/docs/RESEARCH_FACTORY_IMPLEMENTATION.md) | Blueprint |
| Experiment execution/evidence | immutable experiment specifications/runs plus sealed evidence | Python API/workers, PostgreSQL domain state, Temporal execution | [Research factory](../product/docs/RESEARCH_FACTORY_IMPLEMENTATION.md) | Blueprint |
| Bundle build/qualification | canonical JSON manifests/S3 CAS/ECR/signatures; PostgreSQL decisions | Python artifact/eval + Rust inspector/launcher | [Research factory](../product/docs/RESEARCH_FACTORY_IMPLEMENTATION.md) | Blueprint; portability/operator gates |
| Promotion from research | signed proposal and independent approval | Python qualification -> Node release authority | [Research factory](../product/docs/RESEARCH_FACTORY_IMPLEMENTATION.md) | Blueprint; public promotion remains human |
| Customer-configured gateways | workspace principal and ordinary prepaid path | recipes + shared black-box harness | [Distribution](../product/docs/DISTRIBUTION_IMPLEMENTATION.md) | Blueprint |
| Native OpenRouter traffic | channel principal, catalog, exposure and receivable ledger | Rust gateway + channel worker | [Distribution](../product/docs/DISTRIBUTION_IMPLEMENTATION.md) | Blueprint; external acceptance/legal gate. Hugging Face remains a later decision record. |
| Terraform/accounts/network/data | Terraform state per unit | platform modules/live units | [Platform](../infra/docs/PLATFORM_IMPLEMENTATION.md) | Blueprint; account/region approval gate |
| EKS/Helm/GitOps/autoscaling | Git/Argo static desired state; EKS Auto Mode or managed groups | charts/gitops/HPA | [Platform](../infra/docs/PLATFORM_IMPLEMENTATION.md) | Blueprint; Auto Mode measured gate |
| Secrets/identity/supply chain | AWS IAM/Pod Identity/Secrets Manager; signed digests | Terraform/Helm/CI | [Platform](../infra/docs/PLATFORM_IMPLEMENTATION.md) | Blueprint |
| Local development/agent UX | repository fixtures and `grad` CLI | Compose/mprocs/Kind | [Platform](../infra/docs/PLATFORM_IMPLEMENTATION.md) | Blueprint |
| CI/CD/migrations/rollback | Git and immutable artifacts; protected deploy environments | GitHub Actions + Argo CD + migration jobs | [Platform](../infra/docs/PLATFORM_IMPLEMENTATION.md) | Blueprint |
| Monitoring/incidents/DR/cost | metrics/logs plus PostgreSQL/infra authorities | platform and operator runbooks | [Platform](../infra/docs/PLATFORM_IMPLEMENTATION.md) | Blueprint; launch drills required |

## Contradictions and resolutions

| Inconsistency found | Resolution frozen here |
| --- | --- |
| Internal Protobuf namespace appeared as both `grad/...` and `gradiated/...`. | Canonical package/root is `gradiated`; repository path is `product/proto/gradiated/...`. `grad` remains the product/CLI/model prefix only. |
| A universal event principal tried to cover tenant, channel and research events. | Remove `PrincipalRef`. Each small typed event carries only the IDs required by its domain; research uses PostgreSQL state rather than a general event bus. |
| Full bundle manifests were described as both Protobuf and canonical JSON authority. | Canonical JSON Schema plus RFC 8785 bytes own content identity. Protobuf carries `ArtifactRef`, `BundleRef`, commands and events; it does not define a second independently evolving full manifest. |
| The cell request carried an `opaque_billing_principal`, despite cells having no billing authority. | Remove it. `cache_scope` is the sole opaque isolation input; reservation and sell/buy accounting never leave the gateway. |
| Research qualification and Node ModelOps both appeared to own qualification/release transitions. | Python research control owns experiments, evidence, candidates and bundle qualification. Node release authority owns public product envelopes, approval, alias/canary/rollback and Redis release projection. The handoff is a signed `QualifiedBundleRef`. |
| Provider drivers, cells and release authority all appeared able to publish routes. | Release authority publishes the owned release; drivers reconcile capacity; cells attest and connect; the inference router alone uses ephemeral authenticated live-cell health. There is no durable target publisher/document. |
| Many logical workers looked like separate codebases/services. | Use a small number of images with role entrypoints. Scale/security can create separate Deployments without duplicating domain code. See process topology below. |
| A 4×4 effort/speed grammar implied sixteen launch fleets. | The grammar remains stable, but catalog entries are sparse. Launch only measured products—initially `grad/medium/standard` and at most one measured adjacent speed—then add cells independently. |
| Six AWS accounts looked mandatory before seed work could start. | Keep four: management, security/log, non-production and production. Split staging/shared-services only when isolation or qualification requires it. |
| ClickHouse looked mandatory for product analytics. | Remove its adapter/projector/schema from seed. PostgreSQL indexed usage views and measured rollups are the product implementation; reconsider only after a failing benchmark. |
| OpenAI, Anthropic, Google and all endpoint families appeared as one first implementation milestone. | Launch only Models, OpenAI Responses Create and Anthropic Messages. Chat, Embeddings, Google and hosted/stateful product APIs are deferred until demand and no protocol is advertised until its fixture/live gate passes. |
| tRPC was first-party-only while agents/external automation needed a structured API. | Remove tRPC. One Hono REST/Zod registry generates OpenAPI 3.1, the Vite client, Scalar/agent docs and an explicitly allowlisted MCP adapter. |
| Organization closure was operator-only despite a customer expectation of self-service deletion. | Add one durable deletion row/workflow: suspend immediately, drain/reconcile/refund, cryptographically purge and retain only pseudonymous statutory financial evidence. |
| Multi-node was deferred even though frontier/open-weight releases may not fit one node. | Make one- and multi-node cells first-class before public owned inference. Preserve one cell/gateway contract and qualify exact topologies; do not force small releases onto multiple nodes. |
| `main` direct pushes seemed to imply automatic production deployment. | Direct push updates source and runs checks/dev plans. Staging/prod infrastructure apply and production release remain protected, reviewed external actions. |

## Seed process topology and simplifications

Logical responsibilities do not automatically become independent microservices. The seed uses these deployable artifacts:

| Artifact/image | Role entrypoints / deployments |
| --- | --- |
| `control` Node image | `api`, `financial`, `intelligence`, `trace-access`, `mcp`; separate deployments only where IAM/scaling differs |
| `gateway` Rust image | public gateway |
| `inference-router` Rust image | private regional cell connection/dispatch boundary |
| `fleet` Rust image | SQL planner plus one provider-driver deployment per provider credential |
| `cell-agent` Rust image | one/multi-node coordinator, cell router, bundle launcher and runtime supervisor; model runtime/workers are children/containers, not public services |
| `research` Python image | private API, Temporal workflow/activity and evaluator role entrypoints; evaluator retains separate credentials |
| `web` static artifact | Vite assets in S3/CloudFront |

This preserves IAM and scaling isolation while avoiding nine unrelated codebases. Split an image only after dependency weight, security review or measured scaling justifies it.

Explicit seed exclusions remain: service mesh, Kafka, Argo Workflows, active/active money, customer BYOK, arbitrary provider routing, global customer-content training, remote/cross-cell durable KV cache, elastic multi-node rank repair, LoRA multiplexing, automatic public model promotion and unbounded always-running paid GPUs. The research control loop remains always on but every compute activity is budgeted.

## Unresolved measured and human gates

These are not junior-engineer design gaps. Each has an owner, decision evidence and safe fallback.

| Gate | Owner/evidence | Pass condition | Fallback |
| --- | --- | --- | --- |
| Primary region/customer residency | founder/platform; latency and legal requirements | selected region supports services/providers and target customers | keep modules parameterized; no production mutation |
| Managed Valkey durability/latency | INFRA-02/LAUNCH-01 experiment | synchronous acknowledged reserve+event survives failover inside latency budget | qualify MemoryDB or close admission; never weaken reserve |
| First owned model and public SKUs | research/release owner | exact bundle quality/capability/cost and sparse effort/speed gates | sell curated direct providers only |
| GPU providers/regions | fleet owner | security, availability, interruption and successful-token margin evidence | disable provider/cell; do not alter release |
| OpenRouter onboarding | founder/legal/distribution | terms, privacy, payout/tax, protocol, reliability and margin pass | customer-configured gateways/direct endpoint |
| Retention/terms/subprocessors/tax | founder with legal/accounting | reviewed customer terms, privacy disclosure, retention and payout/tax process | limited design partners; disable affected feature/channel |
| Fully autonomous promotion | later ADR | measured false-positive, rollback and evaluator-governance history | human release approval |

## Source record

Repository documents and ADR-0001 through ADR-0009 are the primary architecture inputs. External capabilities are revalidated at implementation time. Current source checks retrieved 2026-07-14 include:

- AWS documents Valkey 9 node-based durability with synchronous writes persisted to a Multi-AZ transactional log before acknowledgement, plus explicit unsupported configurations: [ElastiCache durability options](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Durability.Options.html), [limitations](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Durability.Limitations.html). Vendor-reported; the exact command/latency behavior remains a Grad measurement.
- OpenRouter's provider contract currently requires a model-list feed, automatic payment/invoicing, OpenAI-compatible streaming/usage, capacity/reliability behavior and monitored performance: [provider integration](https://openrouter.ai/docs/guides/community/for-providers). Vendor-reported and volatile.
- Other external source records remain next to their decisions in `product/docs/*EVIDENCE*`, `infra/evidence/` and ADRs. No cloud account, provider endpoint or paid model was exercised by this documentation audit.

## How junior agents use this ledger

1. Start from [the system manual](SYSTEM_MANUAL.md) and the relevant [Mermaid view](SYSTEM_DIAGRAMS.md).
2. Select one unblocked packet from [the work package catalog](implementation/WORK_PACKAGES.md).
3. Read its cross-service inputs in [the contract catalog](implementation/CONTRACT_CATALOG.md) and exactly one bounded-context blueprint.
4. Claim the packet paths; implement its first failing example/property; do not broaden an authority or dependency.
5. Run the packet checks plus the matching [verification-matrix](implementation/VERIFICATION_MATRIX.md) scenarios and update its [operations](implementation/OPERATIONS_MANUAL.md) handoff.
6. If any required input, failure behavior or acceptance field remains undefined, open an architecture-gap issue rather than inventing policy.
