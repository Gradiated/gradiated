# OpenRouter feature inventory and opinionated product decisions

Date: 2026-07-13. Retrieval date: 2026-07-13. Scope: current official public OpenRouter documentation and documentation index; no authenticated dashboard, API request, paid traffic, or private commercial terms. OpenRouter behavior is vendor-reported. Every product decision is analytical.

## Decision

OpenRouter is a broad model/provider marketplace and programmable routing substrate. We will build a curated inference and migration product: one endpoint/key, explicit direct access to a short provider/model registry, first-party `grad/<effort>/<speed>` products on owned inference, strict protocol behavior, transparent costs, retained Product Intelligence traces by default, and customer-controlled Grad migration experiments. We will not expose an unbounded provider marketplace, plugin ecosystem, routing DSL, or agent runtime in the seed.

The first-party product grammar is:

| Dimension | Values | Promise |
| --- | --- | --- |
| Effort | `low`, `medium`, `high`, `max` | Explicit bounded inference compute/quality level. |
| Speed | `flex`, `standard`, `fast`, `turbo` | Explicit owned-serving latency/capacity lane. |
| Canonical ID | `grad/<effort>/<speed>` | Fixed-price immutable owned-inference release; default `grad/medium/standard`. |
| Direct IDs | `openai/<model>`, `anthropic/<model>`, `google/<model>` | Exact curated provider/model migration lane, with no hidden cross-provider fallback. |

Grad products have fixed published sell prices per immutable release and never fall back to external providers or a different effort/speed. Direct IDs hard-pin provider/model/version. Bare upstream IDs are compatibility aliases only while unambiguous. The full contract is [Model lanes and migration](MODEL_LANES_AND_MIGRATION.md).

## Test for every feature

A feature is customer-visible only if it passes all four questions:

1. Does it make a common production AI workload materially easier, safer, more reliable, or more economical?
2. Can we provide one coherent behavior across owned open-model inference and frontier providers?
3. Can a new customer ignore it and still succeed in under five minutes?
4. Can we explain its billing, privacy, fallback, and failure semantics without provider jargon?

Decision labels:

- **Keep** — required in the first production product.
- **Simplify** — preserve the user outcome behind a smaller, opinionated contract.
- **Defer** — architecture-compatible, but blocked on demand/evidence or distracts from the seed.
- **Reject** — intentionally not our product surface.
- **Operator-only** — useful internally or for distribution, not a customer configuration surface.

## Complete product-surface inventory

This inventory covers the feature/navigation/API surface in OpenRouter's current docs index. Repeated language SDK method pages and cookbook examples are grouped under the capability they expose; community integrations are grouped rather than duplicated.

### Access, protocols, and SDKs

| OpenRouter capability | Decision | Our contract and rationale |
| --- | --- | --- |
| One API/key for many models | Keep | One base URL and workspace key is the core adoption promise. |
| OpenAI Chat Completions | Keep | Full supported subset, streaming and non-streaming, tested with official SDK. |
| Anthropic Messages | Keep | First-class skin rather than lossy conversion at the client. |
| OpenAI Responses API beta | Keep | Implement a stateless supported subset: text/multimodal input, streaming, reasoning, tools, and structured output. Version fixtures because upstream remains beta. |
| SSE streaming | Keep | Preserve event ordering, usage, cancellation, terminal and mid-stream error semantics. |
| Standard bearer authentication | Keep | One inference key format; accept Anthropic key header only at protocol edge. |
| Official OpenRouter TypeScript/Python/Go clients | Reject | Existing OpenAI/Anthropic/Google clients are the zero-dependency adoption path. A custom inference SDK would fragment expectations. |
| OpenRouter Agent SDK | Reject | We are an inference layer, not a second agent framework/runtime. |
| MCP server | Defer | A model-discovery/usage MCP may help agents later, but it is not the serving contract. |
| Community framework integrations | Simplify | Publish verified base-URL recipes for OpenAI/Anthropic/Google/Vercel/LangChain-style clients; do not maintain wrappers for every framework. |
| App attribution/rankings headers | Reject | Marketplace ranking is not part of a private production request path. Accept and ignore harmless compatibility headers. |
| OAuth PKCE for third-party user-funded keys | Defer | Useful only when other apps ask their users to connect our billing. Seed customers create their own workspace keys. |
| Management API keys | Defer | Design a separate non-inference credential class; ship after REST management demand and rotation automation are proven. |
| Stripe Projects provisioning | Defer | Excellent distribution idea; first make `grad` and copyable env setup excellent, then evaluate catalog integration. |

