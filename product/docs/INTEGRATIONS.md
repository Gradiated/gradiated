# Gateway and provider integrations

There are two distinct integration directions. Keep them separate in code, credentials, economics, and metrics. The complete target, package, harness and delivery decision is in [Open distribution and gateway integration plan](DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md).

- Curated model-provider adapter: a customer explicitly requests a tested model provider/model from our short registry; we buy that exact inference and preserve identity.
- Distribution channel: OpenRouter or another gateway sends traffic to our owned/differentiated inference and pays us for capacity.
- Capacity-provider adapter: an operator-only fleet reconciler acquires GPU infrastructure for Grad-owned inference; this is not a customer model-provider option.

Both use the same Rust protocol, routing, metering, and serving core. An external-gateway listing must never bypass our request identity, provider-side limits, metering, or reconciliation.

There are two materially different ways traffic can arrive through another gateway:

- **Customer-configured gateway:** the customer points LiteLLM, Cloudflare, Portkey, Helicone, Kong, or another compatible proxy at Grad using their workspace key. This is ordinary prepaid organization traffic and follows that workspace's model/data/trace/limit policy.
- **Native distribution listing:** OpenRouter, Hugging Face, or another approved marketplace calls Grad with a dedicated channel credential. This uses channel exposure/receivable accounting and the channel privacy/catalog profile; it never mutates a customer organization credit pool or creates first-party Product Intelligence traces.

Credential lookup selects the principal and profile. A caller cannot select channel billing, a customer organization, or a catalog view with headers or request-body fields.

## Upstream adapters

### Adapter contract

Each Rust adapter declares:

- supported ingress protocols, fields, modalities, tools, structured output, and streaming events;
- provider request translation and credential/header construction;
- retryable status/transport classes and whether an attempt can be safely replayed;
- usage extraction, local estimation fallback, and evidence class;
- cancellation semantics and whether partial usage remains billable;
- provider request ID, latency, error normalization, and cost evidence;
- bounded customer sell exposure used by reservation calculation and a separate internal provider buy/attempt exposure used by route margin/risk gates.
- exact concrete model/version, endpoint region/runtime/quantization, retention/training/ZDR policy, prompt-cache behavior, and qualification-evidence version;
- Responses, embeddings, image/native-file input and reasoning support independently rather than inheriting them from Chat compatibility.
- canonical provider/model IDs, unique bare aliases, native service tiers, training/retention policy and whether Private/No Retention is eligible.

Never declare a capability based only on a generic compatibility label. Add fixtures for each supported field and fail explicitly when translation would be lossy.

### Initial targets

1. Deterministic fake OpenAI, Anthropic, Google, owned, and generic servers for all faults and PR tests.
2. Owned inference for every canonical `grad/<effort>/<speed>` release and exposed Grad checkpoints.
3. OpenAI direct under `openai/` for selected qualified models.
4. Anthropic direct under `anthropic/` with first-class Messages semantics for selected qualified models.
5. Google Gemini direct under `google/`, qualifying native and OpenAI-compatible behavior separately.
6. OpenRouter/generic-compatible upstream only as operator contingency/benchmark infrastructure, never customer-selectable breadth.

Direct traffic is not an automatic route: `openai/x`, `anthropic/y`, or `google/z` remains on that provider/model/version. We expose a bare upstream ID only while its registry binding is unique. Failed attempts never justify cross-provider fallback. Native service tiers are explicit model capabilities and are not mapped to Grad speed labels.

OpenRouter upstream does not appear in customer setup. If enabled by operators, its charge is our buy cost while the admitted price/reservation remains authoritative, and it cannot satisfy a canonical direct-provider pin unless the contract still proves that exact provider/model identity. We do not route frontier traffic through OpenRouter merely to resell marketplace breadth.

## Official-client compatibility

The Grad endpoint is independently usable as an OpenAI-compatible provider; third-party distribution is additive, not required. The conformance suite instantiates official OpenAI, Anthropic, and Google SDKs with base URL pointed to the Rust gateway. It covers canonical/bare model identity, native skins, Product Intelligence/no-retain behavior, fake providers on every `main` commit and external pull request, and real providers in protected CI as specified in [Testing and CI](TESTING_AND_CI.md).

The OpenAI-compatible seed baseline is bearer authentication plus `GET /v1/models`, `POST /v1/chat/completions`, a qualified stateless `POST /v1/responses` subset, and qualified `POST /v1/embeddings`. Standard clients require only the base URL/key; Grad headers are optional. Public JSON/SSE compatibility is fixture-governed, including usage, tools, structured output, finish reasons, cancellation, UTF-8 chunking, early 429 and midstream errors. OpenAI's published `gpt-oss` compatibility test is pinned as an additional tool/API-shape smoke, not a claim of exhaustive OpenAI parity.

