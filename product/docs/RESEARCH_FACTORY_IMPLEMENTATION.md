# Always-on research factory implementation blueprint

## Purpose and boundary

The factory is a continuously operating inference laboratory, not a training pipeline or model registry wrapper. It performs the work of model, kernel, runtime, serving and systems researchers; learns from negative results; assembles complete challengers; independently qualifies exact bundles; and hands a signed qualified reference to public release authority.

Python owns model-facing research and research state transitions. Rust owns bundle verification/launch, production cell/runtime supervision and serving. TypeScript owns the operator UI/BFF. Fable and Sol are historical evidence only; no new package imports their workspaces or preserves their schemas.

The factory cannot:

- access customer no-retention payloads or treat trace retention as global training consent;
- expand campaign budget/provider/data/hidden-eval authority;
- mutate a sealed experiment or observation;
- let a candidate-writing agent see hidden holdouts or approve its own result;
- publish a `CellTarget`, move a public alias or deploy mutable/unqualified artifacts;
- keep paid GPU work running merely to satisfy “always on.”

## Python package and process layout

```text
research/factory/
  pyproject.toml
  uv.lock
  src/grad_research/
    api/                    # private gRPC/service handlers
    domain/                 # programs, hypotheses, campaigns, evidence, candidates
    repositories/           # PostgreSQL interfaces/implementations
    workflows/              # deterministic Temporal workflows
    activities/             # side effects and job submission
    agents/                 # role-scoped tool runners and prompts
    models/                 # PyTorch reference models/adapters
    interventions/          # surgery, pruning, quantization, distillation
    training/               # healing/fine-tuning/data recipes
    operators/              # torch.library schemas/reference/meta/autograd
    kernels/triton/         # optimized candidates
    runtimes/               # vLLM/SGLang/custom packaging adapters
    evals/                  # visible suites and evaluator protocol
    artifacts/              # CAS, manifests, OCI/signing clients
    providers/              # research allocation adapters
    simulators/             # priors and experiment-tool clients
    contracts/gen/          # generated Protobuf; never edited
    testkit/                 # Hypothesis strategies/fakes/replay
  tests/
  experiments/              # reviewed reusable specs/templates only
```

One `research` image exposes entrypoints:

- `research-api`: private generated API and sole normal research-domain writer;
- `research-workflow-worker`: Temporal workflows only, with deterministic imports;
- `research-activity-worker`: database/provider/artifact/Git/agent orchestration activities;
- `research-gpu-runner`: short-lived image/profile for model/kernel jobs;
- `research-evaluator`: separately built/owned image with hidden-suite authority.

Do not load PyTorch/CUDA/Triton into the lightweight API/workflow environment. Use separate locked CPU, CUDA-target, provider-bootstrap and evaluator environments/images.

## Domain model

### Model program

```python
@dataclass(frozen=True)
class ModelProgram:
    id: ModelProgramId
    model_family: ModelFamilyRef
    objective: ObjectiveEnvelope
    baseline_bundle: BundleRef
    champion_release: RouteReleaseRef | None
    pareto_policy: ParetoPolicy
    budget_policy: ProgramBudgetPolicy
    cadence: ProgramCadence
    lifecycle: Literal["active", "maintenance", "paused", "retired"]
    version: int

class ModelProgramService(Protocol):
    async def create(self, command: CreateModelProgram, actor: ResearchActor) -> ModelProgram: ...
    async def scan(self, command: RecordOpportunityScan, actor: ServiceActor) -> ScanResult: ...
    async def rank_queue(self, program_id: ModelProgramId, reason: RankReason) -> QueueSnapshot: ...
    async def set_baseline(self, command: SetBaseline, actor: ResearchActor) -> ModelProgram: ...
    async def update_frontier(self, command: UpdateFrontier, actor: EvidenceActor) -> FrontierSnapshot: ...
```

The program stores refs/summaries, not mutable run logs. Its baseline is a current tuned control for the exact target scope, not merely an upstream default. Champion points to the active production release when one exists. Pareto dimensions include quality/capability, goodput/SLO, latency, memory/startup, successful-token cost, reliability, portability and maintenance risk.

### Hypothesis and queue

```python
@dataclass(frozen=True)
class ResearchHypothesis:
    claim: str
    falsifier: str
    intervention_family: InterventionFamily
    target_scope: ScopeIdentity
    predicted_effects: tuple[Prediction, ...]
    source_refs: tuple[SourceRef, ...]
    prior: ProbabilityAssessment
    expected_information: InformationValue
    estimated_resources: ResourceEstimate

@dataclass(frozen=True)
class QueueEntry:
    hypothesis_id: HypothesisId
    class_: Literal["exploit", "explore", "replicate", "baseline"]
    priority: Decimal
    dependencies: tuple[EvidenceRef, ...]
    next_fidelity: Fidelity
    admitted_spec: ExperimentSpecRef | None
```

