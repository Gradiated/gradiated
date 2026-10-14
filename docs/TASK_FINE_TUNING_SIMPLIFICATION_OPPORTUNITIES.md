# Fine-tuning: remaining simplification opportunities

Status: accepted simplifications and remaining proposals. The owning contracts define the current launch architecture. Items marked as proposals are not implementation requirements.

## 1. Host-owned adapter caches — accepted

The gateway sends an authorized request to a compatible base runtime. The host owns coalesced S3 downloads, disk/RAM/GPU caches, active-use protection and bounded cold-load waits. No `adapter-warm` key, worker warm loop, synchronized adapter placement map or mandatory production preload is required. Promotion uses the same host loader for preparation. Validate concurrent loads, cancellation, saturation, restart and exact identity under S3/S4 qualification.

## 2. Independent evaluation — deferred

Evaluation remains part of the training run at launch. Its settings, call history, results and summaries are recorded in `training_run_events`, keyed by run ID. There are no separate PostgreSQL evaluation or evaluation-operation tables. Worker recovery resumes unfinished evaluation from that history. A future independent evaluation feature requires its own scope decision.

## 3. Keep the recipe inside the trainer — accepted

Applied to RUN-01, RUN-03 and RUN-05. The trainer owns recipe steps and checkpoints. ClickHouse owns structured execution history for logs and execution decisions. PostgreSQL keeps run definitions and execution control fields. There is no training-step table or required progress cache. S3 holds checkpoint and output bytes. Reconciliation checks execution history and referenced artifacts. Each run has one execution; host loss fails it.

## 4. Artifact operations — simplified

The generic artifact-operation table is removed. Training-run events and S3 manifests track uploads, validation and publication; model records reference published artifacts. Existing format validation remains in ART-01. Requiring a single trainer output format remains a possible later simplification.

## 5. Store each fact once

**Current design:** a restriction intent overrides a policy boolean that still says enabled. A second transaction changes the boolean after projection. Other candidates for duplicated state include model readiness, copied release fields and independently updated counters.

**Proposal:** commit the authoritative restricted state, revision and projection work once; emit the action audit through the best-effort ClickHouse helper. Track projection completion separately. Control-plane checks see the restriction immediately. Report it as effective at the gateway only after acknowledgement and the cache bound.

Derive model readiness from current runtime observations. Reference an immutable compatibility profile instead of copying its fields into independently mutable model columns. Derive counters from accepted records or rebuildable views. Keep hashes where exact-byte verification requires them.

**Before acceptance:** retain ordered projections, tombstones, bootstrap handling and the acknowledgement barrier. Keep the existing money-projection contract separate. Require a concrete consumer for each additional identity or state field.

Owner: [OPS-01](TASK_FINE_TUNING_OPERATIONS_CONTRACT.md), [SERV-01](TASK_FINE_TUNING_SERVING_CONTRACT.md), and the plan's data catalogue.

## 6. Evaluation-call bookkeeping — superseded

The earlier proposal for PostgreSQL call-operation rows is withdrawn. Evaluation belongs to a training run and uses `training_run_events` for dispatch history, results and recovery. EVAL-03 defines bounded retries and worker takeover. Do not add evaluation-operation tables from an earlier draft.

## 7. Use one Kubernetes scheduler — implemented

Git owns serving runtime pins, replicas and placement. Kubernetes owns workload
placement and lifecycle; Argo Rollouts gates serving updates on SDK qualification.
Temporal creates training Jobs from frozen run configuration. PostgreSQL retains
the model catalog and provider inventory. There is no second scheduler or enabled
serving autoscaler. Future adapter sharding remains a separate design.

## 8. Use operational metrics for availability — accepted

OPS-05 uses Prometheus counters, edge metrics, monitoring-gap alerts and external probes. Generation records support diagnosis. The availability event table, Valkey stream and reconciliation consumer are removed. Missing telemetry is unknown; there is no exact per-request SLA ledger.

## 9. Avoid a second memory scheduler for internal inference

**Current design:** internal admission must preserve customer headroom in resource units that include token memory. This requires request-cost estimates and atomic resource reservation beyond a request-count lease.

**Proposal:** use existing request-capacity leases, a conservative allowance for background concurrency, and runtime overload rejection. Keep declared capacity for training judges that must remain available throughout a run.

**Choice required:** this protects customer capacity conservatively but does not guarantee exactly 20% free KV memory. If that guarantee is required, specify and qualify the token-memory reservation system as a separate feature. Keep bounds on background work in either design.

Owner: [RUN-04](TASK_FINE_TUNING_RUN_CONTRACT.md).

## 10. Remove optional automation from launch prerequisites

These are separate scope choices:

| Feature | Smaller first implementation | Tradeoff or condition |
| --- | --- | --- |
| Adaptive capture sampling | Capture at a fixed rate, initially all eligible traffic, within the existing resource bounds | Measure storage volume first. Preserve the 500-new-session training trigger and honest loss reporting. |
| Five-minute provider-price refresh | A versioned operator-maintained price table | Keep price provenance, verification time and unknown usage categories. Estimates may need manual updates. |
| Cleanup after a year without use | Retain models and record publication and customer-use evidence now | Workspace deletion is outside launch scope. Build inactivity cleanup before it can act; check imported models before deferring it. |

Host failure fails the training run. Launch has no automatic restart or cross-run checkpoint resume.

Owners: [CAP-02](TASK_FINE_TUNING_GATEWAY_CONTRACT.md), [EVAL-03](TASK_FINE_TUNING_EVALUATION_CONTRACT.md), [SERV-04](TASK_FINE_TUNING_SERVING_CONTRACT.md), [RUN-02 and RUN-03](TASK_FINE_TUNING_RUN_CONTRACT.md).

## Document maintenance

Give each rule one owning contract. Keep the overview focused on architecture, dependencies and build order. Treat diagrams as illustrations of the owning rule. Link to field semantics instead of copying them across documents.

For each module, state which dependencies are required for new work, existing serving and telemetry. This makes unnecessary availability dependencies easier to find. Apply accepted proposals to those contracts rather than creating a second implementation specification here.
