# ADR-0007: Immutable full-stack model bundles and separate research/release authority

- Status: accepted
- Date: 2026-07-13
- Amended: 2026-07-14
- Extends: ADR-0003, ADR-0005 and ADR-0006

## Decision

The research factory produces a content-addressed, signed `ModelStackBundle` that includes the complete deployable vertical stack: model/checkpoint and factory-produced architecture, tokenizer/templates/parsers, runtime image, kernels, compression, scheduler/cache, parallelism/topology, placement envelope, protocol/data-policy contract, operations metadata and exact evidence references.

Research, qualification, staging and production use the same bundle digest. Production does not rebuild or manually recreate a candidate. PostgreSQL owns campaign/evidence/qualification/release/alias state; S3 owns immutable large objects; ECR/OCI indexes the bundle and runtime images; signatures and attestations bind build/test/approval predicates to the digest. Redis receives only the bounded active route projection needed by the gateway.

Use separate state machines and roles for:

1. experiments and scope-matched evidence;
2. candidate assembly and bundle qualification;
3. production release, rollout, alias movement and rollback.

The factory is a deliberately polyglot, always-on inference laboratory. Python owns model research, PyTorch references, training, quantization, evaluation, Triton kernel exploration, campaign planning and Temporal workflows. TypeScript owns the operator UI and authenticated Hono/tRPC BFF. Rust owns bundle inspection/materialization, runtime supervision, cells, inference transport and the gateway. The research service is the sole normal writer of campaign, evidence, candidate and qualification state; the BFF calls its generated private API instead of duplicating research state machines.

Each supported model has a durable `ModelProgram`: baseline, current champion, Pareto frontier, open questions, negative findings, active campaigns and a ranked experiment queue. Scanner, planner and agent loops run continuously, but recurring GPU work is admitted only through a bounded immutable experiment specification with hypothesis, expected information value, budget, timeout, stop rule and cleanup contract. Always-on means continuous attention and learning, not permanent GPU consumption.

Fable and Sol are spike evidence, not implementation dependencies or compatibility targets. Useful algorithms, controls and tests are ported into factory-owned packages with provenance and fresh validation; abandoned shapes remain historical. Neither a simulation nor an isolated component win can authorize production.

Temporal orchestrates durable cross-provider research campaigns. Kubernetes execution uses Kueue and JobSet where applicable; provider-native allocations remain honest external resources behind the research execution adapter. Research allocations and production cells have disjoint identities, credentials, registration paths and budgets.

A candidate graduates through measured stages: eager PyTorch reference, compiled/reference validation, Triton kernel candidate, out-of-tree framework runtime, optional native CUDA/C++ component and, only when whole-system evidence warrants it, an owned Rust engine integration. A production bundle declares `python_plugin`, `native_library` or `rust_engine`; promotion does not require a Rust rewrite. Language-neutral Protobuf services plus canonical JSON `ModelArchitectureSpec`, `CheckpointManifest`, `OperatorManifest`, `RuntimeManifest` and `QualificationManifest` contracts connect research to Rust launch and serving.

Public model identities have three layers:

- `grad/<family>/<speed>` is a mutable head restricted to one declared family compatibility envelope;
- `grad/<effort>/<speed>` is a managed product head restricted to its quality/capability/service/price envelope and may cross qualified families with actual-release disclosure;
- `grad/<family>/<speed>@<release>` is an immutable release pin.

Canonical speed classes remain `flex|standard|fast|turbo`; preview `slow` may alias `flex` but is not a separate lane.

At seed, autonomous agents may run research and propose releases within explicit authority and budget. A human release owner approves a signed proposal before any public alias moves. Automatic canary progression and rollback are allowed only within that approved proposal. Fully autonomous public promotion requires a later ADR.

## Why

The product's differentiator is co-design across model architecture, weights, kernels, runtime, serving and hardware. A checkpoint-only registry would lose the interactions that created the result and could deploy code or topology that was never tested. Conversely, coupling exploratory agent work directly to production aliases would let mutable research state bypass financial, protocol, security and reliability guarantees.