### Core model behavior

| Capability | Decision | Our contract and rationale |
| --- | --- | --- |
| Tool/function calling | Keep | Required for agents. Preserve tool IDs/arguments, parallel calls, choice, and finish reasons only for models passing conformance. |
| Structured outputs/JSON Schema | Keep | Required for production automation. Reject an unsupported model before dispatch instead of silently degrading. |
| Reasoning controls/tokens | Keep | Normalize common effort levels and usage accounting; preserve encrypted/opaque reasoning where protocols support it, never invent chain-of-thought. |
| Common sampling parameters | Keep | Temperature, top-p, stop, max output, seed where supported, penalties/logprobs behind capability checks. |
| Provider-specific arbitrary parameters | Simplify | Pass only an explicitly tested namespaced allowlist. Unknown or lossy fields return a stable 400. |
| Silent ignoring of unsupported parameters | Reject | Smooth operation requires explicit errors, not apparently successful behavior changes. |
| Assistant prefill | Keep where native | Capability-gated per direct model or Grad effort/speed release; incompatible identities fail explicitly. |
| Stable typed errors and `Retry-After` | Keep | One cross-protocol error taxonomy translated into native envelopes. Preserve pre-stream versus mid-stream distinction. |
| Router/debug metadata in responses | Simplify | Safe request/route/version headers by default; detailed attempts and retained Product Intelligence traces are in authenticated Usage. No provider secrets or internal scores. |
| Generation feedback/reporting | Defer | Add thumbs up/down and failure labels after request logs exist; use only with explicit privacy rules to improve route evaluation. |

### Modalities and endpoint breadth

| Capability | Decision | Our contract and rationale |
| --- | --- | --- |
| Image understanding | Keep | URL and bounded base64 image input through supported Chat/Messages/Responses models. |
| Native PDF/file input | Simplify | Pass files only to models with proven native support. Do not silently send customer files through an undisclosed parser/plugin. |
| Embeddings | Keep | OpenAI-compatible `/v1/embeddings`, batching, model/capability validation, no streaming. Essential for RAG. |
| Image generation | Defer, high priority | Add after text/vision/embeddings are financially and operationally stable; requires object/result and pricing contracts. |
| Reranking | Defer, high priority | Useful for RAG but needs a dedicated endpoint and relevance conformance. |
| Audio input/understanding | Defer | Preserve schema extensibility; demand and large-body economics must justify it. |
| Speech-to-text | Defer | Dedicated endpoint later; not mixed into text launch. |
| Text-to-speech | Defer | Dedicated binary response, voices, storage and pricing need a separate packet. |
| Video understanding | Defer | Large upload, provider variance and cost make it a separate product gate. |
| Video generation/webhooks | Reject for seed | Asynchronous media jobs and object delivery are a distinct business surface. Reconsider only with direct demand. |
| Datasets/files APIs | Reject for seed | Customers retain their data and pass bounded request inputs. We do not become a data-hosting platform incidentally. |

### Catalog and model lifecycle

| Capability | Decision | Our contract and rationale |
| --- | --- | --- |
| Hundreds-of-model marketplace | Reject | Curate provider families and model versions. Direct migration breadth is earned by qualification, not automatic ingestion. |
| Models API with capabilities/pricing | Keep | Auth-filtered catalog includes concrete and managed models, modalities, context/output limits, prices, lifecycle, and compatibility. |
| Provider/endpoints directory | Operator-only | Provider endpoints, quantization, regions, measured health and buy cost feed route planning; ordinary customers see product guarantees. |
| Concrete model IDs | Keep | Support selected frontier/open models for customers who require model fidelity. |
| `latest` aliases | Simplify | Managed aliases evolve through versioned route releases/canaries/changelog. Concrete IDs remain the pinning mechanism. |
| Free model variants/router | Reject | Free availability is unreliable and attracts abuse. Offer bounded promotional credit, not a separate low-trust network. |
| Public rankings/benchmarks/classifications | Operator-only | Use evaluation data to curate routes; do not turn the product into a leaderboard. Publish concise qualification evidence. |
| Deprecation/migration guides | Keep | Lifecycle states, replacement recommendation, notice, compatibility tests, and request/log warnings are first-class. |
| Private models/BYOM endpoints | Defer enterprise | Architecture can add organization-restricted targets, but seed focuses on our supply plus selected providers. |

