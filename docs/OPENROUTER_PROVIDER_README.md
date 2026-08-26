# OpenRouter provider readiness

- status: working checklist
- date: 2026-08-25
- owner: Gradiated Ltd
- application: https://openrouter.ai/providers/apply
- technical requirements: https://openrouter.ai/docs/guides/community/for-providers
- architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

This document is the working checklist for OpenRouter onboarding. Update the
status and evidence after each change. Do not submit the provider application
until all blocker items are complete.

DeepSeek V4 Flash 0731 is the next model-specific launch. Its runtime, model
configuration, tool support, and GPU qualification remain pending. Complete the
shared provider work in this document before adding that model.

## Target outcome

Gradiated must provide OpenRouter with a reliable OpenAI-compatible endpoint.
OpenRouter must be able to list models, read their prices and capabilities,
send streaming and non-streaming requests, reconcile usage, and pay by monthly
invoice.

## Current status

| Area             | OpenRouter expectation                                    | Gradiated status                                                                                                         | State        |
| ---------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------ |
| Application      | Submit the provider form and pass review                  | Not submitted                                                                                                            | pending      |
| API protocol     | OpenAI-compatible `/chat/completions` with streaming      | Gateway implements both response modes and usage accounting                                                              | ready        |
| Endpoint path    | Stable public provider endpoint                           | `https://api.gradiated.com/openai/v1`                                                                                    | ready        |
| Authentication   | Protected endpoint and provider credential                | Bearer authentication works; the dedicated operator setup command is ready, but the production credential is not created | blocker      |
| Models endpoint  | Non-empty `/models` response                              | Catalog serializer emits the OpenRouter model shape; Gemma 4 is released in production after the configuration operation | ready        |
| Model identity   | Exact model ID used by OpenRouter                         | Lowercase canonical IDs are implemented                                                                                  | ready        |
| Release metadata | `created` timestamp for each model                        | Production Gemma 4 row has `released_at` set to `2026-08-22T14:09:29.651Z`                                               | ready        |
| Pricing          | USD token prices                                          | Catalog emits string USD prices from integer nano-USD values                                                             | ready        |
| Limits           | Context and maximum output limits                         | Catalog emits model-owned limits                                                                                         | ready        |
| Capabilities     | Advertise supported parameters and features               | Catalog emits typed modality parameter descriptors and only configured features                                          | partial      |
| Capacity         | Measured or declared capacity                             | Typed capacity entries are optional and remain unset until measured                                                      | pending      |
| Location         | Datacenter and deployment-region metadata                 | Catalog declares the production datacenter as `US`                                                                       | ready        |
| Compliance       | Clear data-handling posture                               | No ZDR, HIPAA, or SOC 2 claim is made                                                                                    | partial      |
| Privacy          | Policy with prompt logging, retention, and training terms | Privacy page now includes inference storage, training, retention, and subprocessors                                      | legal review |
| Payments         | Monthly invoice or automatic payment setup                | Schema anticipates OpenRouter payments; onboarding is not configured                                                     | pending      |
| Reliability      | Continuous monitoring and stable traffic handling         | Two gateway replicas exist; runtime soak results are incomplete                                                          | partial      |
| Status page      | Public operational status                                 | To be completed by the Gradiated owner                                                                                   | user-owned   |
| Legal pages      | Company identity, privacy, and service terms              | Gradiated Ltd and privacy page exist; public terms are absent                                                            | recommended  |
| Next model       | Model-specific runtime, features, and benchmarks          | DeepSeek V4 Flash 0731 is not configured                                                                                 | pending      |

OpenRouter does not require every model to support every feature. Advertise only
features that have passed real request tests.

## Compatibility contract

### Public endpoint

Use this base URL in the provider application:

```text
https://api.gradiated.com/openai/v1
```

Required routes:

```text
GET  /models
POST /chat/completions
```

The public ALB adds `/openai` and removes that prefix before the Rust gateway
matches `/v1`. Keep the public provider base URL above in all integrations and
documentation.

### Model document

Every released model must publish:

- canonical lowercase `id`;
- customer-facing `name`;
- Hugging Face model ID when applicable;
- `created`, derived from `released_at`;
- description, quantization, and tokenizer metadata when known;
- typed text input modality with limits and token prices;
- typed text output modality with limits, token prices, streaming support, and
  supported parameter descriptors;
- request-scoped passthrough parameters when supported;
- `is_ready`;
- datacenter and deployment-region metadata;
- capacity metadata when measured.

The catalog must never publish private service URLs, credentials, artifact
revisions, internal release digests, prompts, completions, or customer data.

