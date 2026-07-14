# Model lanes, Grad effort/speed products, and workload migration

> The two-lane product decision remains current. Storage and serving details are superseded by [current architecture](ARCHITECTURE.md) and the [simplicity review](../../docs/SIMPLICITY_REVIEW.md): PostgreSQL serves seed analytics, recommendations are derived from primary usage/trace state, and owned traffic uses the private inference router without signed target projections.

## Product decision

The gateway has two connected model lanes:

1. **Curated direct-provider models** let a customer move an existing workload by changing the base URL and API key while preserving its provider/model behavior.
2. **First-party Grad models** are served on our inference and selected as `grad/<effort>/<speed>`. They are the differentiated product: explicit compute-quality effort plus explicit serving-speed class.

Direct-provider traffic earns revenue and, in the default Product Intelligence data mode, produces the traces needed to identify Grad migration opportunities. A recommendation never changes traffic. It explains the evidence and offers an explicit replay, shadow, or live-canary experiment controlled by the customer.

## Curated direct-provider lane

### Seed registry

The initial provider families are:

| Namespace | Provider | Why it is included | Boundary |
| --- | --- | --- | --- |
| `openai/` | OpenAI | Large installed workload base and first-class Chat/Responses/Embeddings behavior. | Only model versions and fields in our tested registry. |
| `anthropic/` | Anthropic | Large Messages/tool workload base and a distinct native protocol. | Only model versions and fields in our tested registry. |
| `google/` | Google Gemini | Important frontier/multimodal supply with official native and OpenAI compatibility guidance. | Seed plans both a pinned Google-native SDK skin and OpenAI-compatible access; each field/version is fixture-tested. |

This is a deliberately short launch set, not a permanent moat around three vendors. Adding a provider requires a provider-level adapter review and model-level protocol, privacy, reliability, pricing, metering, and support qualification. OpenRouter, Together, Fireworks, Groq, DeepInfra, cloud resellers, and arbitrary OpenAI-compatible URLs are not customer-selectable providers at seed. OpenRouter remains an operator-only upstream contingency and a downstream distribution channel for our inference.

