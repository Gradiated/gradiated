# Fine-tuning: remaining simplification opportunities

Status: proposals for follow-up review. These proposals do not change the accepted [launch plan](TASK_FINE_TUNING_FROM_TRACES_PLAN.md) or its contracts. Update the owning contract when a proposal is accepted. The plan remains a design that requires implementation and qualification before customer enablement.

The Nomad revision already moves physical placement and serving recovery into Nomad. It also removes the separate runner/executor workflow and uses the same production adapter set on each replica of a base.

Review items 1 and 2 first. They remove dependencies between services. Items 7 to 10 include changes to launch scope or operational guarantees and need an explicit choice.

## 1. Let the serving host own cold adapter loading and cache state

**Current design:** a cold request creates a Valkey warm intent. A worker acts on it. The host loads the adapter and reports status. The gateway waits for the projected readiness before dispatch.

**Proposal:** the gateway asks a compatible host to prepare the exact authorised adapter through the private loader. The host combines duplicate loads, reads accepted objects from S3, and returns the manifest and engine boot identity. The gateway then performs normal admission. The runtime verifies the adapter at dispatch and holds a local use reference.

Keep fetch, validation, loading, eviction and request references local. Report bounded status snapshots with the engine boot id, applied production-set revision, loaded identities, aggregate resource use and failures. Add incremental status updates only if measured snapshot cost requires them.

