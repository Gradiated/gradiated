# Gateway and provider integrations

There are two distinct integration directions. Keep them separate in code, credentials, economics, and metrics.

- Upstream adapter: our gateway buys inference from OpenAI, Anthropic, OpenRouter, or another provider for our direct customers.
- Downstream provider: OpenRouter or another gateway sends customer traffic to our endpoint and pays us for our model capacity.

Both use the same Rust protocol, routing, metering, and serving core. An external-gateway listing must never bypass our request identity, provider-side limits, metering, or reconciliation.

## Upstream adapters

### Adapter contract

Each Rust adapter declares:

- supported ingress protocols, fields, modalities, tools, structured output, and streaming events;
- provider request translation and credential/header construction;
- retryable status/transport classes and whether an attempt can be safely replayed;
- usage extraction, local estimation fallback, and evidence class;
- cancellation semantics and whether partial usage remains billable;
- provider request ID, latency, error normalization, and cost evidence;
- bounded maximum exposure used by reservation calculation.

Never declare a capability based only on a generic compatibility label. Add fixtures for each supported field and fail explicitly when translation would be lossy.

### Initial targets

1. Deterministic fake OpenAI and Anthropic servers for all faults and PR tests.
2. Owned inference target—the strategic supply and highest-priority path when available.
3. OpenAI direct and Anthropic direct for client/gateway validation and selected fallback.
4. OpenRouter upstream through its OpenAI-compatible endpoint for early catalog breadth.
5. Generic OpenAI-compatible target configured by tested capability profile, not optimistic passthrough.

OpenRouter upstream must preserve its provider/routing options only when intentionally exposed and priced. Its customer charge is our upstream buy cost; our organization-funded, workspace-attributed sell price and reservation remain authoritative.

## Official-client compatibility

The conformance suite instantiates the official OpenAI and Anthropic TypeScript SDKs with base URL pointed to the Rust gateway. That validates the customer experience rather than only raw HTTP fixtures. It covers fake providers on every pull request and real providers in protected CI as specified in [Testing and CI](TESTING_AND_CI.md).

Model IDs for paid smoke are environment-pinned because catalogs change. At each monthly review, verify from current official model/pricing documentation that the selected model supports the tested endpoint/streaming mode and remains the cheapest reasonable choice. The job's token and dollar preflight is the hard guardrail.

## OpenRouter provider path

OpenRouter's current provider documentation asks prospective providers to apply and publishes a provider model-list shape with exact IDs, capabilities, pricing strings, readiness, capacity, and data-center metadata. It also reports that normal routing begins at 95%+ measured uptime after sufficient traffic; 429s are tracked separately, while many auth/server/midstream errors count against uptime. These are vendor-reported requirements and must be revalidated before onboarding: [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers).

### Compatibility spike deliverables

Build these before submitting any application:

- provider-facing `/v1/models` view with OpenRouter-required metadata sourced from immutable model/price/capacity config;
- OpenAI-compatible Chat Completions stream with tools, usage, finish reasons, cancellation, auth errors, 429 capacity, and model-not-found behavior;
- capacity and maintenance controls that distinguish temporary rate limit from server failure;
- synthetic monitor proving TTFT/throughput/error metrics without request payload retention;
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
- legal/privacy/terms and payout/tax handling have an owner.

Application submission, accepting terms, publishing a model, or sending credentials requires a human checkpoint. The code/evidence spike does not authorize those external actions.

## Other gateway distribution paths

Prioritize configurable customer-side integrations before formal marketplace partnerships:

| Path | Seed integration | Evidence to produce | Priority |
| --- | --- | --- | --- |
| Cloudflare AI Gateway | Document a custom-provider/base-URL route to our OpenAI-compatible endpoint. | Tested config, auth/header handling, stream/tool matrix, safe logs. Cloudflare documents custom HTTPS providers: [custom providers](https://developers.cloudflare.com/ai-gateway/configuration/custom-providers/). | High |
| LiteLLM Proxy | Publish a tested custom/OpenAI-compatible model config. | Config fixture, stream/tool/usage behavior, error matrix. | High |
| Portkey | Publish base-URL/custom-provider configuration. | Config fixture, virtual-key/header behavior, usage/error matrix. | Medium |
| Kong AI Gateway | Validate an OpenAI-compatible route and plugin transformations. | Declarative config and protocol fixture results. | Medium |
| Vercel AI SDK | Offer an OpenAI-compatible provider configuration for application clients. | Example package/test, not an assumed marketplace listing. | Medium |
| Enterprise gateways | Generic base URL plus OpenAPI and capability profile. | Customer-specific conformance packet. | Demand-driven |

Do not claim a formal provider program unless official documentation and a contact path confirm it. A working custom endpoint configuration is still valuable distribution and can be shipped without platform partnership.

## Integration test matrix

For each direction/target record:

| Dimension | Required cases |
| --- | --- |
| Authentication | valid, invalid, revoked, rotated, no credential leakage. |
| Protocol | stream/non-stream, tools, structured output, supported modalities, unknown fields. |
| Limits | 400/401/402/403/404/413/429/5xx, body/output/context/capacity. |
| Streaming | event ordering, usage, finish reason, UTF-8 splits, malformed chunk, midstream close, cancel. |
| Retry | connect failure, pre-byte 5xx, rate limit, no retry after exposed output, bounded exposure. |
| Metering | provider-reported, local measured, estimated, missing usage, duplicate event. |
| Economics | buy cost, sell amount, retries, external payout, gross margin. |
| Privacy | payload/log policy, retention, region, external terms. |

Fixtures are versioned with provider/document date. Live canaries are vendor-dependent measurements and are not generalized beyond tested model, endpoint, region, and date.

## Evidence sources

- [Hono supports native web Request/Response and runtime adapters](https://hono.dev/docs/getting-started/basic).
- [tRPC fetch adapter consumes native Request and returns Response](https://trpc.io/docs/server/adapters/fetch).
- [shadcn/ui Vite installation](https://ui.shadcn.com/docs/installation/vite).
- [OpenRouter API reference](https://openrouter.ai/docs/api/reference/overview).
- [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers).
- [OpenAI official TypeScript SDK](https://github.com/openai/openai-node).
- [Anthropic official TypeScript SDK](https://github.com/anthropics/anthropic-sdk-typescript).
- [OpenAI model catalog](https://developers.openai.com/api/docs/models/gpt).
- [Anthropic model selection](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model).

Vendor docs are volatile. Reverify before implementing model IDs, pricing, or onboarding forms.
