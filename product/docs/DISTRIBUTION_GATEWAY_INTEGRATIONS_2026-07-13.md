# Open distribution and gateway integration plan

- status: accepted product/architecture plan; implementation and partner onboarding not started
- evidence cutoff: 2026-07-13
- issue: https://github.com/joshsny/gradiated/issues/9
- scope: direct Grad inference, customer-configured gateways, native router/provider listings, compatibility packages and verification harnesses

## Decision

Grad inference is an independent OpenAI-compatible provider. Customers are never required to use Grad's console as their only router and are never required to buy through Grad's first-party gateway experience.

One public Rust serving surface supports three distribution modes:

1. **Direct Grad API.** A customer creates a Grad organization/workspace key, points an OpenAI-compatible client at `GRAD_OPENAI_BASE_URL`, and prepays the organization's credit pool.
2. **Customer-configured gateway.** A customer stores that same workspace key in LiteLLM, Cloudflare AI Gateway, Portkey, Helicone, Kong, or another compatible gateway. This remains first-party, prepaid organization traffic even though another gateway proxies it.
3. **Native distribution listing.** OpenRouter, Hugging Face, or another approved marketplace authenticates with a dedicated channel credential and resells/routs selected Grad-owned inference. This is distribution-channel receivable traffic, not customer organization credit.

The modes share public protocol parsing, exact-release routing, owned inference, metering and request IDs. They do not share principals, balance domains, privacy defaults, catalog views, price books, quotas or settlement state.

The seed order is direct endpoint plus customer-configured gateway recipes first, OpenRouter conformance/application next, then Hugging Face provider registration. Native listings are additive distribution and cannot block direct launch.

## Product promise

The adoption path should be as small as this:

```ts
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.GRAD_API_KEY,
  baseURL: process.env.GRAD_OPENAI_BASE_URL,
});

const result = await client.chat.completions.create({
  model: "grad/medium/standard",
  messages: [{ role: "user", content: "Hello" }],
});
```

`GRAD_OPENAI_BASE_URL` includes `/v1`; its production hostname is a deployment/DNS decision and must not be hard-coded in generated clients or fixtures. Baseline use requires only the standard bearer credential and standard OpenAI request fields. `x-grad-*` headers are optional enhancements, never required for ordinary Chat Completions, Responses, Embeddings, models, streaming, tools or structured output.

We do not publish a required proprietary inference SDK at seed. We publish copyable configurations, an optional thin Vercel AI SDK provider package, OpenAPI/JSON Schema, and conformance results.

## Architecture

```text
OpenAI clients / AI frameworks
             │ direct workspace key
             ├─────────────────────────────────────────────┐
             │                                             │
Customer gateway                                           │
LiteLLM / Cloudflare / Portkey / Helicone / Kong           │
             │ forwards customer workspace key             │
             └─────────────────────────────────────────────┤
                                                           v
OpenRouter / Hugging Face ── dedicated channel key ──> public Grad ingress
                                                           │
                                                           ├─ credential -> principal/profile
                                                           ├─ OpenAI JSON/SSE validation
                                                           ├─ Redis admission and route release
                                                           ├─ immutable usage/request identity
                                                           v
                                                  AWS inference edge
                                                           │
                                             exact signed Grad release target
                                                           v
                                            external GPU inference cells

Customer workspace principal -> organization prepaid reservation/settlement
Distribution principal       -> channel exposure/receivable reconciliation
```

There is no separate model runtime, inference cluster or second gateway implementation per router. A small **distribution profile** selected from the authenticated credential controls catalog projection, accepted paths, channel price book, quotas, privacy and response metadata. It cannot change the exact runtime semantics of a release.

The public edge is still the existing Rust gateway. Hono is not on the inference request path. PostgreSQL remains authoritative, but the gateway reads only Redis synchronously for internal auth/config/admission state. Channel and organization events drain independently to PostgreSQL reconciliation workers.

### Exact OpenRouter request path

OpenRouter traffic always enters the public Grad Rust gateway. OpenRouter must never receive or call an AWS inference-edge URL, cell URL, GPU runtime, Kubernetes service or provider-native allocation directly.

