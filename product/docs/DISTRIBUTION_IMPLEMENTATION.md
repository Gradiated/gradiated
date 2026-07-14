# Distribution and gateway integration implementation blueprint

## Two integration modes

Do not combine these modes in credentials, billing, traces, catalog or customer support:

1. **Customer-configured gateway:** a Grad customer configures LiteLLM, Cloudflare, Portkey, Helicone, Kong, Vercel AI SDK or another client/proxy with a workspace key and Grad base URL. This is ordinary organization-prepaid traffic.
2. **Native distribution channel:** OpenRouter, Hugging Face or another approved marketplace lists selected Grad-owned releases and calls Grad with its own channel credential. This uses channel exposure/receivables and contract privacy. The downstream end user need not have a Grad account.

Both enter the same public Rust gateway and then the same exact-release owned inference path. Neither may call inference edge/cells directly.

## Source/package layout

```text
product/
  packages/
    distribution-contracts/       # profiles/catalog/settlement schemas
    distribution-testkit/          # language-neutral request/stream/error cases
    integration-configs/
      litellm/ cloudflare/ portkey/ helicone/ kong/ vercel-ai/
    integration-docs/              # generated/tested customer snippets
  tests/distribution/
    official-openai/{ts,python,go}/
    local-router/litellm/
    channel-simulator/
    hosted-smoke/
  services/gateway/crates/gateway-distribution/
  evidence/integrations/<target>/<date>/
```

Production gateway dependencies remain Rust/HTTP/Protobuf/Redis. LiteLLM, framework SDKs and router packages are test/example dependencies only.

## Principal and event contracts

```text
PrincipalRef = oneof
  WorkspacePrincipalRef(organization_id, workspace_id, api_key_id)
  DistributionChannelPrincipalRef(channel_id, credential_id, profile_version)
  ServicePrincipalRef(service, role)
  ResearchPrincipalRef(program/campaign/run)
```

Credential lookup selects exactly one principal before parsing model policy or money. A header/body cannot convert workspace traffic to channel traffic, select an organization for a channel or borrow a channel catalog.

Channel PostgreSQL entities:

- `distribution_channels`: contract/status/risk/currency/settlement terms, legal/privacy owner;
- `distribution_credentials`: prefix/keyed digest/status/rotation/last-used;
- `distribution_profiles`: immutable protocol/catalog/data/price/limit version;
- `channel_catalog_entries`: exact owned release and external model ID/metadata/effective time;
- `channel_receivable_transactions`: immutable usage/credit/invoice/payment/adjustment business effects;
- `channel_reconciliation_checkpoints`: downstream report/invoice period, usage set/digest, delta and status.

Redis `ChannelAccountProjection` contains status/profile/catalog/price/exposure/in-flight/rate/concurrency/credential state under `gw-channel:{channel_id}`. Workspace keys/scripts cannot touch it.

Events are `ChannelReservationCreated`, `ChannelUsageSettled`, `ChannelCreditRequested`, `ChannelInvoiceIssued`, `ChannelPaymentApplied`, `ChannelAdjustmentPosted`, `ChannelStatusChanged` and `ChannelReconciliationMismatch`. They carry channel principal, never fake organization/workspace IDs.

## Customer-configured gateway contract

Every recipe configures:

- Grad base URL and standard bearer workspace key;
- exact canonical model ID or documented unique bare alias;
- no provider arrays or Grad-specific headers required for baseline use;
- streaming and timeout values that do not buffer/corrupt SSE;
- log/body capture disabled or explicitly disclosed in the third-party gateway;
- optional Grad session/data-policy headers only when the proxy safely forwards them.

The black-box assertion is simple: the same request directly and through the gateway resolves the same principal/model/release/price/data mode and posts one organization usage effect. Proxy retries must not create an extra financial effect; request IDs/idempotency fixtures prove behavior.

### Recipe acceptance matrix

Each checked-in target version runs:

- authentication forwarding, key redaction and prohibited header injection;
- base URL/path joining including `/v1` and slash-containing Grad model IDs;
- model list where supported;
- stream/non-stream text, tools and structured output;
- usage/finish reason/error preservation, UTF-8/SSE comments and cancellation;
- 400/401/402/404/413/429/5xx and midstream failure;
- no-retain tightening and proof of third-party logging configuration;
- direct-versus-proxy ledger, trace and actual-model equivalence.