Use provider schema version `2.4`. OpenRouter marks the older flat format as
legacy for existing integrations. New providers should use the typed modality
format from its [provider schema](https://openrouter.ai/docs/assets/provider-monitor-schema-v2.openapi.json).

### Request behavior

The gateway must:

- accept the OpenAI Chat Completions request shape;
- match model IDs without regard to ASCII letter case;
- forward the canonical lowercase model ID downstream;
- return usage for non-streaming responses;
- return a final usage event for streaming responses;
- stream tokens as soon as they are available;
- return early `429` responses when capacity is exhausted;
- send keep-alive comments when model processing takes time;
- return stable OpenAI-compatible errors;
- avoid logging prompts, completions, authorization headers, or API keys.

### Capability policy

| Capability                                  | Initial policy                                      |
| ------------------------------------------- | --------------------------------------------------- |
| Text input and output                       | Required                                            |
| Streaming                                   | Required                                            |
| Temperature and sampling                    | Advertise only tested values                        |
| Tools                                       | Advertise only after tool-call tests pass           |
| Structured outputs                          | Advertise only after JSON-schema tests pass         |
| Reasoning                                   | Advertise only after reasoning and usage tests pass |
| Images, audio, video, embeddings, reranking | Do not advertise unless implemented                 |

## Privacy and data policy

The public privacy policy must add an inference-specific section. It must state:

- whether Gradiated stores prompts or completions;
- whether Gradiated uses prompts or completions to train models;
- how long request metadata is retained;
- whether prompts and completions appear in application, GPU, or provider logs;
- which subprocessors handle inference traffic and infrastructure;
- how customers request access or deletion;
- how OpenRouter traffic follows the same policy;
- which claims are not made, such as ZDR, HIPAA, or SOC 2, unless verified.

The current architecture does not persist prompts or completions. The public
policy must state this operational behavior clearly before application review.
This document does not replace legal review.

## Provider account and payment setup

Complete these items in production:

- create one `distribution_channel` organization named `OpenRouter`;
- create one workspace and one dedicated API key for OpenRouter;
- store only the key digest in PostgreSQL;
- provide the raw key to OpenRouter through its private onboarding flow;
- mark the account as `invoiced`;
- confirm that OpenRouter usage maps to the distribution-channel account;
- configure the monthly invoice and payment contact;
- verify that OpenRouter payments reconcile through `openrouter_payment`;
- document key rotation and revocation.

The API image includes an idempotent operator command. Run it from an API pod
with the raw key supplied by the production secret manager. Do not place the
raw key in the repository or in shell history:

```sh
OPENROUTER_API_KEY='secret-manager-value' \
  node /app/services/api/dist/operations/configure-openrouter.js
```

Never put the OpenRouter credential in this repository, a public document, or a
client-side application.

## Verification checklist

Run these checks with the dedicated provider key. Store results in a release
record. Do not store the key or request content.

### Catalog

```sh
export GRADIATED_OPENROUTER_KEY='use-a-secret-manager'

curl --fail --silent \
  https://api.gradiated.com/openai/v1/models \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" | jq .
```

Confirm that the response contains at least one model with a canonical ID, a
valid `created` timestamp, `is_ready`, valid prices, valid limits, tested
capabilities, and correct location metadata.

### Non-streaming request

```sh
curl --fail --silent \
  https://api.gradiated.com/openai/v1/chat/completions \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "MODEL_ID_FROM_CATALOG",
    "messages": [{"role":"user","content":"Reply with one word: ready"}],
    "max_tokens": 16
  }' | jq .
```

Confirm valid choices, usage, and the canonical model ID.

### Streaming request

```sh
curl --fail --silent \
  https://api.gradiated.com/openai/v1/chat/completions \
  -H "Authorization: Bearer $GRADIATED_OPENROUTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "MODEL_ID_FROM_CATALOG",
    "messages": [{"role":"user","content":"Reply with one short sentence."}],
    "max_tokens": 32,
    "stream": true
  }'
```

Confirm prompt tokens, streamed output, one authoritative usage event, and
`[DONE]`.

### Error and capacity checks

Confirm all of the following:

- invalid keys return `401`;
- unknown models return the documented model error;
- unsupported features return bounded `400` errors;
- invalid parameter values return bounded `400` errors;
- capacity exhaustion returns `429` without a long queue delay;
- cancelled streams stop upstream work;
- secrets and prompt content do not appear in logs;
- OpenRouter and Gradiated token totals reconcile.

### Reliability gate

Before enabling production traffic:

- run a representative load test;
- record TTFT, output tokens per second, error rate, and concurrency;
- complete a 24-hour soak test;
- confirm clean model restart behavior;
- confirm GPU, runtime, gateway, and network alerts;
- document maintenance and incident procedures;
- use on-demand GPU capacity, not spot capacity.

OpenRouter uses uptime, latency, throughput, price, and error behavior for
routing. It gives normal routing priority at 95% or higher uptime. Early `429`
responses are preferred to queued timeouts.

## Work order

1. Deploy the release-date change and confirm a non-empty production catalog. [done]
2. Add measured capacity entries after the runtime soak test.
3. Create and test the dedicated OpenRouter distribution-channel credential.
4. Complete privacy and company legal review.
5. Configure monthly invoicing and payment reconciliation.
6. Add a public status page or document the accepted alternative with OpenRouter. [user-owned]
7. Add and qualify DeepSeek V4 Flash 0731.
8. Run the complete verification checklist.
9. Submit the application with the endpoint, model data, pricing, capacity,
   region, privacy policy, and payment contact.

## Evidence log

| Date       | Change or test                                      | Result                                                                                                                             | Evidence                                            |
| ---------- | --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| 2026-08-25 | Production model row inspected                      | `released_at` is null; catalog is not advertised                                                                                   | Read-only production check                          |
| 2026-08-25 | Gateway model normalization tested                  | Mixed-case input becomes lowercase for lookup and upstream dispatch                                                                | Gateway test suite                                  |
| 2026-08-25 | Live OpenRouter catalog compared with provider docs | Public `/api/v1/models` is a normalized marketplace response; provider submission uses typed schema `2.4`                          | OpenRouter public API and provider schema           |
| 2026-08-25 | Production release deployed                         | API and gateway pods rolled out; Gemma 4 model row now has `released_at` and is available                                          | GitHub deployment run and production database check |
| 2026-08-25 | OpenRouter account setup prepared                   | Added idempotent operator command for the distribution channel, workspace, invoiced account, API-key digest, and Valkey projection | `configure:openrouter`                              |
| 2026-08-25 | Provider catalog serializer tested                  | Typed input/output modalities, string USD prices, datacenter, region, and no private deployment fields                             | Gateway catalog test suite                          |