### Routing and provider behavior

| Capability | Decision | Our contract and rationale |
| --- | --- | --- |
| Automatic provider routing | Simplify | Direct IDs explicitly select provider/model. Grad IDs route only inside owned inference. Endpoint health routing remains automatic within that hard boundary. |
| Provider order/allowlist/ignore list | Defer advanced | Expose only when compliance or an enterprise contract requires it. It cannot weaken organization policy. |
| Same-model provider fallback | Keep | Retry qualified endpoints only on transient/connect/429/5xx failures before output, within one reservation. |
| Cross-model fallback list per request | Simplify | Managed aliases have tested semantic fallback sets. Pinned concrete models do not silently switch model families. Advanced versioned routes come later. |
| Fallback on context errors/moderation | Reject | Those are semantic/user-policy failures, not availability failures. Return an actionable error. |
| Auto Router | Replace with explicit lanes | Existing workloads select a direct provider/model; new owned workloads select effort/speed. Recommendations help customers choose but do not route invisibly. |
| Pareto coding router | Simplify into Grad qualification/recommendations | Coding/tool conformance can recommend a higher effort/speed cell; no separate router score parameter. |
| Nitro/speed variant | Keep as Grad speed dimension | `flex|standard|fast|turbo` is a first-class owned-serving SLO/price dimension, not a suffix mapped across providers. |
| Thinking variant | Simplify into standard `reasoning.effort` | Use protocol-native controls and capability validation. |
| Online variant/web search | Simplify into explicit web-search tool | Search has separate privacy/cost semantics and is never silently enabled by a suffix. |
| Extended-context variant | Simplify | Catalog reports context; route selects compatible endpoint. Reject oversize before cost when no eligible target exists. |
| Exacto/Auto Exacto tool-quality routing | Operator-only | Tool-call conformance and success rate are route-health inputs; customers simply receive reliable tool behavior. |
| Service tiers | Simplify | `standard` and `priority` only, each with published behavior and price. No provider tier vocabulary. |
| Session/provider stickiness | Keep | Direct traffic stays on its provider/model; `x-grad-session-id` stabilizes exact endpoints/releases while healthy. Grad stays in the selected effort/speed cell. |
| Prompt caching | Keep | Preserve provider-native caching automatically and report read/write units/savings. No extra configuration for common use. |
| Full response caching | Defer | Exact-response reuse is surprising and retains content. Later explicit opt-in with TTL, key/workspace isolation, ZDR conflict, and billing semantics. |
| Body Builder router | Reject | Natural-language generation of API calls is a docs/agent concern, not inference behavior. |
| Fusion multi-model router | Defer as separate product | Potentially valuable for high-stakes research, but cost, latency and citations need a dedicated product/SLO—not a hidden plugin. |
| Arbitrary route/preset DSL | Reject for default; defer advanced routes | Five managed models first. Later routes expose a bounded declarative policy and preview, not every provider knob. |
| Capacity/uptime/TTFT/throughput routing | Operator-only | Core reliability signals for owned and upstream targets, continuously measured and used by route releases/circuit breakers. |

### Organizations, billing, and administration

| Capability | Decision | Our contract and rationale |
| --- | --- | --- |
| Organization roles and unified billing | Keep | Organization is customer/credit/ledger boundary. |
| Default workspace | Keep but hide | Created atomically. No workspace picker/navigation until a second workspace exists. |
| Multiple workspaces/members | Keep via progressive disclosure | Needed for production/dev/team isolation, but absent from first-request setup. |
| Workspace API keys/system keys | Keep | Default creates one service key explicitly, displayed once; rotate/revoke/expiry are polished. |
| Daily/weekly/monthly/lifetime workspace budgets | Simplify | Default UI shows monthly cap and concurrency. Advanced drawer exposes other windows/key caps; all remain hard reservations. |
| Per-key credit limits | Keep | Optional cap/reset, never a separate balance. |
| Shared prepaid credits | Keep | PostgreSQL append-only organization ledger, Stripe top-ups and server-confirmed balance. |
| Automatic top-up | Defer until manual stability | Add with amount, threshold, monthly maximum, notification, idempotent webhook, and easy disable. |
| Postpaid/invoicing | Defer enterprise | Requires underwriting, contracts and finance operations. |
| Tax IDs/invoices/receipts | Keep basic | Stripe-hosted receipts and billing identity; jurisdictional expansion requires review. |
| Crypto funding | Reject | Adds compliance/fraud complexity without improving inference quality. |
| Activity/usage exports | Keep | Metadata CSV and REST export; no raw payload by default. |
| User tracking/custom request metadata | Simplify | Allow bounded opaque customer/user tags with privacy-safe indexing; never make arbitrary high-cardinality metrics labels. |