This removes the distributed warm-intent queue and much of the cache-state synchronisation. It keeps tenant checks, exact-byte validation, production protection, memory limits and load deadlines. It does not expose runtime management endpoints to customers. vLLM supports dynamic loading within a trusted boundary. [vLLM dynamic LoRA loading](https://docs.vllm.ai/en/v0.28.0/features/lora/#dynamically-serving-lora-adapters).

**Before acceptance:** test simultaneous cold requests, cancellation, cache saturation, process restart and eviction between preparation and dispatch. Keep existing serving status independent of a PostgreSQL query on every heartbeat; initial registration can still validate durable ownership.

Owner: [SERV-01 and SERV-02](TASK_FINE_TUNING_SERVING_CONTRACT.md), with gateway and status-contract updates.

## 2. Finish training at publication; run evaluation independently

**Current design:** a run remains non-terminal through evaluation. Only one non-terminal run is allowed per task. A provider outage can therefore block the next training run after a valid model has been published.

**Proposal:** complete training when publication succeeds. Create a separate evaluation operation with its own status, retries, deadline and cancellation. The console can show evaluation beside the training run through their explicit link.

This keeps training independent of the final judge and provider calls. Publication and manual promotion still do not depend on evaluation quality.

**Before acceptance:** define cancellation after publication, evaluation authorisation after the run becomes terminal, and the effect of capture disable. Persist the evaluation request with publication so a worker crash cannot lose it. Keep all evaluation calls bounded.

Owner: [RUN-02 and RUN-04](TASK_FINE_TUNING_RUN_CONTRACT.md), [EVAL-03](TASK_FINE_TUNING_EVALUATION_CONTRACT.md).

## 3. Keep the recipe inside the trainer

**Current design:** the plan describes versioned recipe steps, checkpoints after each step, and generic side-effect records. This can become a recipe interpreter in the control plane.

**Proposal:** expose one boundary: immutable inputs, a pinned trainer image, a deadline, bounded progress, an optional resume input, and an output manifest. The trainer owns its internal steps. The control plane owns submission, cancellation and accepted results.

This lets the learning method change without changing the gateway, fleet policy or run state machine. Durable records remain necessary for external control-plane effects. Local trainer steps do not each need a database workflow row.

**Before acceptance:** separate local progress from accepted outcomes. Add an external step protocol only when a real recipe requires it.

Owner: [RUN-01, RUN-03 and RUN-05](TASK_FINE_TUNING_RUN_CONTRACT.md).

## 4. Require the trainer to emit the serving format

**Current design:** the publisher accepts an archive, validates extraction, converts formats, validates tensors, load-tests and copies the result. Launch has no customer uploads, and we own the trainer image.

**Proposal:** require named safetensors and configuration files plus a manifest. Reject other input formats. Remove archive extraction and publisher-side conversion. An export archive can be built from accepted files if the download flow needs one.

Keep tensor bounds, finite-value checks, layout and base checks, content hashes, immutable object versions and load tests. Record expected object names before upload and returned S3 version ids after upload. Copy validated bytes into publisher-only storage before the private loader tests those unpublished bytes. Publish customer availability only after the test succeeds.

This removes conversion states, extraction code and temporary copies. It also makes the publication order compatible with the loader's publisher-only storage rule.

Owner: [ART-01 and SERV-01](TASK_FINE_TUNING_SERVING_CONTRACT.md).

## 5. Store each fact once

**Current design:** a restriction intent overrides a policy boolean that still says enabled. A second transaction changes the boolean after projection. Other candidates for duplicated state include model readiness, copied release fields and independently updated counters.

**Proposal:** commit the authoritative restricted state, revision, audit and projection work once. Track projection completion separately. Control-plane checks see the restriction immediately. Report it as effective at the gateway only after acknowledgement and the cache bound.

Derive model readiness from current runtime observations. Reference an immutable compatibility profile instead of copying its fields into independently mutable model columns. Derive counters from accepted records or rebuildable views. Keep hashes where exact-byte verification requires them.

**Before acceptance:** retain ordered projections, tombstones, bootstrap handling and the acknowledgement barrier. Keep the existing money-projection contract separate. Require a concrete consumer for each additional identity or state field.

Owner: [OPS-01](TASK_FINE_TUNING_OPERATIONS_CONTRACT.md), [SERV-01](TASK_FINE_TUNING_SERVING_CONTRACT.md), and the plan's data catalogue.

## 6. Use the provider-call operation as its concurrency reservation

**Current design:** each external call has an operation and attempt. Separate provider slots add another ownership and expiry lifecycle for the same call.

**Proposal:** under a short provider-credential-scoped PostgreSQL lock, count active unexpired attempts and claim the next eligible operation. The claimed attempt is the reservation. Release or expire it under its own identity. Never hold the transaction during the HTTP call.

This removes the separate durable slot record. Keep local connection bounds, fair queue selection, deadlines, retry limits and accepted-result identity.

**Before acceptance:** test concurrent claims, worker loss and late responses. A timeout does not prove that the provider stopped computing. Keep uncertain calls reserved until their bound and record possible duplicate cost.

Owner: [RUN-04](TASK_FINE_TUNING_RUN_CONTRACT.md), [EVAL-03](TASK_FINE_TUNING_EVALUATION_CONTRACT.md).

## 7. Defer the full fleet policy calculation until automatic scaling

**Current design:** operators set counts at launch, but launch still computes throughput targets and accounts for shared serving service across organisations and hardware classes.

**Proposal:** launch with demand metrics, operator counts, protected capacity, recovery and a smaller training queue. Implement the full demand-to-target policy when its output will control allocation. Keep the workload-target interface small enough for that later policy to use.

**Choice required:** does equal training priority mean equal turns or equal consumed GPU time? Organisation round-robin gives equal selection opportunity. A small per-class service counter can account for GPU time. Neither requires shared-inference fairness accounting before automatic serving allocation exists.

Owner: [FLEET-00 and FLEET-03](TASK_FINE_TUNING_FLEET_CONTRACT.md).

## 8. Use operational metrics for the internal availability target

**Current design:** the 99.9% target has a separate event stream, edge-to-gateway request matching, coverage manifests, a finalisation window and revised monthly reports.

**Proposal:** use terminal request-outcome counters, edge failure counters, monitoring-gap alerts and independent end-to-end probes. Count capacity failures, cold-load failures and interrupted streams. Keep detailed generations for diagnosis and Incident.io for response. Metrics-based SLO measurement is an established approach. [Google SRE guidance](https://sre.google/workbook/implementing-slos/).

**Choice required:** this changes the reporting promise. Metrics and probes do not prove the exact, individually reconciled monthly denominator in the current contract. Retain that event system if the exact report is required. Do not report missing monitoring coverage as success.

Owner: [OPS-05](TASK_FINE_TUNING_OPERATIONS_CONTRACT.md).

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
| Cleanup after a year without use | Retain models and record publication and customer-use evidence now | Keep explicit purge. Build inactivity cleanup before it can act; check imported models before deferring it. |
| Full checkpoint resume | Retry short jobs from the same accepted inputs and starting adapter | Measure job duration and restart cost first. A host failure loses progress. Keep the original deadline and retry ceiling. |

If resume is needed at launch, prefer one trainer-owned checkpoint format and one accepted checkpoint pointer. The control plane does not need to understand optimizer contents.

Owners: [CAP-02](TASK_FINE_TUNING_GATEWAY_CONTRACT.md), [EVAL-03](TASK_FINE_TUNING_EVALUATION_CONTRACT.md), [SERV-04](TASK_FINE_TUNING_SERVING_CONTRACT.md), [RUN-02 and RUN-03](TASK_FINE_TUNING_RUN_CONTRACT.md).

## Document maintenance

Give each rule one owning contract. Keep the overview focused on architecture, dependencies and build order. Treat diagrams as illustrations of the owning rule. Link to field semantics instead of copying them across documents.

For each module, state which dependencies are required for new work, existing serving and telemetry. This makes unnecessary availability dependencies easier to find. Apply accepted proposals to those contracts rather than creating a second implementation specification here.
