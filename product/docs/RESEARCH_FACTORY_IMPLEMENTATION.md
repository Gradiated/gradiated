# Simplified always-on research factory blueprint

## Purpose and boundary

The factory continuously improves the complete inference stack for selected models: weights/architecture, operators/kernels, runtime, scheduler/cache, topology and hardware mapping. It preserves negative results, builds exact bundles and independently qualifies them. It never handles live customer admission or moves a public alias.

Python owns research state transitions, model-facing work and bundle construction. Temporal owns resumable workflow execution. Rust owns production cell/runtime supervision and serving. TypeScript is the authenticated operator BFF. Fable/Sol are evidence to port with provenance, not dependencies.

## Dependencies and processes

Use Python 3.12, uv, PostgreSQL, Temporal, S3/ECR, PyTorch, Transformers/safetensors, Triton where justified, pytest/Hypothesis and curated compute adapters. Temporal removes the need to build a custom durable scheduler, timer, retry, cancellation and recovery engine. Its history is execution state, not scientific evidence or release authority.

```text
research/factory/src/grad_research/
  api/                    private generated Protobuf service
  domain/                 programs, hypotheses, campaigns, specs/runs, evidence, bundles
  workflows/              deterministic Temporal workflows
  activities/             DB, artifact, provider, Git, agent and evaluator operations
  experiments/            baselines, interventions and evaluation
  operators/              PyTorch oracle/differential/Triton/native candidates
  artifacts/              S3 CAS, manifests, ECR image refs/signing
  providers/              bounded research-compute adapters
  qualification/          independent exact-bundle suite
  agents/                 scoped work leases/tool policy
  testkit/                Hypothesis models/fakes/Temporal replay
```

One image exposes `api`, `workflow-worker`, `activity-worker`, and `evaluator` roles. Evaluator credentials/data remain separate even when the image is shared.

## Minimal scientific model

