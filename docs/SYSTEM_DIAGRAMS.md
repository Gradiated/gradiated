# Grad system diagrams

These diagrams are explanatory views of [the canonical system manual](SYSTEM_MANUAL.md). Labels simplify implementation names, but arrows preserve dependency direction and authority. A diagram never overrides a written invariant or contract.

## 1. Product context

```mermaid
flowchart LR
  Developer[Developer or platform team]
  Admin[Organization owner or admin]
  Router[Customer gateway]
  OpenRouter[OpenRouter]
  Providers[Curated model providers]
  Capacity[Curated GPU capacity providers]
  Stripe[Stripe]
  Grad[Grad platform]

  Admin -->|fund, configure, inspect| Grad
  Developer -->|Responses or Messages| Grad
  Router -->|workspace key| Grad
  OpenRouter -->|channel credential| Grad
  Grad -->|exact direct model request| Providers
  Grad -->|owned model serving| Capacity
  Grad <-->|checkout and verified webhook| Stripe
```

## 2. Planes and authorities

```mermaid
flowchart TB
  subgraph Experience[Experience plane]
    Web[Vite React console]
    Docs[OpenAPI Scalar agent docs]
    MCP[MCP REST adapter]
  end

  subgraph Control[Control and data plane on AWS]
    API[Hono control API]
    Financial[Financial worker]
    Intelligence[Intelligence worker]
    TraceAccess[Trace access]
    PG[(Aurora PostgreSQL)]
    Valkey[(Durable Valkey)]
    TraceS3[(Encrypted trace S3)]
  end

  subgraph Serving[Serving plane]
    Gateway[Rust public gateway]
    Router[Rust inference router]
    Direct[Curated model providers]
  end

  subgraph Owned[External owned-inference cells]
    CellA[Single-node cell]
    CellB[Multi-node cell]
  end

  subgraph Research[Research and release plane]
    ResearchAPI[Python research API]
    Temporal[Temporal workflows]
    Jobs[Research jobs and agents]
    Artifacts[(Artifact S3 and ECR)]
  end

  Web --> API
  Docs --> API
  MCP --> API
  API --> PG
  API --> Valkey
  Financial <--> PG
  Financial <--> Valkey
  Intelligence --> PG
  Intelligence --> Valkey
  Intelligence --> TraceS3
  TraceAccess --> PG
  TraceAccess --> Valkey
  TraceAccess --> TraceS3
  Gateway --> Valkey
  Gateway --> Direct
  Gateway --> Router
  Router <--> CellA
  Router <--> CellB
  API --> ResearchAPI
  ResearchAPI --> PG
  ResearchAPI --> Temporal
  Temporal --> Jobs
  Jobs --> Artifacts
  Artifacts --> CellA
  Artifacts --> CellB
```

## 3. Public API generation

```mermaid
flowchart LR
  Zod[Described Zod schemas]
  Manifest[Hono route manifest]
  Registry[OpenAPI route registry]
  Runtime[Runtime validation]
  OpenAPI[OpenAPI 3.1]
  Scalar[Scalar reference]
  AgentDocs[Agent Markdown and llms.txt]
  Client[Generated TypeScript client]
  Allowlist[MCP allowlist manifest]
  MCPServer[Stateless MCP server]
  Web[Vite application]

  Zod --> Registry
  Manifest --> Registry
  Registry --> Runtime
  Registry --> OpenAPI
  OpenAPI --> Scalar
  OpenAPI --> AgentDocs
  OpenAPI --> Client
  Manifest --> Allowlist
  OpenAPI --> Allowlist
  Allowlist --> MCPServer
  Client --> Web
  MCPServer -->|calls only REST| Runtime
```

## 4. Organization activation and top-up

```mermaid
sequenceDiagram
  actor Owner
  participant Web
  participant API as Hono API
  participant PG as PostgreSQL
  participant Stripe
  participant Worker as Financial worker
  participant VK as Valkey

  Owner->>Web: Sign in and create organization
  Web->>API: POST /api/v1/organizations
  API->>PG: Transaction: org + owner + Default workspace + audit + outbox
  PG-->>API: Organization created
  API-->>Web: Organization view
  Owner->>Web: Choose top-up amount
  Web->>API: POST billing/topups with idempotency key
  API->>PG: Create topup_intent
  API->>Stripe: Create Checkout session
  Stripe-->>Owner: Hosted checkout
  Stripe->>API: Signed webhook
  API->>PG: Deduplicate event, lock intent, post balanced credit transaction
  API-->>Stripe: 2xx after commit
  PG-->>Worker: Outbox/account projection work
  Worker->>VK: Publish monotonic account snapshot
  VK-->>Worker: Version acknowledged
```