### Privacy, safety, and observability

| Capability | Decision | Our contract and rationale |
| --- | --- | --- |
| No gateway prompt/response retention by default | Replace | Product Intelligence retains bounded encrypted traces by default for customer features and migration recommendations. Private/No Retention is an explicit workspace/request option. |
| Provider training/data-policy filtering | Keep | Default deny training where endpoint policy is known; unknown policy is ineligible. |
| Strict zero-data-retention routing | Keep as opt-in | Private/No Retention workspace mode or stricter request header; may reduce eligible direct models and disables content-based recommendations. |
| Per-model-group ZDR switches | Simplify | Product Intelligence default or Private/No Retention. Request may tighten, never loosen. Provider training policy remains separate. |
| EU/sovereign in-region routing | Defer enterprise | Preserve region/data-residency fields; launch only after end-to-end provider/tool/storage proof. |
| Metadata activity/request logs | Keep | Model, actual route, timings, usage, price, cache, terminal state, request ID and safe diagnostics. |
| Private input/output logging | Keep as first-party trace product | Encrypted bounded traces, customer access/export/delete, explicit retention, credential stripping and separate object storage—not ordinary logs. |
| Broadcast to many observability vendors | Simplify | First-party logs first; then one OTLP exporter and signed webhook/S3 export. Customers can fan out from their collector. |
| Guardrail spend/model/provider restrictions | Simplify | These become budgets, curated model access and data policy—not a generic “guardrail” object. |
| Regex prompt-injection detection | Reject | High false confidence and app-specific semantics. Tool-owning applications must enforce trust boundaries. |
| PII detection/redaction | Defer specialized | Do not inspect content by default. Add only as explicit, separately retained/processed service with measured accuracy. |
| Custom regex content filters | Reject | Belongs in the customer's application or a dedicated safety product, not the core gateway path. |
| Custom classifiers | Simplify into workload intelligence | Workspace-local profiles and migration evaluators use retained traces for that customer. No cross-customer tracking or training without separate consent. |
| Provider moderation behavior | Keep as transparent constraint | Surface stable refusal/policy errors. Do not silently switch models to evade a policy refusal. |

### Plugins, hosted tools, and agent features

| Capability | Decision | Our contract and rationale |
| --- | --- | --- |
| Generic plugin marketplace/configuration | Reject | Increases hidden execution, billing, retention and support paths. |
| Web-search plugin | Defer as explicit server tool | Ship only with named provider, source/citation contract, separate price and privacy disclosure. |
| PDF parser plugin | Reject | Prefer native model file support; an external parser is a distinct data processor. |
| Response-healing plugin | Reject | Structured output conformance and explicit retry are more trustworthy than silent mutation. |
| Context-compression transform | Defer operator optimization | Never silently remove customer context. Any future compression is explicit and measured. |
| Message transforms/middle-out | Reject by default | Oversize requests return a clear error/recommendation; hidden truncation changes meaning. |
| Hosted bash/shell/files/apply-patch tools | Reject | High-risk execution is outside an inference gateway. |
| Hosted subagent/advisor/fusion tools | Defer product layer | May become separate managed agent/research products after gateway trust. |
| Hosted datetime/search-models helpers | Reject | Client-side utility, not a model call. |
| Agent loops, stop conditions, state persistence, approvals | Reject | Use established agent frameworks; keep our API stateless. |

### Reliability and commercial behavior

| Capability | Decision | Our contract and rationale |
| --- | --- | --- |
| Rate limits and capacity limits | Keep | Workspace/key limits plus route capacity. Return early typed 429 with `Retry-After`; never queue without bound. |
| Uptime-aware routing | Keep | Health/circuit breakers remove bad targets before customer impact; no per-customer setup. |
| Zero Completion Insurance | Simplify into failed-request credit | If no usable output is delivered, automatically reverse the customer sell charge; record/absorb or explicitly disclose provider input exposure under fraud controls. |
| Price/usage in every response | Keep | Exact units, fixed managed-product sell rate or concrete-model rate, cache/reasoning details, and request ID. |
| Provider buy price/marketplace markup | Operator-only | Customers see reproducible sell prices; internal margin does not leak into routing controls. |
| Model migration guides | Keep | Console warnings, replacement diff, compatibility test, deadline, and changelog. |