Required fields are in [the research model](../../docs/SIMPLICITY_REVIEW.md#research). Retained primary entities have different authority:

- `research_programs`: long-lived model/scope, baseline, champion and budget;
- `research_hypotheses`: falsifiable scientific intent and intervention;
- `research_campaigns`: real budget/deadline/scope authority envelope;
- `experiment_specs`: immutable execution intent;
- `experiment_runs`: one environment-bound observation and Temporal workflow ID;
- `evidence_reports`: reviewed scope-bound synthesis, including negative results;
- `bundles` and `bundle_qualifications`: deployable output and independent decision.

Remove only derived/duplicative entities:

| Removed concept | Derivation |
| --- | --- |
| queue entry | eligible hypotheses/specs ordered by priority and age |
| stored expected-information score | recompute from current cost/evidence inputs |
| persisted Pareto frontier | query sealed evidence reports/runs |
| open-questions/negative-findings arrays | hypothesis/evidence status queries |
| candidate aggregate | a built bundle is the deployable challenger |
| relational workflow step/job rows | Temporal history/activity heartbeats own execution detail |
| per-gate qualification rows | immutable qualification report artifact |

This keeps scientific intent/evidence while deleting views and execution mirrors that can drift.

## State and private API

Program is `active|paused|stopped`. Hypothesis is `proposed|approved|rejected|exhausted`. Campaign is `draft|approved|running|stopped|completed`. Run is `queued|running|succeeded|falsified|failed|cancelled`. Bundle is `built|qualification_pending|qualified|rejected`.

Do not add a state unless it changes an allowed command, resource action, evidence meaning or operator display.

Private service package is `gradiated.research.v1`. Calls require mTLS/service identity and operator context from Hono. Commands are `create/update program`, `propose/approve hypothesis`, `create/approve/stop campaign`, `start/cancel experiment`, `record reviewed evidence`, `build bundle`, and `request qualification`.

Each command opens one PostgreSQL transaction, locks/checks expected version, validates authority/state, writes domain state/audit/outbox and commits. Python is the sole normal writer. Hono has no research mutation repository. Temporal activities call the same application ports, not ad hoc SQL.

## Temporal workflows

```text
PortfolioWorkflow(program)
  -> BaselineRefreshWorkflow when stale
  -> CampaignWorkflow for approved campaigns
       -> ExperimentWorkflow per admitted immutable spec
            validate -> cheap correctness/profile
            -> acquire compute -> execute -> collect artifacts
            -> release/cleanup -> seal run/evidence
            -> optionally build bundle/request qualification
```

Workflow code uses deterministic time/random/versioning only. All network, database, provider, filesystem, Git, S3/ECR, model and agent actions are activities with small refs. Large outputs/logs go to S3.

Activities are idempotent by domain ID, step and input digest. Provider acquisition records provider allocation identity before success. Cleanup runs in a non-cancellable bounded branch and by an independent sweeper. Uncertain cleanup freezes new acquisitions for that provider and is durable evidence; it is not silently converted to success.

Temporal workflow ID/run ID is stored on `experiment_runs`. PostgreSQL stores domain milestones and artifact refs, not copied activity history. On disagreement, reconciliation can terminate workflow execution, but workflow history cannot approve evidence or alter release state.

## Always-on portfolio loop

Within fixed cheap/paid quotas:

1. refresh reproducible baseline when source/software/hardware changes;
2. scan profiles/regressions/prior evidence for opportunities;
3. deduplicate hypotheses by scope/intervention digest;
4. rank admissible work by expected information per bounded cost;
5. admit only inside program/campaign/provider/global budgets;
6. stop a lineage on falsification/stop rule and continue with the next admissible lineage;
7. recompute frontier/open questions from primary evidence and propose bundle-worthy challengers.

Paid GPU work always has immutable scope, budget, timeout, stop rule and cleanup contract. Expected-information score and queue order are derived and may change without mutating evidence.

## Research SDK

Start every intervention with an eager PyTorch oracle, tiny deterministic inputs and matched control.

```python
class Intervention(Protocol):
    def applicable(self, baseline: Baseline) -> Applicability: ...
    def apply(self, baseline: Baseline, spec: FrozenSpec) -> InterventionOutput: ...
    def checks(self, output: InterventionOutput) -> VerificationPlan: ...

class OperatorCandidate(Protocol):
    reference: Callable
    implementation: Callable
    tolerances: TolerancePolicy
    supported_shapes: ShapePolicy
```

Only profile-proven bottlenecks proceed to Triton/native/Rust work. Operators declare schema, mutation/alias behavior, FakeTensor/meta behavior and autograd promise. Use `torch.library.opcheck`, generated differential cases and `gradcheck` where gradients are promised. Benchmark the declared workload distribution, not one favorable shape.

Runtime packaging produces one OCI image implementing the local serving Protobuf. There is no `python_plugin|native_library|rust_engine` product enum: language is an image implementation detail behind one runtime protocol.

## Artifacts and bundles

S3 CAS keys derive from digest; ECR stores runtime images by digest. Keep a small compositional schema set:

- `ArtifactDescriptor`: digest, size, media type, role/object ref;
- `CheckpointManifest`: source/revision, shard/tokenizer/config refs and transformation lineage;
- `RuntimeManifest`: image digest, protocol/command, software/driver bounds and cache layout;
- `BundleManifest`: checkpoint/runtime digests, additional artifacts, compatibility/capabilities and known limitations;
- `QualificationReport`: policy, exact scope, gates/results/uncertainty and evaluator attestations.

Do not create separate architecture/operator manifests when their content is already a referenced artifact or runtime field. Creation time, experiment/campaign IDs, prices, rollout and qualification are not bundle identity. Canonical RFC 8785 bytes determine manifest digests. Sign bundle and image provenance; component digests provide transitive integrity.

The Rust cell independently verifies canonical bundle/runtime/image identity before launch.

## Qualification and promotion

Evaluator policy/image/hidden datasets have separate repository/IAM ownership. Candidate agents cannot modify or inspect them beyond allowed aggregate feedback. Qualification tests the exact bundle through source/legal, model quality/correctness, operator/runtime, public protocol/metering, measured performance/economics, distributed-cell only when required, security/privacy, interruption and soak gates.

One immutable S3 qualification report records gate detail; PostgreSQL stores bundle, policy version, status, report key and expiry. Node release authority verifies it, chooses public model/alias/prices/SLO/canary and requires human approval. It cannot edit qualification; research cannot move an alias.

## Research compute and security

Native provider work remains native. For honest Kubernetes execution, Kueue owns quota/admission and JobSet owns actual distributed/gang jobs; neither becomes research evidence or provider abstraction. Do not create Kubernetes Jobs for native VM/container providers merely for uniformity.

Agents receive program/hypothesis/campaign/spec/run IDs, base commit, writable paths, readable evidence class, tool/network allowlist, CPU/GPU/spend/time/output limits, expected artifacts and verification command. Candidate agents cannot mutate qualification. Research roles have no production Valkey, customer keys, trace decrypt or release-alias rights. Customer-trace evaluation requires explicit workspace consent and separate scoped identity; retention is not global training consent.

## Verification and ordered packages

Use pytest/Hypothesis domain models, Temporal replay/crash tests, fake S3/ECR/provider/evaluator services, tiny PyTorch/operator fixtures and cross-language manifest/serving goldens. Protected GPU runs require budget and cleanup packets.

1. `RF-00`: minimal schemas/domain/Hypothesis strategies and generated private API.
2. `RF-01`: program/hypothesis/campaign/spec/run/evidence authority and API.
3. `RF-02`: Temporal workflows/activities, idempotency, cancellation, replay and cleanup.
4. `RF-03`: S3 CAS plus artifact/checkpoint/runtime/bundle manifests and Rust inspection.
5. `RF-04`: PyTorch intervention/operator testkit and profile-gated Triton path.
6. `RF-05`: OCI runtime packaging and cell-local conformance.
7. `RF-06`: independent qualification report and Node release handoff.
8. `RF-07`: operator program/evidence/bundle UI through generated client.
9. `RF-08`: one continuous program producing a durable falsified result and one qualified dry-run challenger without moving a public alias.

Temporal, Kueue and JobSet remain because they replace difficult execution machinery. Derived frontier/queue/state mirrors and speculative runtime modes remain removed.