## 5. Direct paid inference request

```mermaid
sequenceDiagram
  actor Client
  participant GW as Rust gateway
  participant VK as Valkey
  participant Provider as Exact model provider
  participant FW as Financial worker
  participant PG as PostgreSQL

  Client->>GW: POST Responses or Messages
  GW->>GW: Bound, parse, canonicalize
  GW->>VK: Resolve key, policy, alias/release
  GW->>GW: Validate capability and compute worst-case sell exposure
  GW->>VK: Atomic reserve + concurrency + lease + ReservationCreated
  alt reserve rejected
    VK-->>GW: Stable admission error
    GW-->>Client: Protocol-native error
  else reserve accepted
    VK-->>GW: Reservation token and exact release
    GW->>Provider: Exact provider/model request
    Provider-->>GW: Canonicalized stream and usage
    GW-->>Client: Protocol-native stream
    GW->>VK: Atomic settle + release concurrency + UsageSettled
    VK-->>FW: At-least-once billing event
    FW->>PG: Idempotent usage row + balanced ledger transaction
    PG-->>FW: Commit
    FW->>VK: Acknowledge event and publish newer projection
  end
```

## 6. Owned Grad request

```mermaid
sequenceDiagram
  actor Client
  participant GW as Public gateway
  participant VK as Valkey
  participant IR as Inference router
  participant Cell as Exact-release cell

  Client->>GW: model=grad/medium/standard
  GW->>VK: Resolve alias generation and immutable digest
  GW->>VK: Reserve against selected digest and sell price
  VK-->>GW: Reservation accepted
  GW->>IR: Serve exact release digest
  IR->>IR: Filter authenticated ready registry
  alt no exact cell
    IR-->>GW: release_unavailable before output
  else exact cell available
    IR->>Cell: mTLS ServeRequest with exact digest
    Cell->>Cell: Select local replica and cache trust domain
    Cell-->>IR: Typed event stream and metering
    IR-->>GW: Relay stream
    GW-->>Client: Protocol-native stream
  end
  GW->>VK: Settle once or leave lease for terminal sweep
```

## 7. Reservation state and reconciliation

```mermaid
stateDiagram-v2
  [*] --> Reserved: atomic reserve
  Reserved --> Settled: terminal metering
  Reserved --> Abandoned: lease expiry or proven no invocation
  Settled --> [*]
  Abandoned --> [*]

  note right of Reserved
    Holds credit or channel exposure,
    concurrency and immutable release identity.
  end note
```

```mermaid
flowchart LR
  Ledger[(PostgreSQL ledger)]
  Balance[(Balance projection)]
  Usage[(Usage records)]
  Stream[Valkey billing stream]
  Reservations[Valkey reservations and holds]
  Reconciler[Reconciler]
  Gate[Admission status]

  Ledger --> Reconciler
  Balance --> Reconciler
  Usage --> Reconciler
  Stream --> Reconciler
  Reservations --> Reconciler
  Reconciler -->|match| Gate
  Reconciler -->|unexplained delta: suspend| Gate
```

## 8. Trace retention and access

```mermaid
sequenceDiagram
  participant GW as Gateway
  participant VK as Valkey trace stream
  participant IW as Intelligence worker
  participant S3 as Trace S3
  participant PG as PostgreSQL
  actor User
  participant API as Control API
  participant TA as Trace access

  alt Product Intelligence
    GW->>GW: Strip secrets, bound and envelope-encrypt
    GW->>VK: Append ciphertext envelope if trace budget permits
    VK-->>IW: At-least-once envelope
    IW->>S3: Put opaque ciphertext object
    IW->>PG: Upsert trace metadata and wrapped key
    IW->>VK: Acknowledge after both durable
    User->>API: Request trace detail
    API->>PG: Authorize current workspace membership and trace state
    API-->>User: Short-lived single-use grant
    User->>TA: Grant
    TA->>VK: Consume nonce once
    TA->>PG: Recheck authorization and tombstone
    TA->>S3: Read exactly one object
    TA-->>User: Decrypted no-store stream
  else Private or No Retention
    GW->>GW: Emit no payload envelope
    Note over GW: Ephemeral tenant/release/retention-salted KV cache remains enabled
  end
```