If a proxy cannot preserve a claimed feature, the recipe declares it unsupported; Grad does not alter core wire semantics to accommodate one low-value target.

## Native channel catalog

Use a separate operator/channel catalog endpoint rather than overloading customer `GET /v1/models` with incompatible marketplace fields:

```text
GET /integrations/<channel>/v1/models
Authorization: Bearer <channel-catalog-credential>
ETag / If-None-Match

ChannelModelCatalog
  catalog_version, generated_at, expires_at
  models[]
    external_model_id
    exact_route_release_id / bundle_digest
    display/source/HuggingFace identity where applicable
    modalities, context/output limits, quantization
    supported parameters/features
    fixed channel pricing strings/currency/unit
    capacity, regions/data centers, lifecycle/deprecation/readiness
    data policy and training/logging disclosure
```

The endpoint is generated from approved immutable channel catalog entries and release/capacity projections. It cannot list curated direct-provider resale or an unqualified/unpriced/expired Grad release. Channel-specific renderers convert one internal `ChannelCatalogEntry` to OpenRouter/Hugging Face schemas and have golden fixtures.

The inference request still uses the normal public `/v1/chat/completions` (and any separately approved paths). The external model ID resolves only under the authenticated channel profile to one exact Grad release.

## Native channel admission and serving

```rust
pub trait DistributionProfileResolver {
    fn resolve(&self, principal: &ChannelPrincipal, requested_model: &RequestedModel)
        -> Result<ChannelRequestProfile, DistributionError>;
}

pub trait ChannelExposureStore {
    async fn reserve(&self, command: ChannelReserveCommand) -> Result<Reservation, AdmissionError>;
    async fn settle(&self, command: ChannelSettleCommand) -> Result<SettlementReceipt, SettlementError>;
}
```

Admission verifies credential/status/profile/catalog/release/price, maximum receivable exposure, aging/freeze policy, rate/concurrency/capacity and idempotency in one channel Redis operation. It does not require or debit a customer credit balance. Gateway routes only the exact owned release through inference edge/cell and emits channel settlement. External downstream request ID is bounded/hashed and stored as reconciliation correlation; it is not trusted as sole idempotency identity.

Channel data handling is profile-owned. Seed native traffic does not create first-party Product Intelligence traces, workload profiles or migration recommendations. Minimum content-free usage/reliability facts are retained for settlement and operations. If a channel contract later permits payload retention, it requires a new explicit profile/ADR and isolated customer-facing disclosure—not reuse of workspace trace behavior.

## Channel settlement and reconciliation

```ts
interface ChannelSettlementService {
  postUsage(event: ChannelSettlementEvent): Promise<ReceivableTransaction>;
  ingestStatement(input: ChannelStatementRef, operator: OperatorContext): Promise<ReconciliationReport>;
  issueInvoice(input: InvoicePeriod, billingActor: BillingActor): Promise<InvoiceRecord>;
  applyPayment(input: ChannelPaymentEvidence, billingActor: BillingActor): Promise<void>;
  adjust(input: ChannelAdjustment, billingActor: BillingActor): Promise<void>;
}
```

Usage posting is immutable/idempotent and carries our request/attempt/release/units/channel-price version plus downstream correlation. Statements/invoices are stored by content digest and reconciled line-by-line or aggregate-with-provable-membership according to the contract. Unexplained delta, overdue exposure, payment failure or profile mismatch closes new channel admission while existing settlements/reconciliation continue.

Channel revenue and customer prepaid ledger are separate account families. An operator report may combine company economics, but no database transaction transfers a channel receivable to organization credit unless an explicit unrelated customer payment business event exists.

## OpenRouter profile

Current official provider requirements are volatile and must be source-dated at onboarding. The implementation package currently needs:

- OpenAI-compatible Chat Completions streaming with terminal usage;
- the separate OpenRouter model-list renderer with exact IDs, pricing strings, features, quantization, lifecycle/readiness, capacity and data-center metadata;
- early explicit 429 under load, keepalive comments where safe and correct midstream terminal behavior;
- synthetic uptime/TTFT/throughput/tool-call conformance without payload logging;
- automatic payment/invoicing owner and reconciled request/usage evidence;
- maintenance/readiness control that hides a model without changing its identity;
- a 24-hour staging soak and contribution-margin model before application.

OpenRouter validates/bills its user token. It sends Grad's channel credential to Grad. Grad validates only that channel and never receives or needs the user's OpenRouter account identity. Application submission, terms acceptance, secret exchange and model publication require founder/legal approval.

