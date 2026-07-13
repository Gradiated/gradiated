# ADR-0003: Curated provider lane, Grad effort/speed products, and trace intelligence

- status: accepted for planning; supersedes ADR-0002 model taxonomy and payload-retention boundary
- GitHub issue: https://github.com/joshsny/gradiated/issues/4
- owner: product architecture
- date: 2026-07-13

## Decision

Expose two connected model lanes:

1. A curated direct-provider registry with canonical `openai/<model>`, `anthropic/<model>`, and `google/<model>` identities. A bare upstream model ID is accepted only while it has one unambiguous active binding. Direct requests never cross provider/model/version.
2. First-party `grad/<effort>/<speed>` products served only on owned inference. Effort is `low|medium|high|max`; speed is `flex|standard|fast|turbo`; the default is `grad/medium/standard`. Every enabled cell has an immutable fixed-price qualified RouteRelease and never silently leaves its effort/speed lane.

Product Intelligence is the default workspace data mode. The gateway strips credentials, bounds and encrypts request/response/tool traces with a random data key, wraps that key to a rotating ingest public key, and emits ciphertext to a separate Redis stream. Workers store encrypted payloads in private lifecycle-managed S3 and authorization/key/retention metadata in PostgreSQL. ADR-0004 adds ClickHouse Cloud as a content-free replayable trace-analytics projection; it does not change raw payload custody or authority. Initial raw retention targets 30 days, configurable downward and subject to launch legal/security review. Private/No Retention can be selected at workspace level or as a stricter request header and suppresses payload capture before Redis.

Trace processors group requests into workspace-local workloads and propose Grad migrations. Evidence progresses from metadata `opportunity`, to retained-trace replay `candidate`, to customer evaluator/shadow `verified`, to live-canary `ready`. Replays/shadows are not customer-billed; live canaries use ordinary prepaid admission plus an experiment cap. No system state automatically changes the customer's requested model.

Trace retention grants permission only for the customer's product features. It does not authorize training/global model improvement; that requires a separate explicit opt-in and ADR.

## Context and constraints

Customers need exact direct provider access to migrate without a risky semantic cutover. That traffic is also the best workload-scoped baseline for recommending our inference. The differentiated product is not generic automatic provider routing; it is owned inference with understandable effort and speed controls plus evidence that a workload can move.

The gateway must retain Redis as its only synchronous internal state/control dependency, so trace capture cannot synchronously call S3/PostgreSQL/KMS. Billing events are correctness-critical while trace capture is valuable but shed-able. Trace ciphertext therefore uses a distinct Redis stream, separate quotas and workers; financial admission/settlement never depends on trace success.

## Alternatives considered

1. **Chosen: curated direct identities plus Grad effort/speed and default trace intelligence.** Creates easy migration, explicit differentiated supply and a measurable conversion funnel.
2. **Only Grad models.** Rejected because it creates a high-friction behavioral migration before we have workload evidence.
3. **Every provider/OpenRouter-style catalog.** Rejected because support, privacy and identity complexity would dominate differentiation.
4. **Hidden owned-inference preference behind direct IDs.** Rejected because it violates provider/model fidelity and customer trust.
5. **No payload retention by default.** Superseded because trace-based customer features and migration intelligence are now core; a no-retain mode remains available.
6. **Synchronous gateway-to-S3 trace writes.** Rejected because it adds a second internal hot-path dependency and couples inference availability to object storage.
7. **Automatic migration after recommendation.** Rejected because workload quality and safety require customer evaluators, bounded canaries and explicit authority.

## Consequences

- positive: existing applications can often change only base URL/key; exact namespaced IDs remain durable when aliases are ambiguous.
- positive: the Grad product is legible and defensible—compute effort and serving speed are explicit, measured dimensions on our inference.
- positive: retained traces enable history, analytics, regression detection and workload-scoped migration evidence.
- negative: encrypted trace storage, access, deletion, export and incident response become launch-critical security/compliance systems.
- negative: 16 possible Grad cells require disciplined qualification/capacity; unavailable cells must be hidden rather than launched aspirationally.
- negative: direct providers create adapter/support and margin exposure; each model/version remains curated.
- migration/rollback: preview aliases (`grad/auto`, `grad/fast`, `grad/smart`, `grad/code`, `grad/open`) map to documented replacements with warnings and are removed before GA. A workspace can change to no-retain immediately for future requests and delete retained traces asynchronously. Route heads roll back without repricing in-flight requests.

## Evidence

- [Model lanes and migration](../../product/docs/MODEL_LANES_AND_MIGRATION.md): user decision plus derived product/security architecture.
- [OpenRouter feature decisions](../../product/docs/OPENROUTER_FEATURE_DECISIONS.md): vendor-reported broad-marketplace inventory and analytical scope cut.
- [OpenAI API reference](https://platform.openai.com/docs/api-reference), [Anthropic API](https://docs.anthropic.com/en/api/overview), and [Gemini partner integration](https://ai.google.dev/gemini-api/docs/partner-integration): vendor-reported, time-sensitive direct integration surfaces.
- [Billing and Redis](../../product/docs/BILLING_AND_REDIS.md): derived prepaid and experiment-accounting invariants.
- [ADR-0004](0004-clickhouse-trace-analytics.md) and [ClickHouse trace analytics decision](../../product/docs/CLICKHOUSE_TRACE_ANALYTICS_DECISION.md): analytical store, query, deletion, restore and qualification boundary.

No provider request, trace experiment or benchmark has measured provider compatibility, Grad monotonicity, recommendation accuracy or customer trust. Those remain release gates.

## Reversal trigger

Revisit the provider set when retained paid workloads repeatedly require another direct provider and qualification/support economics are favorable. Revisit effort/speed labels when funded users cannot choose them or measured cells do not show useful monotonic quality/latency behavior. Revisit Product Intelligence as default if opt-out/deletion/security evidence shows material trust or compliance harm. Revisit automatic migration only after customers explicitly request it and a separate safety/authority ADR defines rollback and liability.