## 9. Organization deletion

```mermaid
stateDiagram-v2
  [*] --> Active
  Active --> DeletionPending: owner request + recent reauth
  DeletionPending --> Active: cancel before execute_after
  DeletionPending --> Running: fixed window expires
  Running --> Blocked: unreconciled financial or external condition
  Blocked --> Running: condition repaired and retry
  Running --> Deleted: refund, purge, revoke, pseudonymize complete
  Deleted --> [*]
```

```mermaid
flowchart TD
  Request[Owner deletion request]
  Suspend[Suspend admission and management mutation]
  Window[Seven-day cancellation window]
  Drain[Drain or expire reservations]
  Reconcile[Reconcile ledger, usage and provider exposure]
  Refund[Refund eligible unused credit]
  Purge[Destroy trace keys and objects]
  Revoke[Revoke keys, sessions, OAuth and membership]
  Retain[Pseudonymize required financial evidence]
  Complete[Mark deleted]

  Request --> Suspend --> Window --> Drain --> Reconcile
  Reconcile -->|clean| Refund --> Purge --> Revoke --> Retain --> Complete
  Reconcile -->|uncertain| Blocked[Blocked and alerted]
  Blocked --> Reconcile
```

## 10. External GPU fleet and cell lifecycle

```mermaid
flowchart LR
  Target[(capacity_targets)]
  Planner[Fleet planner]
  Allocation[(allocations and members)]
  Native[Native provider driver]
  ManagedK8s[Managed Kubernetes driver]
  Provider[Provider resources]
  Enroll[Cell enrollment and Private CA]
  Cell[Authenticated cell]
  Registry[Router in-memory registry]
  Sweeper[Independent orphan sweeper]

  Target --> Planner
  Planner --> Allocation
  Allocation --> Native
  Allocation --> ManagedK8s
  Native --> Provider
  ManagedK8s --> Provider
  Provider --> Enroll
  Enroll --> Cell
  Cell --> Registry
  Provider --> Sweeper
  Allocation --> Sweeper
  Sweeper --> Allocation
```

```mermaid
stateDiagram-v2
  [*] --> Requested
  Requested --> Provisioning
  Provisioning --> Ready: all members joined, attested and healthy
  Provisioning --> Failed: timeout or partial acquisition rollback
  Ready --> Draining: scale-down, interruption, release or member loss
  Draining --> Released: every resource cleanup confirmed
  Draining --> Failed: cleanup uncertain
  Failed --> Released: independent sweep proves cleanup
  Released --> [*]
```

## 11. Single-node and multi-node cell

```mermaid
flowchart TB
  IR[Inference router]

  subgraph Single[Single-node cell]
    SCoord[Coordinator and runtime]
    SCache[Ephemeral KV and prefix cache]
    SCoord --- SCache
  end

  subgraph Multi[Multi-node cell]
    MCoord[Coordinator rank]
    W1[Worker rank 1]
    W2[Worker rank 2]
    Fabric[Qualified collective fabric]
    MCache[Cell-scoped KV and prefix cache]
    MCoord --- Fabric
    W1 --- Fabric
    W2 --- Fabric
    MCoord --- MCache
  end

  IR <--> SCoord
  IR <--> MCoord
```

The router sees one cell identity in both cases. It never sees provider resource IDs, ranks or collective topology.

## 12. Always-on research and promotion

```mermaid
flowchart LR
  Observe[Measured observation]
  Hypothesis[Scoped falsifiable hypothesis]
  Spec[Immutable experiment spec and budget]
  Fidelity[Cheapest adequate fidelity]
  Run[Reproducible run]
  Evidence[Evidence report including negative result]
  Bundle[Content-addressed ModelStackBundle]
  Qualify[Independent qualification]
  Proposal[Signed release proposal]
  Human{Release owner approves?}
  Release[Immutable model release]
  Canary[Bounded canary]
  Alias[Public alias]

  Observe --> Hypothesis --> Spec --> Fidelity --> Run --> Evidence
  Evidence -->|promising| Bundle --> Qualify --> Proposal --> Human
  Evidence -->|falsified| Observe
  Human -->|no| Observe
  Human -->|yes| Release --> Canary --> Alias
  Canary -->|hard gate fails| Rollback[Prior release pointer]
```

## 13. AWS deployment