```text
End user
  -> OpenRouter API with OpenRouter user key
  -> OpenRouter validates its user/key/credits and selects Grad as provider
  -> OpenRouter sends OpenAI-compatible request to GRAD_OPENAI_BASE_URL
       Authorization: Bearer <dedicated Grad-issued OpenRouter channel secret>
  -> Grad gateway validates channel credential from Redis
  -> atomic channel exposure + model/capability + rate/concurrency/capacity admission
  -> exact approved Grad release through AWS inference edge
  -> private signed/mTLS cell request; no OpenRouter or end-user secret reaches cell
  -> Grad gateway meters and streams OpenAI-compatible response to OpenRouter
  -> OpenRouter streams to and bills its user
  -> Grad channel event reconciles request/usage/receivable with OpenRouter settlement
```

This is hop-by-hop authentication. OpenRouter owns validation and billing of the OpenRouter end user. Grad validates only the Grad-issued channel credential presented by OpenRouter; it does not receive, introspect or trust the end user's OpenRouter API key and does not require that user to have a Grad organization. Any forwarded end-user ID is optional, bounded, privacy-reviewed, non-authoritative abuse/correlation metadata—not an authentication or billing principal.

The channel credential should be a rotatable scoped bearer secret unless the partner supports a stronger mutually agreed mechanism. Its digest/version/status and `DistributionChannelPrincipal` are projected from PostgreSQL into Redis. It authorizes only the agreed catalog and inference paths. It cannot call tRPC, list customer workspaces, spend organization credit, request arbitrary models, select an upstream URL or bypass gateway admission. If Redis cannot prove the credential and reserve channel exposure, the gateway fails closed before inference.

OpenRouter may already have checked its own balance, but Grad must still admit every request. Our admission protects unpaid/aged receivable exposure, contract/model allowlists, release readiness, regional capacity, RPM/TPM/concurrency, request bounds and abuse. These checks are not duplicated end-user billing; they are the provider-side safety boundary. Raw inference cells trust only the AWS inference edge's short-lived signed identity and exact release target, never a public or channel API key.

## Public provider contract

### Seed surface

| Method | Path | Distribution contract |
| --- | --- | --- |
| `GET` | `/v1/models` | OpenAI-compatible list for direct/customer-key policy. A channel credential receives its approved channel catalog projection. |
| `POST` | `/v1/chat/completions` | Universal seed baseline: stream/non-stream, tools, structured output, usage and stable finish/error behavior. |
| `POST` | `/v1/responses` | Stateless qualified subset. Advertise per model/profile only after client and router conformance. |
| `POST` | `/v1/embeddings` | Qualified models only; not inferred from Chat support. |
| `GET` | `/healthz` | Liveness; not a substitute for channel model/readiness monitoring. |

Anthropic Messages and Google native skins remain available to direct customers, but OpenAI Chat Completions is the common denominator for third-party distribution. A channel may gain another skin only after that channel documents and passes it.

### Compatibility rules

- Accept `Authorization: Bearer <key>` and standard JSON content types. Do not require a customer to put a Grad key in a nonstandard header.
- Preserve model IDs containing `/` in JSON bodies. Customer-gateway fixtures must catch path join, URL encoding and accidental prefix stripping.
- Return OpenAI-compatible response objects and SSE data events. Stream termination, usage, tool calls, finish reasons, UTF-8 boundaries, cancellation and midstream errors are fixture-governed.
- Send an externally safe `x-request-id`; accept a bounded upstream request ID/idempotency key only under the published deduplication contract. Never trust a channel-supplied organization/workspace/channel ID.
- Return explicit `400`, `401`, `402`, `403`, `404`, `413`, `429` and `5xx` classes. Do not turn admission failures into empty `200` responses.
- Emit an early `429` before model work when capacity is unavailable. Do not admit a request merely to improve an availability numerator.
- SSE comments may be used as transport keepalives, but never as fake output or proof of backend progress.
- Public model/card claims are capability gated. Chat compatibility does not imply Responses, embeddings, images, tools, structured output or a context length.
- Unknown unsupported fields fail explicitly instead of being dropped. Optional Grad metadata is namespaced and cannot alter the standard core.

OpenAI publishes OpenAPI endpoint schemas for Chat Completions, Responses, Embeddings and Models. We snapshot the supported subset into `product/schemas/` with a recorded upstream version/date; we do not claim exhaustive parity with unrelated OpenAI services. OpenAI also publishes a `gpt-oss` compatibility test for Responses/Chat tool calling and API shape. That upstream test is pinned and run as one smoke layer, not treated as proof of full compatibility.