The official provider surfaces are time-sensitive. Implementation revalidates [OpenAI API behavior](https://platform.openai.com/docs/api-reference), [Anthropic's API](https://docs.anthropic.com/en/api/overview), and [Gemini's gateway/partner integration guidance](https://ai.google.dev/gemini-api/docs/partner-integration) before freezing each adapter/model profile.

### Model identity

Canonical model IDs are provider-qualified:

```text
openai/<upstream-model-id>
anthropic/<upstream-model-id>
google/<upstream-model-id>
```

The registry may expose a bare upstream model ID as a compatibility alias only when it maps to exactly one active provider/model definition. This supports a base-URL-and-key-only migration. If an alias becomes ambiguous, new requests fail with `ambiguous_model` and list canonical choices; an alias never silently changes binding. An optional `x-grad-provider` header can disambiguate a bare ID, but the namespaced ID is the durable form.

A direct-provider request is a hard provider and concrete-model pin:

- it may retry another qualified endpoint operated by that same provider for that exact model/version;
- it never crosses provider, model family, or model version unless the customer changes the model ID;
- it uses the provider model's published Grad sell price and capability/data-policy profile;
- native provider service-tier fields are supported only when explicitly qualified and are not confused with Grad speed levels;
- provider credentials are ours at seed; arbitrary BYOK remains deferred.

## First-party Grad lane

### Public identity

Every first-party model product is:

```text
grad/<effort>/<speed>
```

Effort and speed are orthogonal. Effort controls the inference compute/quality budget. Speed controls the serving lane and capacity policy. The default is `grad/medium/standard`.

Two advanced identities expose stability without making the default experience more complex:

```text
grad/<family>/<speed>
grad/<family>/<speed>@<release>
```

For example, `grad/glm-5.2/fast` follows qualified complete-stack releases only within the declared GLM 5.2 family compatibility envelope, while `grad/glm-5.2/fast@r2026.07.13.3` is an immutable release pin. A family head never silently becomes another family. A managed effort/speed head may change families only through qualification against its published product envelope, canary and rollback, with the actual family/release disclosed.

Compatibility aliases from the earlier design resolve as documented redirects during preview only:

| Deprecated alias | Replacement |
| --- | --- |
| `grad/auto` | `grad/medium/standard` |
| `grad/fast` | `grad/medium/fast` |
| `grad/smart` | `grad/high/standard` |
| `grad/code` | `grad/high/fast` initially; code capability is a release qualification, not a permanent separate product. |
| `grad/open` | `grad/medium/standard`; every canonical Grad product is our inference, so `open` is redundant. |
| `grad/<effort>/slow` | `grad/<effort>/flex`; preview compatibility only. `flex` describes queue tolerance and cost posture more accurately than a latency promise. |

Aliases produce a deprecation header and console warning and are removed before general availability unless real preview customers require a longer window.

### Effort levels

| Effort | Intended workload | Compute contract |
| --- | --- | --- |
| `low` | extraction, classification, rewriting, simple chat, high-volume deterministic work | Small bounded reasoning/compute budget; lowest price and quickest completion at a given speed. |
| `medium` | default general use, RAG, common tools and application logic | Balanced compute budget and the recommended starting point. |
| `high` | difficult coding, multi-step tools, analysis and higher-complexity generation | Larger reasoning/compute budget and stricter quality qualification. |
| `max` | hardest supported tasks where quality dominates cost | Highest bounded compute budget; explicit higher price/output latency and lower default concurrency. |

Effort is not a hidden prompt rewrite and does not promise correctness. Each release publishes supported capabilities, context/output limits, evaluation scope, and any reasoning controls. A request-level reasoning parameter can make behavior stricter only within the selected effort contract; incompatible values fail explicitly.

### Speed levels

| Speed | Serving behavior | Customer expectation |
| --- | --- | --- |
| `flex` | price-optimized queueing and batching; preemptible/spare capacity where safe | Lowest price; bounded queue deadline; suited to asynchronous or non-urgent work. |
| `standard` | normal online serving, balanced batching and capacity | Default price/performance and broadest availability. |
| `fast` | reserved lower-batch/queue lane with stronger TTFT/throughput target | Interactive production traffic at a premium. |
| `turbo` | highest-priority qualified hardware/configuration, aggressive latency optimization and strict admission | Fastest published lane, highest price, capacity-limited with early 429 rather than silent downgrade. |

Speed is an end-to-end serving class, not just queue priority. A release freezes hardware/runtime/quantization, batching, speculative-decoding policy, queue deadline, TTFT/throughput objectives, price, capacity and fallback behavior. Numeric SLOs are published only after measured qualification. The gateway never serves a slower speed class under a faster ID; it returns typed capacity/unavailable errors.

All 16 effort/speed combinations are valid product identities, but a combination is exposed in `/v1/models` only after its release is qualified and has launch capacity. This keeps the grammar stable without pretending every cell is available on day one.

### First-party routing and release rules

- Canonical `grad/*/*` traffic is served only by our owned inference fleet.
- A request resolves to one immutable `RouteRelease` and `ModelStackBundle` before admission and cannot change because an alias moves while it is in flight.
- A managed head may move among complete bundles qualified for that exact effort/speed product, preserving its capability, quality, data-policy, price-policy and SLO envelope.
- A family head may move only inside its declared family compatibility envelope. An immutable `@release` pin never moves.
- There is no hidden external frontier fallback. A customer who wants an external provider requests its namespaced model directly.
- Releases remain immutable, fixed-price, canaried, session-sticky where useful, and rollbackable.
- Actual family, release and bundle identity are disclosed in authenticated usage metadata; internal host/topology and protected model artifacts remain hidden.
- Effort/speed may map to different owned families over time only through a published complete-stack release, compatibility evaluation, canary and rollback. Customers requiring reproducibility use the immutable public release pin.

The research factory is allowed to change weights/model architecture, custom operators, kernels, runtime, scheduler/cache, topology and hardware mapping. Those changes are one content-addressed `ModelStackBundle`; the exact bundle is qualified and promoted rather than manually reproduced in serving. See [Model research factory to production](MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md).

## Data modes and trace retention

### Product Intelligence — default

The default workspace mode retains bounded encrypted inference traces so we can provide request inspection, workload grouping, regressions, cost/latency analysis and Grad migration recommendations.

- Initial raw trace-retention target is 30 days, configurable downward and subject to launch legal/security review.
- Metadata and derived workload/evaluation summaries may be retained longer under the published account retention schedule.
- Traces may contain request messages, responses, tool schemas/calls/results and safe customer tags. Authorization headers, API/provider keys, transport cookies and unrelated headers are always excluded.
- Files and payloads over the trace-size limit are omitted or represented by safe metadata; inference continues and capture status explains the omission.
- Retention for customer features does not grant model-training rights. Training or global model improvement on customer content requires a separate explicit opt-in and contract.
- Customers can inspect, export and delete retained traces; deletion is asynchronous, audited and enforced by object lifecycle/tombstones across every object version. Raw trace backup/replication cannot extend the published retention deadline.

### Private / No Retention — opt-in

A workspace can select Private/No Retention, and any request can tighten Product Intelligence with `x-grad-data-policy: no-retain`. In this mode:

- the gateway records only the minimum billing, security and aggregate operational metadata;
- no request/response/tool/file payload is written to the trace stream or object store;
- route eligibility requires the selected direct provider or Grad deployment to meet the documented no-retention policy;
- owned Grad execution still uses active-sequence and cross-request prefix KV cache. It is separated into an opaque no-retention workspace/channel/release namespace, kept only in ephemeral GPU/RAM or qualified encrypted local spill, and never copied to trace/object/analytics storage;
- content-based workload analysis, replay and migration recommendations are unavailable; metadata-only cost/latency suggestions are clearly labeled low confidence.

A request cannot loosen a workspace's mode. Provider training/data use is a separate eligibility dimension and remains disallowed unless a future customer explicitly chooses otherwise.

### Trace transport and storage

The gateway keeps Redis as its only synchronous internal state/control dependency; model APIs and the inference edge are upstream serving dependencies:

```text
request/response events
  -> gateway strips credentials and applies workspace/request data mode
  -> bounded trace encrypted with a random data key; data key wrapped to the trace-ingest public key
  -> ciphertext XADD to organization-tagged Redis trace stream
  -> trace worker drains ciphertext to private S3 object storage
  -> PostgreSQL stores authorization, wrapped-key state, retention/tombstone and object reference

terminal settlement
  -> financial worker posts authoritative usage and an analytics outbox record in PostgreSQL
  -> trace-analytics projector batches typed content-free facts into ClickHouse Cloud
  -> Hono queries ClickHouse for trace lists/charts/workload analytics
  -> trace detail is separately authorized in PostgreSQL and decrypted from S3
```

The worker owns the KMS-backed private/decryption path; the gateway receives only an active trace-encryption public key through Redis projection. A separate trace-access service can decrypt one object only after receiving a signed, short-lived, single-use grant bound to user/workspace/trace/action and after rechecking retention/deletion/key state; every view/export is audited and never becomes a reusable S3 URL. Per-trace wrapped-key destruction provides immediate cryptographic revocation before object/version cleanup completes.

ClickHouse Cloud is a replayable analytics projection, not raw trace custody. It stores only allowlisted typed dimensions, usage/latency/cost copies, derived workload/evaluation features and aggregates—never prompts, responses, tool arguments/results, files, credentials, arbitrary headers or free-form tags. PostgreSQL remains authorization, ledger, trace-registry, retention/delete and experiment authority; encrypted raw payloads remain in private S3. The browser never receives ClickHouse credentials or SQL capability. This split and its delete/restore gates are specified in [ClickHouse trace analytics decision](CLICKHOUSE_TRACE_ANALYTICS_DECISION.md) and [ADR-0004](../../docs/decisions/0004-clickhouse-trace-analytics.md).

Payloads are never plaintext in PostgreSQL, ClickHouse, logs, metrics or CI artifacts. Trace capture is not part of financial admission: under backpressure or encryption/config failure, inference and billing continue, capture is marked `skipped_*`, and the system alerts. A ClickHouse outage delays analytics only; it cannot block inference, settlement, PostgreSQL posting or S3 persistence. Separate quotas/TTL/headroom/KEDA scaling prevent trace traffic from starving billing.

## Workload intelligence and migration recommendations

### Workload model

Customers may provide `x-grad-workload-id` and bounded request tags. The raw customer label/tag values remain in the encrypted payload object; ClickHouse receives only a generated internal workload UUID or workspace-scoped HMAC for explicitly indexed identifiers. Otherwise the processor derives a workspace-local workload fingerprint from protocol, model, capability use, normalized parameter shape, tool/schema hashes, input/output size bands and—only in Product Intelligence mode—content-derived features. Fingerprints are HMAC-scoped per workspace so they cannot become cross-customer tracking identifiers.

Core records are:

- `TraceRecord`: PostgreSQL authorization/tombstone/key state, encrypted object reference, request/response linkage, capture status, policy, retention deadline and analytics-projection status;
- `WorkloadProfile`: workspace-local group, direct-provider baseline, capability/schema requirements, volume, errors, token/size distributions, latency and spend;
- `MigrationCandidate`: proposed Grad effort/speed product, compatibility result, projected price/performance, evidence scope and confidence;
- `MigrationExperiment`: bounded replay, shadow or live canary with customer approval, budget, sample, evaluator and stop conditions;
- `MigrationRecommendation`: immutable evidence snapshot, status, reasons, exclusions, uncertainty, expected savings/latency, quality result and one-click next action.

### Recommendation evidence ladder

| Level | Evidence | UI language/action |
| --- | --- | --- |
| `opportunity` | Metadata compatibility, volume, cost and latency only. | “This workload may fit …”; inspect requirements. |
| `candidate` | Retained samples replayed on owned Grad inference; protocol/schema/tool checks and baseline-output comparison pass. | Review sample/evaluation evidence. |
| `verified` | Customer evaluator or approved shadow experiment passes quality and safety thresholds. | Start a bounded live canary. |
| `ready` | Live canary meets customer-defined error, quality, latency and cost stop conditions. | Explicitly change the workload's configured model. |

The system never labels a generative migration “equivalent” from token/latency metadata alone. Structured-output validity, tool behavior, refusal/safety behavior, task quality and tail latency are workload-specific. Recommendations include sample size, dates, source provider/model, candidate Grad release, evaluator, confidence and known gaps.

### Experiment behavior

- Automated offline replays use retained Product Intelligence traces and our inference; they are internal product-evaluation cost and never charged as customer inference.
- Shadowing or live canaries require an explicit customer action, percentage, dollar/request budget, timeout and rollback condition.
- Shadow Grad outputs are not returned to the application. They use the same data mode/retention policy and are linked to the baseline trace.
- Live canaries run only when the application adds `x-grad-migration-experiment: <id>` to a request. The experiment contract explicitly authorizes direct-or-Grad routing for that request, uses stable workload/session buckets, and returns actual identity/price. Without the header, a direct provider/model remains a hard pin even when an experiment exists. Removing the header is immediate client-side rollback.
- Failure, schema/tool regression, quality threshold breach, excess cost or SLO breach halts the experiment automatically; it does not alter the original workload configuration.
- The customer performs the final model change to the canonical Grad ID. Merely creating/starting an experiment in the console never intercepts ordinary traffic. A future auto-migration feature requires a separate ADR and opt-in.

## Console experience

The five-screen shell remains, but Models and Usage become the bridge:

- **Overview:** quickstart defaults to the inferred/brought-over provider model when onboarding an existing workload; a new workload defaults to `grad/medium/standard`.
- **Models:** two tabs—“Grad” effort × speed selector first, “Direct providers” second. Provider models are grouped under only OpenAI, Anthropic and Google; there is no provider endpoint table.
- **Usage:** Hono serves ClickHouse-backed workload groups, charts and individual trace facts with provider/model, capability, latency, cost and retention deadline. Opening payload detail follows the separate PostgreSQL authorization and S3 decrypt path. A Migration card appears only with sufficient evidence.
- **Settings → Data:** Product Intelligence default, retention/delete/export controls, Private/No Retention, request-header example and provider-policy implications.
- **Migration flow:** recommendation → evidence → configure evaluator/budget → replay/shadow → live canary → customer-approved switch.

The first provider migration quickstart changes the provider base URL/key and can keep an unambiguous bare model ID. The first Grad quickstart is one obvious choice: `grad/medium/standard`. The effort/speed grid is explained through workload outcomes, not infrastructure jargon.

## Billing and commercial contract

- Direct-provider models have immutable per-model sell prices. Provider buy price and failed retries are our margin risk.
- Every Grad effort/speed release has a fixed input/output/cache/reasoning price. Speed premiums and effort compute are visible before use.
- A speed lane never silently downgrades to preserve margin or capacity.
- Internal recommendation replays are not deducted from organization credit. Customer-approved live canary requests are normal billed requests; the UI estimates and caps exposure before start.
- Failed-request credit, organization prepaid admission, workspace/key budgets and low-balance concurrency apply equally to both lanes.
- Contribution margin is measured separately by provider-qualified model and Grad effort/speed release.

## Acceptance gates

Before enabling a direct provider/model:

- compatibility fixtures pass for every claimed protocol/capability;
- exact provider/model identity, retention/training policy, price, usage and failure behavior are current and source-dated;
- concrete provider pinning cannot cross namespace/version;
- margin and protected real-provider smoke pass.

Before enabling a Grad effort/speed cell:

- the factory-produced complete stack is frozen as one signed `ModelStackBundle`; research, qualification and the cell launch the same digest;
- model/custom-architecture, kernel/runtime, protocol/metering, measured single-node, distributed-cell, security/privacy and production-like soak gates pass against tuned stock and active-production controls;
- the exact runtime/release must prove always-on salted prefix cache, no cross-workspace/channel/retention-class reuse, bounded eviction/teardown and no payload-bearing logs/backups;
- the external-provider cell must pass the provider/region/topology/security/interruption/effective-successful-token-cost gates in [Owned Grad inference architecture](OWNED_INFERENCE_ARCHITECTURE.md);
- bundle identity, evaluation scope and evidence expiry are bound into a RouteRelease;
- capability, privacy, quality, TTFT, throughput, queue deadline, availability, capacity and margin gates pass for that cell;
- speed monotonicity holds under representative load (`turbo` no slower than `fast`, and so on, within published statistical tolerance);
- effort monotonicity is demonstrated on the declared evaluation scope or the release is not marketed as a higher effort;
- canary, session behavior, fixed pricing and rollback pass property and fault tests.

Before showing a recommendation:

- source workload and candidate release are current;
- capability/privacy hard requirements pass;
- evidence level and uncertainty are displayed accurately;
- projected savings/latency use workload-scoped traces, not catalog averages;
- no automatic traffic change occurs.