Queue ranking is advisory. Budget/data/provider/hidden-eval policy admission is authoritative. Duplicate detection uses normalized intervention/scope/source identities and evidence graph similarity; it never collapses two scopes merely because titles resemble each other.

### Campaign, experiment and evidence

```python
class CampaignState(Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    ACTIVE = "active"
    STOPPING = "stopping"
    COMPLETE = "complete"
    EXHAUSTED = "exhausted"
    INVALIDATED = "invalidated"

class RunState(Enum):
    ADMITTED = "admitted"
    LEASED = "leased"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    COLLECTING = "collecting"
    SEALED = "sealed"
    FAILED = "failed"
    INVALID_ENVIRONMENT = "invalid_environment"
    CANCELLED = "cancelled"
```

`ResearchCampaign` freezes objective, hypothesis space, target scopes, control requirements, metric/decision policy, total budget, timeout, allowed data/providers, stop/cleanup rules and owner. Approval creates the maximum authority envelope; children may narrow but never broaden it.

`ExperimentSpec` is canonical JSON and content-addressed before admission. It includes hypothesis, exact model/checkpoint/workload/software/hardware/intervention/control identities, predictions, metrics/thresholds/statistical method, repetitions/seeds, fidelity, maximum spend/runtime, artifact contract and cleanup. The first observation permanently seals the spec.

`ExperimentRun` is append-only observed execution. Environment validity is decided separately from model outcome. Failure to acquire capacity is not a negative model result. A sealed run names exact metering and cleanup evidence.

`EvidenceClaim` states one conclusion, exact scope, evidence class, controls, uncertainty/limitations, observation refs, contradictions/replications, expiry and reviewer. Claim composition intersects scope; it cannot widen hardware, workload, model, software or intervention identity.

### Candidate and qualification

```text
candidate: proposed -> implementing -> runnable -> measured -> rejected | bundle_ready
bundle: assembling -> signed -> qualification_pending -> qualified | failed | expired
qualification: planned -> running -> passed | failed | invalid -> expired/revoked
```

A `ResearchCandidate` is an immutable lineage node plus coherent intervention set; implementation commits/artifacts are refs. New bytes/config create a new candidate/bundle. `BundleQualification` belongs to the exact bundle digest and policy/evaluator/environment versions.

## Private research API

Service package is `gradiated.research.v1`. Calls require mTLS/service identity plus a signed `ResearchActorContext` issued by Hono for operator actions. Workflow/service identities use their own principal; research events never fake organization/workspace IDs.

```text
ModelPrograms
  CreateModelProgram, GetModelProgram, ListModelPrograms
  RecordOpportunity, RankExperimentQueue, SetProgramLifecycle

Campaigns
  DraftCampaign, ApproveCampaign, StartCampaign, StopCampaign, GetCampaign

Experiments
  AdmitExperimentSpec, LeaseRun, AppendRunObservation, SealRun, CancelRun

Evidence
  ProposeClaim, ReviewClaim, InvalidateClaim, GetEvidenceGraph

Candidates
  CreateCandidate, RecordImplementation, AssembleBundle, RejectCandidate

Qualification
  RequestQualification, RecordGateResult, FinalizeQualification
  GetQualifiedBundleRef
```

Commands carry expected aggregate version and idempotency key. Responses include new version and event IDs. The API opens one PostgreSQL transaction per command, locks the aggregate or uses optimistic version compare, validates authority/state, writes state/append-only observation, audit and outbox, then commits. Temporal calls these APIs/ports; workflow history is not the domain source of truth.

Hono/tRPC never accesses research tables directly. It maps product operator authorization to signed calls and returns generated views. Python does not own public alias/price/customer routes.

## Always-on Temporal workflows

### Workflow hierarchy

```text
ResearchPortfolioWorkflow
  -> ModelProgramWorkflow(program_id) [long-lived, continue-as-new]
       -> OpportunityScanWorkflow
       -> BaselineRefreshWorkflow
       -> CampaignWorkflow(campaign_id)
            -> ExperimentRunWorkflow(run_id)
       -> ChallengerAssemblyWorkflow
       -> QualificationWorkflow(bundle_ref)
```