## Principals, money and privacy

| Property | Direct Grad or customer-configured gateway | Native distribution listing |
| --- | --- | --- |
| Auth principal | workspace API key | dedicated channel credential/profile |
| Who validates the end user | Grad validates its customer workspace key. | The router validates its user; Grad validates the router/channel only. |
| Financial authority | customer organization credit ledger | distribution-channel contract and receivable ledger |
| Redis admission | organization/workspace/key policy, reservation and nested limits | `ChannelAccountProjection`, exposure, catalog, contract quotas and concurrency |
| Prices | first-party immutable price book | channel-specific immutable sell/payout price book |
| Trace policy | workspace/request Product Intelligence or stricter no-retain | channel contract; never silently creates a first-party customer workspace/trace |
| Analytics owner | authenticated Grad organization/workspace | aggregate channel operations and settlement only unless contract says otherwise |
| Reconciliation key | Grad request/admission/usage IDs | Grad IDs plus channel request/settlement IDs |
| Suspension | organization/workspace/key/balance policy | channel exposure, aging, drift, contract or capacity policy |

A customer using their own Grad key through a gateway does not become a channel receivable. Their gateway may independently retain payloads; our UI/docs disclose that the customer's selected gateway policy is outside Grad's no-retain guarantee. Native channels receive only contract-approved payload/metadata handling and are excluded from Product Intelligence by default.

Credential lookup, never a spoofable header, selects the principal/profile. Channel credentials cannot access the first-party tRPC control plane, organization credits, traces or customer catalog. Workspace credentials cannot select a channel price book. Properties and integration tests prove those separations under credential rotation, replay and concurrent settlement.

## Catalog profiles

One immutable internal release/catalog source generates several bounded views:

- **Direct customer view:** models permitted by organization/workspace/key policy, including curated direct-provider models and Grad products.
- **OpenRouter provider view:** only approved Grad-owned/differentiated releases plus OpenRouter-required identity, modality, quantization, context/output, string pricing, parameter/feature, readiness, capacity and data-center metadata.
- **Hugging Face mapping view:** concrete Hugging Face model identity, Grad provider model ID, task, staging/live state and capability evidence.
- **Other future channel view:** explicit schema/profile version; never an untyped copy of the direct customer response.

The HTTP route may remain `/v1/models`, with the credential selecting a view, if the partner accepts the standard route. If a partner requires a different model-list schema or fetch mechanism, add a separately authenticated channel catalog route; do not overload the customer schema with unbounded partner fields. All views are generated and drift-tested from the same release, qualification and price sources.

## Distribution target matrix

“Custom” means a user can configure Grad today without Grad entering a commercial provider program. “Native” means Grad appears by name in the router/marketplace and requires a contribution, application or contract.