## Seed product surface

### Five screens

The default console has only:

1. **Overview** — balance, one quickstart, service health, recent requests.
2. **API keys** — create, copy once, rotate, revoke, expiry and optional cap.
3. **Models** — Grad effort × speed selector first; curated OpenAI/Anthropic/Google direct models second.
4. **Usage** — workload groups and retained traces, actual identity, latency/tokens/cost/cache/errors, migration evidence and export/delete.
5. **Billing** — top up, low-credit notification, history and receipts.

Members, workspaces, privacy, budgets and advanced routes live under Settings and appear in navigation only when configured. Provider names, weights, fallback arrays, quantization and health scores are not setup steps.

### Five-minute activation

```text
sign in
  -> organization + Default workspace created silently
  -> top up
  -> create key (Default workspace implicit)
  -> keep an unambiguous existing provider model or choose grad/medium/standard
  -> successful request and encrypted trace in Product Intelligence mode
  -> exact charge/workload appears in Usage; Grad recommendation follows only with evidence
```

The UI detects the first request and advances onboarding automatically. It never asks the user to choose a provider, routing strategy, guardrail, workspace, region, or observability integration before success.

## Managed routing contract

### Request resolution

```text
protocol parse + capability/data requirements
  -> resolve canonical direct provider/model or Grad effort/speed
  -> apply organization/workspace model + data policy
  -> resolve immutable same-lane RouteRelease and eligible TargetSet
  -> pin session/canary deterministically
  -> calculate worst-case fixed customer sell reserve
  -> atomic billing/limit admission in Redis
  -> choose healthy exact-provider target or owned Grad target
  -> retry only safe pre-output transient failures
  -> settle fixed sell price from customer-billable units and expose actual route
```

For a direct model, targets may vary only inside the exact named provider/model/version and must pass identity/conformance. For a Grad product, every target is owned inference qualified for the exact effort/speed cell. Neither lane silently crosses its identity boundary.

### Owned inference selection

Our endpoint is selected only for a canonical Grad product/checkpoint and when all are true:

- it serves the exact Grad checkpoint or effort/speed release;
- its capability/quality/tool/structured-output conformance passes;
- privacy, region, context, service tier and capacity match;
- measured health/TTFT/throughput are inside the product envelope;
- expected buy cost keeps the fixed-price route within margin guardrails.

An operator cannot force owned inference for a direct provider/model request. Customers move through an evidence-backed recommendation and explicit experiment/switch, preventing our margin goal from becoming an undisclosed quality downgrade.

### Release and rollback

Every direct model and Grad effort/speed product resolves to an immutable `route_release_id` containing hard identity, targets, capabilities, fixed sell prices, max attempt exposure, data constraints, quality/SLO evidence and rollout policy. Grad releases progress internal -> staging -> opted-in organizations -> deterministic canary -> default. Rollback points to the prior release; usage retains the original release ID forever.

## Evidence sources

All sources are official OpenRouter pages, live without a displayed revision date unless noted. Retrieval was 2026-07-13.