```mermaid
flowchart TB
  Internet[Internet]
  DNS[Route 53 and ACM]
  CF[CloudFront and WAF]
  WebS3[(Private web S3)]
  ControlALB[Control ALB and WAF]
  GatewayALB[Gateway ALB and WAF]
  CellNLB[Cell-connect NLB mTLS only]

  subgraph VPC[Three-AZ workload VPC]
    subgraph EKS[Private EKS]
      ControlPods[Control roles]
      GatewayPods[Gateway]
      RouterPods[Inference router]
      FleetPods[Fleet roles]
      ResearchPods[Research and Temporal]
      Argo[Argo, KEDA and policy controllers]
    end
    Aurora[(Aurora PostgreSQL)]
    Valkey[(Durable Valkey)]
    DataS3[(Trace and artifact S3)]
    ECR[(ECR)]
    PCA[AWS Private CA]
    Secrets[Secrets Manager and KMS]
  end

  ExternalCells[External provider cells]
  Stripe[Stripe]
  ModelProviders[Model providers]

  Internet --> DNS
  DNS --> CF
  CF --> WebS3
  Internet --> ControlALB --> ControlPods
  Internet --> GatewayALB --> GatewayPods
  ControlPods --> Aurora
  ControlPods --> Valkey
  ControlPods --> Stripe
  GatewayPods --> Valkey
  GatewayPods --> ModelProviders
  GatewayPods --> RouterPods
  RouterPods <--> CellNLB
  ExternalCells -->|outbound HTTP/2 mTLS| CellNLB
  FleetPods --> Aurora
  FleetPods --> PCA
  ResearchPods --> Aurora
  ResearchPods --> DataS3
  ResearchPods --> ECR
  ControlPods --> DataS3
  EKS --> Secrets
```

## 14. Infrastructure ownership

```mermaid
flowchart LR
  Git[Git desired state]
  Terraform[Terraform modules]
  Terragrunt[Terragrunt live units]
  AWS[AWS resources and IAM]
  Bootstrap[Minimal EKS Argo bootstrap]
  Argo[Argo CD]
  K8s[Kubernetes static resources]
  SQL[PostgreSQL runtime intent]
  Drivers[Rust reconcilers]
  External[External capacity resources]

  Git --> Terraform --> Terragrunt --> AWS
  AWS --> Bootstrap --> Argo
  Git --> Argo --> K8s
  SQL --> Drivers --> External

  note1[Terraform does not own application rollout or ephemeral GPU allocations]
  note2[Argo does not own business state]
  note3[Drivers do not own customer request routing]
```

## 15. Build, promotion and rollback

```mermaid
flowchart LR
  Change[Scoped change]
  Verify[Language, PBT, contract and infra checks]
  Main[Direct push to main]
  Build[Build once]
  Supply[SBOM, provenance and signature]
  Registry[Immutable image and chart digests]
  Nonprod[Non-production GitOps]
  Smoke[Fake and protected smoke]
  Approval{Production approval}
  Production[Production digest promotion]
  Observe[Canary and SLO observation]
  Rollback[Prior application or alias digest]

  Change --> Verify --> Main --> Build --> Supply --> Registry --> Nonprod --> Smoke --> Approval
  Approval -->|approved| Production --> Observe
  Approval -->|rejected| Change
  Observe -->|hard gate fails| Rollback
```

Database and Terraform state are forward-fixed; `Rollback` means an application/chart/release pointer, never database history or Terraform state rewind.

## 16. Implementation dependency graph

```mermaid
flowchart LR
  FND[Foundation and contracts]
  DATA[PostgreSQL schema and domain core]
  API[REST, auth and UI shell]
  MONEY[Ledger, Stripe and Valkey projection]
  GW[Gateway admission and protocols]
  DIRECT[Direct provider paid slice]
  TRACE[Trace and customer intelligence]
  INF[Owned inference and fleet]
  RF[Research factory and qualification]
  DIST[OpenRouter distribution]
  CLOUD[AWS, EKS and GitOps]
  HARDEN[Fault, recovery and launch gates]

  FND --> DATA
  FND --> CLOUD
  DATA --> API
  DATA --> MONEY
  MONEY --> GW
  API --> GW
  GW --> DIRECT
  GW --> TRACE
  GW --> INF
  DATA --> INF
  FND --> RF
  DATA --> RF
  RF --> INF
  INF --> DIST
  MONEY --> DIST
  CLOUD --> HARDEN
  DIRECT --> HARDEN
  TRACE --> HARDEN
  INF --> HARDEN
  RF --> HARDEN
  DIST --> HARDEN
```