`ResearchPortfolioWorkflow` receives global budget/freeze signals and starts one child per funded program. `ModelProgramWorkflow` wakes on schedule/events, reads current queue through activities, starts only admitted work, records summaries and uses continue-as-new before history grows unbounded. Workflow IDs are stable; retrying start returns the same execution.

Temporal workflow code uses deterministic time/random/version gates only. All network, database, filesystem, Git, agent, provider, S3/ECR and model operations are activities. Activity inputs/outputs are small refs; large logs/artifacts go to CAS.

### Experiment workflow

```text
validate admitted immutable spec
 -> acquire research lease and budget hold
 -> quote/acquire compute allocation
 -> stage exact inputs/image
 -> run command with timeout/heartbeat/cancel
 -> collect content-addressed outputs/metering
 -> seal observation and environment validity
 -> release allocation and record cleanup evidence
 -> close budget hold
```

Cleanup runs in a non-cancellable bounded branch after allocation identity exists. If cleanup cannot be proven, the run remains `cleanup_uncertain`, the provider adapter may freeze new acquisition and an orphan sweep is scheduled. Workflow completion never turns missing cleanup into success.

### Signals and controls

- `pause/resume/stop_program` affects new work, not sealed evidence.
- `freeze_global_spend` stops new paid activities and cancels/drains according to spec.
- `approve_campaign` and `approve_release` are different authorities; release approval stays outside Temporal research.
- `provider_unavailable` reranks admissible placements or classifies environment failure; it cannot expand provider/price policy.
- Workflow/activity version changes use Temporal-compatible versioning and replay tests before deployment.

## Agent execution contract

Each agent role receives:

```text
AgentWorkLease
  role, program/campaign/run/candidate IDs
  base commit and clean worktree
  writable path allowlist
  readable evidence/holdout class
  tool and network allowlist
  CPU/GPU/spend/time/output limits
  expected artifacts and verification command
  lease owner epoch / expiry / cancellation
```

Agents operate through a small tool protocol:

- `source.search/read/diff/apply/test` for scoped repository work;
- `artifact.get/put` by digest;
- `experiment.status/append_observation` for owned run only;
- `compute.quote/run/cancel` inside admitted spec;
- `evidence.query` filtered by role and hidden-data class.

Candidate agents cannot call qualification result mutation or hidden dataset endpoints. Evaluators receive bundle refs, not candidate worktree credentials. Prompts and procedures are versioned repository artifacts referenced in the run; chat history is never sufficient provenance.

## Model/operator/runtime research SDK

### Reference first

Every intervention starts with an eager PyTorch oracle, tiny deterministic fixtures and matched control. Compiled/Triton/native/Rust work begins only after the hypothesis survives cheaper correctness/quality tests and profiling identifies that layer as a constraint.

```python
class ModelIntervention(Protocol):
    def applicability(self, model: ModelArchitectureSpec) -> Applicability: ...
    def transform(self, checkpoint: CheckpointRef, config: FrozenConfig) -> TransformResult: ...
    def verification_plan(self) -> VerificationPlan: ...

class OperatorCandidate(Protocol):
    schema: OperatorSchema
    reference: Callable
    fake_or_meta: Callable
    implementations: Mapping[Target, ImplementationRef]
    tolerances: TolerancePolicy
```

Custom operators register an explicit namespaced schema, mutation/alias behavior, FakeTensor/meta implementation and autograd policy. Required tests include `torch.library.opcheck`, generated differential cases and `gradcheck` when gradients are promised. Benchmarks sample the declared shape/dtype/hardware distribution rather than one favorable case.

Runtime packaging adapters implement:

```python
class RuntimePackager(Protocol):
    def supports(self, architecture: ModelArchitectureSpec) -> SupportReport: ...
    def build(self, candidate: CandidateRef, target: RuntimeTarget) -> RuntimeArtifactSet: ...
    def conformance_plan(self, artifacts: RuntimeArtifactSet) -> RuntimeConformancePlan: ...
```

Initial target is an out-of-tree framework plugin (`python_plugin`). `native_library` and `rust_engine` are justified by measured whole-system value, not required graduation stages.

## Artifact and bundle contracts

Canonical manifests are JSON Schema-governed and RFC 8785 canonicalized before SHA-256 identity:

- `ModelArchitectureSpec`
- `CheckpointManifest`
- `OperatorManifest`
- `RuntimeManifest`
- `QualificationManifest`
- `ModelStackBundleManifest`

Protobuf transports `ArtifactRef`, `BundleRef`, commands/events and API messages. It does not duplicate full manifest authority. JSON schema, generated Python/TS/Rust readers and canonical golden bytes are drift-checked together.