| Target | Immediate custom path | Native path | Seed decision | Evidence and current uncertainty |
| --- | --- | --- | --- | --- |
| Official OpenAI SDKs | Point `baseURL` and bearer key at Grad. | None needed. | **P0:** release gate. | OpenAI OpenAPI plus TypeScript/Python SDK and `gpt-oss` compatibility harness. Supported subset must be explicit. |
| Vercel AI SDK | `@ai-sdk/openai-compatible` with `createOpenAICompatible`. | Publish a thin `@grad/ai-sdk-provider`; Vercel AI Gateway listing is not publicly self-service in reviewed docs. | **P0:** recipe; **P1:** package. | AI SDK documents both generic configuration and custom package structure. Do not claim Vercel Gateway listing without a confirmed partner path. |
| LiteLLM Proxy | `openai/<grad-model>` plus `api_base` ending `/v1` and Grad key in `model_list`. | Optional upstream contribution/catalog entry after demand. | **P0:** pinned config/container test. | OpenAI-compatible provider docs cover Chat/embeddings and proxy config. Native inclusion is convenience, not launch-critical. |
| Cloudflare AI Gateway | Account-scoped custom provider or `/compat`; BYOK can store the Grad key. | No public shared-listing path found in reviewed docs. | **P0:** documented config and hosted smoke. | Custom providers accept any HTTPS base URL; `custom-` slug/path rules and `/v1` joining need fixtures. |
| Portkey | “Local/Privately hosted provider,” OpenAI specification, Custom Host and auth headers. | Ask for catalog/native listing only after usage. | **P0/P1:** config fixture; hosted smoke. | Current docs explicitly allow OpenAI-spec private/custom hosts and model provisioning. Hosted UI behavior remains revalidation-dependent. |
| Helicone | `Helicone-Target-Url` to Grad and forward Grad authorization. | OSS provider definition, model/author/endpoint registries and tests. | **P0:** target URL; **P1:** native OSS PR. | Unknown domains may be rate limited until approved; current provider-contribution docs specify code/test locations. |
| OpenRouter | A customer can use Grad outside OpenRouter; there is no useful generic BYOK path that makes Grad globally listed. | Provider application, model-list profile, channel settlement, uptime/performance/tool measurements. | **P1:** first native marketplace. | Public provider program is documented; acceptance, contract and commercial terms remain external/human decisions. |
| Hugging Face Inference Providers | No customer custom-host route is required for the native value. | `huggingface.js` provider registration/PR, provider org, model mappings, automated validation. | **P1/P2:** second native marketplace. | Official registration docs say strictly OpenAI-compatible LLMs may skip most translation work; enablement and Team/Enterprise org are required for mapping APIs. |
| Kong AI Gateway | Treat Grad as an OpenAI/self-hosted upstream with explicit upstream URL where supported. | Native provider enum/plugin support would require contribution/partnership. | **P2:** compatibility spike, not promised recipe. | Kong supports OpenAI format, self-hosted/custom operation URLs, but provider/plugin/version/licensing combinations vary; test exact pinned deployment before publication. |
| Open WebUI and developer tools | Add Grad as an OpenAI-compatible connection/base URL. | Tool-specific provider listing only when usage warrants maintenance. | **P1/P2:** short recipes after core harness. | These are clients, not distribution receivable channels. They improve adoption but must not distort channel accounting. |
| Bedrock Marketplace, Vertex Model Garden, Azure model marketplaces | No simple customer custom-host equivalent assumed. | Commercial/cloud marketplace packaging and cloud-specific data/serving integration. | **P3:** evidence-gated enterprise work. | These are materially heavier sales, legal, deployment and billing surfaces; do not put them on seed critical path. |

This is a curated target list, not a commitment to every AI gateway. Add a target only when it offers material reachable users or a funded customer and can reuse the shared contract without weakening auth, money, privacy or exact-release behavior.

## OpenRouter native provider profile

OpenRouter is the reference native distribution integration because its current public provider guide exposes concrete operational requirements.

### Build before applying

1. Generate the provider catalog from immutable Grad release data. Include exact provider-call model ID, Hugging Face ID when applicable, name, created time, modalities, quantization, context/max output, USD pricing strings, supported parameters/features, readiness/lifecycle/free/discount state, capacity and data-center metadata.
2. Support no more than the documented number of price tiers and validate catalog schema independently of inference.
3. Issue a dedicated OpenRouter credential/profile and Redis channel projection. It has a model allowlist, exposure ceiling, TPM/RPM/concurrency/capacity limits, privacy policy and rotation epochs.
4. Implement Chat stream/non-stream, tools, usage, finish reasons, request IDs, auth/model errors, cancellation, early 429, keepalive and explicit midstream failure.
5. Export settlement rows joining OpenRouter request IDs to Grad admission, attempt, metering, price-book and receivable IDs. Duplicate/redelivered settlement must post once.
6. Monitor channel-visible uptime, TTFT, throughput, early capacity rejection and tool-call correctness. No payload retention is needed for these operational metrics.
7. Run Auto Exacto-relevant tool tests for every model advertised as tool-capable; do not advertise the capability from model-family reputation.
8. Run a 24-hour staging soak and unit-economics model before a human submits the application.

OpenRouter currently reports normal routing at at least 95% uptime after sufficient traffic, degraded at 80–94%, and fallback-only below 80%; it classifies several auth/server/midstream failures differently from 400/403/413/429 capacity/client failures. These are vendor rules, not Grad's internal SLO. Revalidate them immediately before implementation/application.

### Packages and harnesses patterned after OpenRouter

OpenRouter's ecosystem illustrates the layers we should cover:

- a raw OpenAI-compatible API so existing `openai` clients work;
- a generated thin client from an OpenAPI document (`@openrouter/sdk`, `openrouter`, and a Go SDK in OpenRouter's case);
- a Vercel AI SDK provider (`@openrouter/ai-sdk-provider`);
- integration recipes for LangChain, LlamaIndex, PydanticAI, Mastra and developer tools;
- provider-side catalog, uptime/performance and tool-quality verification.

Grad should initially build only the layers that reduce adoption friction:

| Layer | Package/tool | Grad use |
| --- | --- | --- |
| Protocol authority | `product/schemas/openapi.yaml`, JSON Schema and SSE fixtures | Generate docs/types and drive black-box conformance. Do not make generated SDKs the only supported clients. |
| TypeScript baseline | `openai` | Direct and through-router Chat/Responses/Embeddings E2E. |
| Python baseline | `openai` | Cross-language direct and through-router E2E. |
| Go baseline | `github.com/openai/openai-go` | Catch URL, header, streaming and decoder assumptions outside JS/Python. |
| OpenAI provider smoke | pinned `openai/gpt-oss` `compatibility-test` | Tool/API-shape smoke for Chat and Responses, including streaming; upstream test results are evidence, not a complete certification. |
| Vercel AI SDK generic | `ai`, `@ai-sdk/openai-compatible` | P0 example and tests for stream, tools, structured output, usage and provider metadata. |
| Grad AI SDK package | `@grad/ai-sdk-provider` built on `@ai-sdk/openai-compatible`, `@ai-sdk/provider`, `@ai-sdk/provider-utils` | P1 thin defaults/model types only. No alternate protocol, retry or billing logic. |
| OpenRouter black box | `@openrouter/sdk`, Python `openrouter`, `github.com/OpenRouterTeam/go-sdk`, and `@openrouter/ai-sdk-provider` | Post-listing E2E proving a public OpenRouter client reaches Grad and settlement IDs match. Test dependencies only. |
| LiteLLM | pinned `litellm` proxy container/Python package | Reproducible config and pass-through tests. Do not link Python into production services. |
| Framework reach | `@langchain/openai`, `langchain-openai`, PydanticAI and LlamaIndex only after P0 | Small compatibility matrix/repro recipes; do not add every framework to main production dependencies. |
| TypeScript verification | Vitest, fast-check, MSW or deterministic Hono/Axum fakes, Testcontainers | Schema properties, request generators, pass-through and fault fixtures. |
| Python verification | pytest, Hypothesis, httpx and respx | Cross-client request/stream/error properties and LiteLLM harness control. |
| Rust verification | reqwest, wiremock, proptest and proptest-state-machine | Ingress/admission/channel state machines, malformed stream/fault simulation and exact byte-level behavior. |
| Containers | Docker Compose/Kind services for pinned LiteLLM, Kong and local fakes | Deterministic local/CI router tests. Hosted Cloudflare/Portkey/Helicone checks are protected, budgeted jobs. |

Do not generate first-party Grad SDKs for three languages before customers need them. The official OpenAI clients are the migration interface. A generated SDK becomes worthwhile only for Grad-specific control-plane or metadata APIs that cannot be expressed cleanly through the standard clients.

## Shared distribution harness

### Repository shape

```text
product/
  packages/distribution-testkit/       # TS generators, assertions, redaction
  services/gateway/crates/gateway-distribution/
  services/gateway/crates/gateway-testkit/
  schemas/distribution/                 # capability and catalog profiles
  tests/distribution/
    fixtures/                           # language-neutral JSON/SSE/error goldens
    direct/                             # official OpenAI client matrix
    routers/
      litellm/config.yaml
      cloudflare/custom-provider.json
      portkey/README.md
      helicone/README.md
      kong/kong.yaml
    channels/
      openrouter/                       # catalog, fake channel and settlement fixtures
      huggingface/                      # provider helper/mapping/validation fixtures
    python/                             # locked pytest/Hypothesis project
    go/                                 # locked official-client smoke module
  evidence/integrations/<target>/<date>/
```

Configuration examples contain environment variable names only. Never commit customer, provider, router or channel credentials.

### Harness layers

1. **Provider contract harness.** Calls Grad directly with official clients and generated HTTP cases. Covers models, Chat, Responses, Embeddings, stream/non-stream, tools, structured output, usage, cancellation, auth, limits and error envelopes.
2. **Pass-through router harness.** Sends the same case through a real pinned local router where possible. Asserts path joining, model IDs with slashes, authorization/header allowlists, body fidelity, SSE ordering/comments, usage, cancellation propagation, timeout and exact status preservation.
3. **Native-channel simulator.** Uses a dedicated fake channel credential, catalog profile and channel request IDs. Proves receivable settlement, exposure closure, credential rotation and zero customer-credit/first-party-trace mutation.
4. **Post-listing black-box harness.** Uses protected partner credentials to call the public router with an official router SDK, verifies the returned provider when observable, and joins router IDs to Grad settlement. It is scheduled/budgeted and never runs on forks.
5. **Soak/performance harness.** Measures accepted availability, early 429, TTFT, output throughput, disconnect/midstream behavior and reconciliation drift at a declared model/release/load/region/date. It does not transfer results across releases/providers.

### Required invariant cases

- A workspace key sent directly and through each custom gateway charges the same organization price book and nested limits exactly once.
- A native channel key can never reserve customer credit, open a customer trace, inherit Product Intelligence or access tRPC.
- Router retries before first output cannot duplicate sold usage; retries after exposed output follow the frozen no-replay/settlement policy.
- Cancellation propagates to the inference edge/cell and records partial billable usage consistently.
- Headers containing credentials, router auth, cookies or trace payloads never enter fixtures/artifacts/logs.
- Unsupported parameters/capabilities remain explicit through every proxy.
- `/v1` is neither omitted nor duplicated by base URL/path joining.
- `grad/high/fast` remains one model string and is never interpreted as URL routing.
- Keepalive comments do not alter token/usage output or hide a terminal error.
- Channel/provider request IDs are bounded, untrusted correlation inputs; Grad IDs remain authoritative.
- Catalog model IDs, capabilities, price version and readiness match the request profile under concurrent rollout/rollback.
- No-retain still permits the tenant-isolated ephemeral KV/prefix cache under the existing cache contract.

Property generators vary messages/content parts, tool schemas, structured-output schemas, optional parameters, Unicode/chunk boundaries, stream event splits, token/usage totals, model IDs, status/fault timing, cancellation point, credential epoch and concurrent reserve/settle/reconcile order. Every failure records seed, minimized trace and one replay command.

## CI jobs and release gates

| Job | Trigger | Network/secrets | Gate |
| --- | --- | --- | --- |
| `distribution-contract` | every main commit/external PR | none | Official OpenAI clients plus generated cases against local Grad/fakes. |
| `distribution-routers-local` | every main commit/external PR | none | Pinned LiteLLM and any qualified local router images/configs; Cloudflare/Portkey config schema checks. |
| `distribution-channel-sim` | every main commit/external PR | none | OpenRouter/HF catalog, credential, receivable and privacy isolation. |
| `distribution-deep-pbt` | nightly | none | High-case cross-language/state-machine/fault run. |
| `distribution-hosted-smoke` | main/nightly/manual protected environment | per-router secrets, hard request/dollar caps | Cloudflare, Portkey, Helicone or equivalent hosted forwarding. |
| `openrouter-post-listing` | nightly/manual after listing | OpenRouter key/channel visibility, hard cap | Public OpenRouter SDK call reaches Grad and reconciles. |
| `distribution-soak` | release/manual | approved environment and explicit budget | 24-hour model/release-specific SLO/economics evidence before native application/release. |

Hosted smoke and partner applications require human-approved credentials/terms and are absent from forked PRs. Missing secrets fail only a required protected environment job; they do not turn untrusted PR checks into paid calls. Each hosted job caps concurrency, tokens, retries, models, wall time and monthly spend, and stores hashes/IDs/measurements rather than payloads.

## Delivery and delegation

1. **Freeze public contract.** Snapshot supported OpenAI schemas, publish capability/error/stream fixtures, add public base URL configuration, and implement direct official-client conformance.
2. **Freeze distribution principals.** Add protobuf/domain types for `DistributionProfile`, channel credential, catalog profile, request correlation and receivable events; generate TS/Rust and add drift CI.
3. **Build the shared harness.** Implement language-neutral cases, TS/Rust property generators, official Python/Go runners, sanitized artifacts and replay commands.
4. **Ship P0 recipes.** LiteLLM, Cloudflare, Portkey, Helicone Target URL and generic Vercel AI SDK configurations, each backed by the same pass-through matrix.
5. **Build OpenRouter profile.** Catalog, dedicated admission/accounting, fake channel, operational metrics, tool harness, settlement export and soak. Human submits only after the decision gate.
6. **Publish `@grad/ai-sdk-provider`.** Keep it thin and generated/tested from the public capability catalog; publish only after generic AI SDK conformance is stable.
7. **Add Hugging Face native adapter.** Prepare the `huggingface.js` provider helper/registration PR, provider organization and staging model mappings; run HF automated validation before live mappings.
8. **Add demand-led integrations.** Helicone native OSS, LiteLLM native catalog/contribution, Kong exact-version spike, developer-tool recipes and closed marketplaces in measured priority order.

Agents may work in parallel after steps 1–3 freeze shared contracts. Give each target agent only its config, adapter, tests and evidence directory. A single integration owner approves changes to public schemas, catalog capabilities, principal/accounting semantics and shared fixtures.

## Go/no-go and falsification

The strategy is wrong or needs revision if any of these are measured:

- ordinary official OpenAI clients require Grad-specific request code for baseline features;
- customer-configured gateways cannot preserve streaming, tools, usage, errors or model IDs without target-specific runtime forks;
- a native channel cannot reconcile request-level usage/revenue without touching customer credit state;
- channel volume has negative contribution margin after retries, spot interruption, support and payout terms;
- a target's integration requires weakening auth, exposing customer traces, silently changing models or violating exact-release routing;
- maintaining router recipes/packages costs more engineering time than the qualified traffic or customer revenue they produce.

When one target fails, remove or defer that target; do not fork the core serving contract to satisfy a low-value router. Native OpenRouter/Hugging Face acceptance is externally controlled, so direct and custom-provider distribution remains the launch fallback.

## Evidence and source notes

Evidence labels in this document are **vendor-reported** for public requirements/package behavior, **analytical** for Grad decisions and **inferred** only where explicitly stated. No authenticated partner UI, application submission, commercial negotiation, paid request or live compatibility run was performed for this plan.

Current official sources reviewed on 2026-07-13:

- [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers)
- [OpenRouter client SDKs](https://openrouter.ai/docs/client-sdks/overview)
- [OpenRouter frameworks and integrations](https://openrouter.ai/docs/guides/community/frameworks-and-integrations-overview)
- [OpenRouter Vercel AI SDK integration](https://openrouter.ai/docs/guides/community/vercel-ai-sdk)
- [OpenAI gpt-oss implementation verification](https://developers.openai.com/cookbook/articles/gpt-oss/verifying-implementations#quick-verification-of-tool-calling-and-api-shapes)
- [OpenAI OpenAPI specification repository](https://github.com/openai/openai-openapi)
- [Vercel AI SDK OpenAI-compatible provider](https://ai-sdk.dev/providers/openai-compatible-providers)
- [Vercel AI SDK custom provider package](https://ai-sdk.dev/providers/openai-compatible-providers/custom-providers)
- [LiteLLM OpenAI-compatible provider](https://docs.litellm.ai/docs/providers/openai_compatible)
- [LiteLLM proxy configuration](https://docs.litellm.ai/docs/proxy/configs)
- [Cloudflare AI Gateway custom providers](https://developers.cloudflare.com/ai-gateway/configuration/custom-providers/)
- [Portkey provider integrations and custom host](https://portkey.ai/docs/product/integrations)
- [Helicone generic gateway target](https://docs.helicone.ai/getting-started/integration-method/gateway)
- [Helicone native provider integration](https://docs.helicone.ai/references/provider-integration)
- [Hugging Face provider registration](https://huggingface.co/docs/inference-providers/en/register-as-a-provider)
- [Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers/en/index)
- [Kong AI Proxy Advanced](https://developer.konghq.com/plugins/ai-proxy-advanced/)
- [Kong AI Proxy configuration reference](https://developer.konghq.com/plugins/ai-proxy/reference/)
- [Vercel AI Gateway models/providers](https://vercel.com/docs/ai-gateway/models-and-providers)

Vendor requirements, package names and onboarding paths are volatile. Revalidate them before pinning dependencies, publishing a recipe/package, submitting an application or accepting commercial terms.