An immutable complete bundle makes the experimental subject, qualified system and served system the same object. Separate authorities preserve fast exploration while keeping promotion fail-closed and auditable. Stable aliases give customers a simple experience without pretending the underlying system never improves.

## Alternatives

1. **Chosen: custom full-stack bundle registry plus existing RouteRelease.** Matches Grad's multi-component product, exact cell attestation, pricing and rollback requirements.
2. **Checkpoint registry such as MLflow as authority.** Rejected as the primary authority. Versions/aliases are useful, but a conventional model artifact does not freeze the runtime, kernels, topology, security profile, cell qualification, price or Redis projection. MLflow may be a rebuildable research UI mirror.
3. **Container image as the entire bundle.** Rejected. Multi-terabyte weights and datasets do not belong in every runtime image, and an image alone cannot express evidence, placement, protocol or release policy. The bundle references both image and S3 object digests.
4. **Mutable tags and environment configuration.** Rejected. They break reproducibility and allow staging/production drift.
5. **Argo Workflows as the global orchestrator.** Deferred. It is useful for Kubernetes DAGs and S3 artifacts, but the campaign spans code agents, native provider leases, human waits and non-Kubernetes cleanup. It may be an execution adapter if measured researcher throughput justifies another control plane.
6. **One Kubernetes cluster or fake Nodes across providers.** Rejected by ADR-0006 and remains rejected for research. Kueue governs only honest Kubernetes workloads.
7. **Fully autonomous promotion at launch.** Rejected until measured false-positive, canary and rollback history supports that authority safely.
8. **One language for research and production.** Rejected. All-Rust slows model and kernel exploration; all-Python weakens the long-lived serving boundary. The artifact and launcher contracts, not source-language uniformity, provide continuity.
9. **Adapters preserving Fable/Sol shapes.** Rejected. Compatibility with exploratory spikes would freeze accidental interfaces and create two authorities.
10. **Require every candidate to become native/Rust before production.** Rejected. A qualified framework plugin may be the best deployable result; native work is justified only by measured residual bottlenecks or operational value.

## Consequences

- positive: exact parity from qualification to production and digest-level rollback/audit;
- positive: research can change the entire vertical stack without exposing that complexity in the customer model surface;
- positive: agent autonomy is bounded by campaign, evaluator and release authorities rather than ad hoc human supervision;
- positive: every supported model receives persistent hypothesis generation, baseline maintenance and portfolio allocation without requiring a human to restart the loop;
- positive: Python keeps the model ecosystem's fastest research path while Rust retains a stable, fail-closed production boundary;
- positive: family, managed and pinned identities serve distinct compatibility needs;
- negative: Grad must build bundle schemas, canonicalization, artifact GC, signatures, qualification and registry UI beyond a checkpoint registry;
- negative: evaluator ownership, hidden datasets and full-cell qualification add cost and operational latency;
- negative: Grad must operate a generated cross-language contract and support qualified Python, native-library and Rust runtime modes;
- negative: an always-on portfolio manager requires explicit anti-churn, spend and experiment-value controls so activity does not become the objective;
- negative: public pins require explicit support and capacity economics;
- limit: evidence is valid only for its exact model/workload/hardware/software/intervention scope and expiry;
- limit: production cells may run only bundles whose placement envelope and required attestations match the observed host;
- migration: preserve current `ReleaseManifest`/`RouteRelease`, add bundle identity and alias generation, then require exact cell attestation before public targets are published;
- reversal trigger: a standard registry proves it can authoritatively model, sign, qualify, price and atomically release Grad's complete stack without weakening these invariants, or Temporal operations fail the bounded orchestration spike.

## Detailed contract

The implementation architecture, state machines, qualification ladder, agent roles, naming rules, package plan and falsification spikes are in [Model research factory to production](../../product/docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md).