CAS object key is derived from algorithm/digest, never mutable name:

```text
s3://<artifact-bucket>/cas/sha256/<first-two>/<digest>
```

Artifact metadata includes size/media type, producer/source commit/workflow, input/command digests, evidence class, license/export/data policy, build environment, SBOM/signature where executable and retention. Model weights use safetensors or another explicitly qualified non-executable format. Runtime images live in ECR by digest. A small OCI artifact may index the canonical bundle and external S3 refs.

Bundle builder refuses mutable tags, missing digests, unsupported executable formats, absent license/data metadata or claims not admitted for the exact scope. Rust `bundle-inspect` independently verifies canonical bytes, references, signatures, SBOM/attestations and placement/runtime mode before launch.

## Independent qualification and promotion

Evaluator policy/image/hidden datasets and thresholds have separate repository/IAM ownership. Candidate agents receive visible suites and may query bounded aggregate hidden results only according to contamination policy. Qualification executes the exact signed bundle through G0–G7 gates in the canonical lifecycle document.

Successful finalization emits:

```text
QualifiedBundleRef
  bundle_digest
  qualification_id / policy_version / expiry
  capability and quality envelope
  runtime modes / placement envelope
  known limitations
  evaluator and attestation refs/signatures
```

Node `ReleaseAuthority` verifies this reference, selects a customer product/family envelope, price/SLO/support/rollout and independent release owner approval. It cannot override qualification. Any changed bundle bytes or expired/invalid qualification require a new reference. Public rollback moves an alias to a prior release; it does not ask research to rebuild.

## Research compute and security

Research allocations reuse provider lifecycle transports but have distinct resource kind, IAM, queues, budgets, networks and registration. They can never publish production readiness. Kubernetes jobs use Kueue/JobSet only where the provider exposes honest Kubernetes compute; native VM/container APIs stay native. Temporal is cross-provider workflow authority. Argo Workflows is not a seed dependency.

Inputs are staged by digest with least-privilege short-lived credentials. Research containers have no production database, Redis route signer, customer API key or trace decryption by default. Customer-specific Product Intelligence evaluation uses a separate consent/scope/job role and never converts retained data into global training authority.

## Portfolio policy and observability

Always-on scanners, static analysis, tiny CPU tests, code generation and synthesis may run continuously within cheap quotas. A paid experiment requires expected information value, immutable spec, program/campaign/global budget, timeout, stop and cleanup.

Metrics:

- queue age by class/fidelity, duplicate hypotheses avoided and baseline freshness;
- admitted/completed/invalid/negative runs, cleanup reliability and provider availability;
- spend/agent time/GPU time per program and accepted learning per dollar;
- evidence expiry/contradiction/replication and challenger funnel;
- quality/goodput/latency/memory/cost Pareto changes against current tuned baseline;
- bundle build/qualification duration/failure reason and false-positive/rollback history.

No metric rewards raw experiment count, GPU utilization or agent activity. High-cardinality run detail remains PostgreSQL/S3, not Prometheus labels.

## Verification and junior-agent packages

Use pytest/Hypothesis for domain/workflow/activity state models, Temporal replay tests, fake provider/CAS/evaluator services and tiny PyTorch/operator fixtures. Cross-language goldens exercise canonical JSON and Protobuf. Protected real-GPU runs require admitted specs and budget/cleanup evidence.

Implement in order:

1. `RF-00`: Python project/tooling, generated contracts, canonical schemas/readers/goldens and fakes.
2. `RF-01`: program/hypothesis/queue/campaign/experiment/evidence PostgreSQL domain and private API.
3. `RF-02`: CAS/manifests/signing plus Rust bundle inspector/launcher.
4. `RF-03`: Temporal portfolio/program/campaign/run workflows with fake/local compute and cleanup PBT.
5. `RF-04`: scoped agent runner/tool protocol and one provider research adapter.
6. `RF-05`: PyTorch intervention/operator SDK and tiny model reference/compiled/Triton path.
7. `RF-06`: framework runtime packaging and cell-local conformance.
8. `RF-07`: independently owned qualification service/harness and signed reference.
9. `RF-08`: Hono BFF/Vite operator program/evidence/bundle/qualification views.
10. `RF-09`: one continuously operated model program with a durable negative result and one dry-run qualified challenger.

RF-09 does not move a public alias. Production recurring GPU autonomy remains disabled until the bounded shadow-lab gate demonstrates learning value, cleanup reliability and budget control.