The channel catalog may initially list one proprietary/differentiated Grad release. Do not list OpenAI/Anthropic/Google resale, an experimental research alias or all theoretical effort/speed combinations.

## Hugging Face and later channels

Hugging Face is the second native target. Keep its model/provider mapping renderer and integration helper separate from OpenRouter. Shared code ends at internal catalog/principal/settlement and black-box request corpus. A marketplace-specific SDK, schema or commercial report never becomes core gateway authority.

New native channels pass a target decision record:

1. documented provider/onboarding path and contact;
2. owned/differentiated supply accepted by the channel;
3. protocol/catalog/privacy/settlement mapping without weakening core invariants;
4. isolated credential/profile and positive expected contribution margin;
5. bounded implementation/support cost and named legal/billing owner.

Otherwise ship a customer-configured endpoint recipe only.

## Shared black-box harness

Language-neutral case format:

```text
DistributionCase
  case_id / schema_version
  ingress endpoint and request fixture refs
  principal kind/profile/catalog version
  expected public event/error sequence
  expected canonical model/release/data mode
  expected reservation/settlement/trace facts
  injected proxy/upstream fault schedule
  timeout and secret/log redaction assertions
```

Runners:

- official OpenAI TypeScript/Python/Go clients direct to Grad;
- Vercel AI SDK OpenAI-compatible provider;
- pinned LiteLLM proxy;
- deterministic custom-gateway fault proxy for header/path/stream behavior;
- native channel simulator with catalog credential and exposure ledger;
- post-acceptance OpenRouter/Hugging Face SDK/hosted black-box smoke.

Every failure artifact includes target/package version, case ID, safe request IDs, seed/shrink path, sanitized event transcript and replay command. Never upload body/credential/proxy dumps.

## Integration lifecycle

```text
proposed -> source_verified -> local_conformance -> staging_soak
 -> approved -> published -> monitored -> deprecated -> removed
                  \-> deferred/rejected
```

Each integration has an owner, pinned versions, evidence date, supported feature matrix, customer/privacy instructions, monitoring and removal test. A volatile vendor requirement older than the review interval blocks publication until revalidated. Removal of a recipe/channel never changes core customer keys or route releases.

## Metrics and operations

Separate by mode and target:

- customer gateway: activation, request success, support cases, protocol differences and retained paid usage;
- native channel: catalog fetch/version lag, auth/rate/exposure rejection, uptime/TTFT/throughput/tool success, capacity 429, usage/statement/invoice delta, payout aging, retries and contribution margin;
- invariant counters: channel-to-organization balance mutation, first-party trace under channel principal, direct-provider resale listing and edge/cell credential acceptance must remain zero.

Operator controls freeze credential, model entry, whole profile or new channel admission while allowing settlement/reconciliation. Secret rotation supports overlap by credential ID/expiry and projects urgently.

## Verification and junior-agent packages

Implement in order:

1. `DI-00`: `PrincipalRef`, channel tables/events/Redis projection and simulator.
2. `DI-01`: language-neutral black-box case schema plus direct OpenAI TS/Python/Go runners.
3. `DI-02`: LiteLLM and deterministic fault-proxy harness.
4. `DI-03`: Cloudflare/Portkey/Helicone/Vercel recipes, one target-owned package per agent.
5. `DI-04`: channel admission/settlement/reconciliation PBT isolated from organization money.
6. `DI-05`: channel catalog core plus OpenRouter renderer/credential/monitor fixtures.
7. `DI-06`: OpenRouter 24-hour staging soak/economics/security packet; human application gate.
8. `DI-07`: Hugging Face renderer/helper and staging validation.
9. `DI-08`: hosted monitoring, deprecation/offboarding and support runbooks.

Customer-configured recipes can ship before native channel work. Native distribution never blocks direct Grad availability or first revenue.

## Current source notes

OpenRouter's official provider documentation retrieved 2026-07-14 reports a model-list contract, automatic payment/invoicing, monitored uptime/performance and OpenAI-compatible streaming/usage requirements: [provider integration](https://openrouter.ai/docs/guides/community/for-providers). This is vendor-reported and must be revalidated before onboarding. The dated target/package source set remains in [Open distribution and gateway integration plan](DISTRIBUTION_GATEWAY_INTEGRATIONS_2026-07-13.md).