| Area | Source | Evidence |
| --- | --- | --- |
| Complete docs inventory | [Documentation index](https://openrouter.ai/docs/llms.txt) | Vendor-reported list of product/API/SDK/cookbook pages. |
| API/protocol surface | [API overview](https://openrouter.ai/docs/api/reference/overview), [parameters](https://openrouter.ai/docs/api/reference/parameters), [streaming](https://openrouter.ai/docs/api/reference/streaming), [errors](https://openrouter.ai/docs/api/reference/errors-and-debugging) | Vendor-reported protocols, parameters and failure behavior. |
| Responses and embeddings | [Responses beta](https://openrouter.ai/docs/api/reference/responses/overview), [embeddings](https://openrouter.ai/docs/api/reference/embeddings) | Vendor-reported; Responses explicitly beta/stateless. |
| Modalities | [Multimodal overview](https://openrouter.ai/docs/guides/overview/multimodal/overview) | Vendor-reported image, PDF, audio, video, speech and generation surface. |
| Models | [Models](https://openrouter.ai/docs/guides/overview/models) | Vendor-reported catalog/filter/capability behavior. |
| Provider/model routing | [Provider selection](https://openrouter.ai/docs/guides/routing/provider-selection), [fallbacks](https://openrouter.ai/docs/guides/routing/model-fallbacks), [auto router](https://openrouter.ai/docs/guides/routing/routers/auto-router), [latest resolution](https://openrouter.ai/docs/guides/routing/routers/latest-resolution) | Vendor-reported routing controls. |
| Specialized routers | [Pareto](https://openrouter.ai/docs/guides/routing/routers/pareto-router), [Body Builder](https://openrouter.ai/docs/guides/routing/routers/body-builder), [Fusion](https://openrouter.ai/docs/guides/routing/routers/fusion-router), [Auto Exacto](https://openrouter.ai/docs/guides/routing/auto-exacto) | Vendor-reported specialized products. |
| Model/provider operations | [Provider integration](https://openrouter.ai/docs/guides/community/for-providers), [uptime](https://openrouter.ai/docs/guides/best-practices/uptime-optimization), [router metadata](https://openrouter.ai/docs/guides/features/router-metadata) | Vendor-reported provider feed, monitoring, performance and metadata. |
| Organization/admin | [Workspaces](https://openrouter.ai/docs/guides/features/workspaces/overview), [budgets](https://openrouter.ai/docs/guides/features/workspaces/workspace-budgets), [management keys](https://openrouter.ai/docs/guides/overview/auth/management-api-keys), [OAuth](https://openrouter.ai/docs/guides/overview/auth/oauth), [BYOK](https://openrouter.ai/docs/guides/overview/auth/byok) | Vendor-reported hierarchy and credential controls. |
| Privacy and safety | [ZDR](https://openrouter.ai/docs/guides/features/zdr), [data collection](https://openrouter.ai/docs/guides/privacy/data-collection), [provider logging](https://openrouter.ai/docs/guides/privacy/provider-logging), [guardrails](https://openrouter.ai/docs/guides/features/guardrails/overview) | Vendor-reported privacy/policy controls. |
| Configuration/extensions | [Presets](https://openrouter.ai/docs/guides/features/presets), [plugins](https://openrouter.ai/docs/guides/features/plugins), [tool calling](https://openrouter.ai/docs/guides/features/tool-calling), [structured output](https://openrouter.ai/docs/guides/features/structured-outputs) | Vendor-reported configuration and extension surface. |
| Caching/reliability | [Prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching), [response caching](https://openrouter.ai/docs/guides/features/response-caching), [zero completion insurance](https://openrouter.ai/docs/guides/features/zero-completion-insurance) | Vendor-reported cache/commercial behavior. |
| Observability | [Input/output logging](https://openrouter.ai/docs/guides/features/input-output-logging), [Broadcast](https://openrouter.ai/docs/guides/features/broadcast), [usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting), [activity export](https://openrouter.ai/docs/cookbook/administration/activity-export) | Vendor-reported telemetry/export surface. |
| Distribution | [Provider integration](https://openrouter.ai/docs/guides/community/for-providers), [Stripe Projects](https://openrouter.ai/docs/guides/overview/stripe-projects) | Vendor-reported onboarding/distribution requirements. |

## Uncertainty and falsifiers

- Public docs changed substantially since the earlier spike and may change again; implementation rechecks the index and source pages.
- Authenticated dashboard polish, adoption, customer demand and commercial terms were not observed. Feature presence is not evidence of value.
- The four effort and four speed labels are unmeasured hypotheses. They are falsified if customers cannot choose them or measured cells lack meaningful quality/latency monotonicity.
- Product Intelligence retention is falsified as a default if it materially harms activation/trust or cannot meet deletion/security obligations; Private/No Retention remains the safe alternative.
- The curated catalog is falsified if retained customers repeatedly need qualified models we excluded; add models through the same qualification gate, not by opening an unbounded marketplace.
- Failed-request credits are falsified if abuse/provider input cost makes them economically unsafe; add bounded eligibility rather than silently charging broken output.

## Next evidence

Before implementation hardens the route set, qualify each direct provider/model and run representative text, tool, structured-output, reasoning, code and vision evaluations across Grad effort/speed cells. Measure quality, protocol fidelity, TTFT, throughput, queueing, availability, cache behavior, trace/recommendation safety, reserve utilization and contribution margin. No provider model or Grad cell enters the catalog without source-dated, scope-matched evidence.