Model IDs for paid smoke are environment-pinned because catalogs change. At each monthly review, verify from current official model/pricing documentation that the selected model supports the tested endpoint/streaming mode and remains the cheapest reasonable choice. The job's token and dollar preflight is the hard guardrail.

## OpenRouter provider path

OpenRouter's current provider documentation asks prospective providers to apply and defines a model-list contract including ID/Hugging Face identity, name, input/output modalities, quantization, context/max-output length, pricing, supported parameters/features, lifecycle/readiness/free/discount flags, capacity and data-center metadata. It describes auto top-up or invoicing for commercial settlement and exposes measured uptime, time-to-first-token and throughput. After sufficient traffic, vendor-reported routing tiers are at least 95% uptime for normal routing, 80–94% as degraded, and below 80% as fallback-only; 429 capacity responses are tracked separately, while many auth/server/midstream failures count against uptime. It recommends early explicit 429s and stream keepalive comments. These requirements are time-sensitive and must be revalidated before onboarding: [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers).

Only owned or contractually differentiated inference is eligible for our OpenRouter provider catalog. Re-exporting OpenAI/Anthropic/OpenRouter supply creates no differentiation and risks circular economics. Distribution-channel requests use dedicated credentials, Redis `ChannelAccountProjection` admission, receivable/payout accounting, price books, capacity/concurrency limits, cache trust domains, and SLOs; they never reserve against a customer organization credit pool even though they share protocol, exact-release routing, metering and inference code. PostgreSQL is authoritative for channel contracts/receivables; reconciliation joins downstream request IDs to immutable Grad usage and closes new admission on exposure, aging, or drift.

OpenRouter calls the public Grad Rust gateway, not the inference edge or GPU cells. OpenRouter validates and bills its own end-user token; it presents a Grad-issued, rotatable OpenRouter channel credential to us. The Grad gateway validates that channel principal from Redis, performs provider-side exposure/model/capacity/rate/concurrency admission, routes the exact release through the private AWS inference edge, meters/streams the response, and emits the channel receivable event. No OpenRouter end-user token or channel secret reaches an inference cell, and the user need not have a Grad organization.

The OpenRouter provider catalog may expose selected Grad effort/speed products or concrete owned checkpoints only when their naming/capability contract fits OpenRouter's current model-list requirements. External marketplace traffic does not create first-party customer traces or migration recommendations; its data handling follows the downstream contract.

### Compatibility spike deliverables

Build these before submitting any application:

- provider-facing model-list view/credential with OpenRouter-required metadata sourced from immutable model/price/capacity/qualification config and isolated from the direct-customer catalog;
- OpenAI-compatible Chat Completions stream with tools, usage, finish reasons, cancellation, auth errors, 429 capacity, and model-not-found behavior;
- Auto Exacto-relevant tool-call conformance evidence for any claimed tool-capable model, without optimizing away protocol correctness;
- capacity and maintenance controls that distinguish temporary rate limit from server failure;
- early 429/load-shed, keepalive and midstream-error behavior that protects measured uptime without accepting work the backend cannot finish;
- synthetic monitor proving uptime/TTFT/throughput/error metrics without request payload retention;
- settlement export that reconciles OpenRouter request IDs/units/revenue to our usage records;
- a compatibility matrix and captured fixtures for every claimed sampling parameter/feature;
- load/soak result against the published uptime and performance expectations;
- unit economics at expected external price, capacity utilization, and support burden.

### Spike decision gate

Proceed to a human-approved application only if:

- the model/supply is differentiated enough to be accepted and attract traffic;
- 24-hour staging soak has no protocol/accounting mismatch and meets our stricter reliability target;
- price produces positive contribution margin at realistic capacity and retries;
- provider-facing traffic cannot consume direct-customer organization credit pools or mix credentials;
- listed supply is owned/differentiated and does not create circular marketplace routing;
- legal/privacy/terms and payout/tax handling have an owner.

Application submission, accepting terms, publishing a model, or sending credentials requires a human checkpoint. The code/evidence spike does not authorize those external actions.

## Other gateway distribution paths

Prioritize configurable customer-side integrations before formal marketplace partnerships. These recipes forward a customer workspace key and therefore stay on prepaid organization accounting:

| Path | Seed integration | Evidence to produce | Priority |
| --- | --- | --- | --- |
| Cloudflare AI Gateway | Document a custom-provider/base-URL route to our OpenAI-compatible endpoint. | Tested config, auth/header handling, stream/tool matrix, safe logs. Cloudflare documents custom HTTPS providers: [custom providers](https://developers.cloudflare.com/ai-gateway/configuration/custom-providers/). | High |
| LiteLLM Proxy | Publish a tested custom/OpenAI-compatible model config. | Config fixture, stream/tool/usage behavior, error matrix. | High |
| Portkey | Publish base-URL/custom-provider configuration. | Config fixture, virtual-key/header behavior, usage/error matrix. | Medium |
| Kong AI Gateway | Validate an OpenAI-compatible route and plugin transformations. | Declarative config and protocol fixture results. | Medium |
| Helicone | Publish `Helicone-Target-Url` configuration first; contribute a native OSS provider after demand. | Header/auth forwarding, unknown-domain limits, stream/tool/usage/error matrix; native registry tests. | High |
| Vercel AI SDK | Offer `@ai-sdk/openai-compatible` configuration, then a thin `@grad/ai-sdk-provider`. | Example/package tests, not an assumed Vercel AI Gateway marketplace listing. | High |
| Enterprise gateways | Generic base URL plus OpenAPI and capability profile. | Customer-specific conformance packet. | Demand-driven |

Do not claim a formal provider program unless official documentation and a contact path confirm it. A working custom endpoint configuration is still valuable distribution and can be shipped without platform partnership.

OpenRouter is the first native listing target. Hugging Face Inference Providers is the second: its current registration guide documents an OSS `huggingface.js` provider helper/registration, partner model mappings, staging/live state and automated endpoint/tool/structured-output validation. Vercel AI Gateway and cloud model marketplaces remain contact/evidence-gated because the reviewed public docs do not establish a self-service provider listing path.

The shared harness uses official OpenAI TypeScript/Python/Go clients; `ai` plus `@ai-sdk/openai-compatible`; a pinned LiteLLM proxy; Vitest/fast-check/Testcontainers; pytest/Hypothesis/httpx/respx; and reqwest/wiremock/proptest in Rust. OpenRouter SDKs and `@openrouter/ai-sdk-provider` are post-listing black-box test dependencies, not production gateway dependencies. Package and harness ownership is frozen in the dated distribution plan.

## Integration test matrix

For each direction/target record:

| Dimension | Required cases |
| --- | --- |
| Authentication | valid, invalid, revoked, rotated, no credential leakage. |
| Identity | canonical provider/model, unique/ambiguous bare alias, provider header match, same-provider retry, prohibited cross-provider/version fallback. |
| Protocol | stream/non-stream, tools, structured output, supported modalities, unknown fields. |
| Product route | direct provider pin vs Grad effort/speed release, deterministic canary/session pin, actual identity disclosure, speed-capacity failure and rollback. |
| Limits | 400/401/402/403/404/413/429/5xx, body/output/context/capacity. |
| Streaming | event ordering, usage, finish reason, UTF-8 splits, malformed chunk, midstream close, cancel. |
| Retry | connect failure, pre-byte 5xx, rate limit, no retry after exposed output, bounded internal buy exposure, failed-attempt units never sold to customer. |
| Metering | provider-reported, local measured, estimated, missing usage, duplicate event. |
| Economics | buy cost, sell amount, retries, external payout, gross margin. |
| Privacy | payload/log policy, retention, region, external terms. |
| Traces | Product Intelligence capture, no-retain suppression, credential stripping and provider-specific policy disclosure. |
| Qualification | exact model/endpoint/runtime scope, capability evidence expiry, owned-target parity, release gate. |

Fixtures are versioned with provider/document date. Live canaries are vendor-dependent measurements and are not generalized beyond tested model, endpoint, region, and date.

## Evidence sources

- [Hono supports native web Request/Response and runtime adapters](https://hono.dev/docs/getting-started/basic).
- [tRPC fetch adapter consumes native Request and returns Response](https://trpc.io/docs/server/adapters/fetch).
- [shadcn/ui Vite installation](https://ui.shadcn.com/docs/installation/vite).
- [OpenRouter API reference](https://openrouter.ai/docs/api/reference/overview).
- [OpenRouter complete documentation index](https://openrouter.ai/docs/llms.txt).
- [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers).
- [Open distribution and gateway integration plan](DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md).
- [OpenAI gpt-oss implementation verification](https://developers.openai.com/cookbook/articles/gpt-oss/verifying-implementations#quick-verification-of-tool-calling-and-api-shapes).
- [Hugging Face provider registration](https://huggingface.co/docs/inference-providers/en/register-as-a-provider).
- [Vercel AI SDK OpenAI-compatible providers](https://ai-sdk.dev/providers/openai-compatible-providers).
- [Helicone provider integration](https://docs.helicone.ai/references/provider-integration).
- [OpenAI official TypeScript SDK](https://github.com/openai/openai-node).
- [Anthropic official TypeScript SDK](https://github.com/anthropics/anthropic-sdk-typescript).
- [Google gateway/partner integration guidance](https://ai.google.dev/gemini-api/docs/partner-integration).
- [OpenAI model catalog](https://developers.openai.com/api/docs/models/gpt).
- [Anthropic model selection](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model).

Vendor docs are volatile. Reverify before implementing model IDs, pricing, or onboarding forms.
