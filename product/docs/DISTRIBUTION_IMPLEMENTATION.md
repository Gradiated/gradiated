# Simplified distribution implementation blueprint

## Two modes, one serving path

1. A customer-configured gateway or SDK sends a normal workspace key to Grad. Billing, traces and limits are identical to direct customer traffic.
2. OpenRouter sends a dedicated channel credential for a natively listed owned release. Grad applies channel exposure/receivable accounting and does not need the downstream user's identity.

OpenRouter is the only native channel implemented first. Hugging Face and others remain future decision records. LiteLLM/Cloudflare/Portkey/Helicone/Vercel integrations are configuration fixtures, not production dependencies.

## Dependencies and source layout

Distribution reuses the gateway, control image, PostgreSQL, Valkey and black-box testkit. It adds no service, database, queue or universal principal/event abstraction.

```text
product/
  packages/distribution-testkit/
  tests/distribution/{cases,runners,fixtures}/
  integrations/{litellm,cloudflare,portkey,helicone,vercel}/
  evidence/distribution/openrouter/
```

Channel credential lookup returns `Principal::Channel { channel_id, credential_id }`; workspace lookup returns the workspace principal. A request body/header cannot change kind. Event payloads carry either workspace IDs or channel IDs, never a generic `PrincipalRef`.

## Minimal channel model

Use only `distribution_channels`, rebuildable `channel_balances`, `channel_credentials`, `channel_catalog`, immutable `channel_usage_records`, the shared fixed-chart ledger, and—when the first contract requires it—`channel_statements`. Required fields are in [the minimal model](../../docs/SIMPLICITY_REVIEW.md#external-distribution). A separate channel usage table avoids nullable generic principal columns in customer usage while preserving dispute/reconciliation evidence.

Remove `distribution_profiles`, copied release capabilities, risk enums and separate receivable transaction classes. Channel status/exposure/data policy/catalog version are sufficient runtime policy; commercial terms remain in the signed contract and operator runbook.

Workspace and channel financial keys/account charts are disjoint, but both call the same parameterized reserve/settle state machine and balanced ledger implementation. Explicit account scope checks, organization/channel foreign keys and repositories prevent a channel effect from mutating organization credit.

## Customer gateway recipes

Each recipe contains only base URL, standard bearer workspace key, exact model ID, streaming-safe timeout and third-party logging/privacy instructions. It cannot require Grad-specific routing headers for basic use.

Pinned black-box cases prove:

- path joining and slash-containing model IDs;
- authentication forwarding/redaction;
- models, stream/non-stream text, tools and structured output where claimed;
- usage/finish/error/SSE/cancellation preservation;
- 400/401/402/404/413/429/5xx and midstream behavior;
- no-retention tightening and disclosed third-party logging;
- direct-versus-proxy equality of principal, release, sell amount and trace mode.

If a gateway cannot preserve a feature, mark it unsupported in that recipe. Do not change core wire behavior to accommodate it.

## OpenRouter catalog

Expose a channel-authenticated catalog renderer at a stable integration URL. Its internal source is the approved `channel_catalog` joined to one active `model_release` and current coarse ready capacity.

```text
ChannelCatalog
  version, generated_at, expires_at
  models[]
    external_model_id
    release_digest
    display/source identity
    modalities, context/output limits, supported parameters
    quantization where known
    channel prices
    coarse capacity/regions/readiness
    data/logging/training disclosure
```

Do not persist fields copied from the release. The renderer derives them. The channel catalog initially lists one differentiated Grad-owned release, never direct-provider resale or theoretical effort/speed combinations.

## Admission and settlement

Channel reserve verifies credential/status, catalog release, immutable channel price, exposure limit/outstanding amount, concurrency and idempotency in one Valkey script. It cannot access organization keys. It routes the exact owned release through inference router/cell and emits channel-shaped reservation/settlement events.

```ts
interface ChannelBilling {
  postUsage(event: ChannelUsageSettled): Promise<void>;
  applyPayment(input: PaymentEvidence, actor: BillingOperator): Promise<void>;
  applyAdjustment(input: Adjustment, actor: BillingOperator): Promise<void>;
  reconcile(statement: ChannelStatementRef, actor: BillingOperator): Promise<ReconciliationReport>;
}
```

Each effect posts an immutable balanced channel receivable/revenue/cash-or-adjustment transaction and updates the locked `channel_balances.outstanding_micros` projection. Statement digest/period uniquely identifies reconciliation. Unexplained delta, overdue exposure or policy mismatch suspends new channel admission while settlement continues.

Seed native traffic creates no first-party Product Intelligence trace or recommendation. It retains only content-free usage/reliability needed for settlement and operations. A later payload-retention contract requires a new explicit decision.

## Onboarding gate

Before applying, record current official requirements, catalog/schema fixtures, privacy/terms/tax/payment owner, 24-hour staging soak, early 429/stream/tool behavior, uptime/TTFT/throughput and positive contribution margin. Human approval is required for terms, credentials and publication.

OpenRouter validates/bills its own user token and calls Grad with Grad's channel credential. Grad validates the channel only. The public channel request still enters the Grad gateway for release/capacity/admission/usage; it never calls cells directly.

## Shared harness

One JSON case format contains case ID/version, endpoint/request fixture refs, principal kind, expected public events/errors, expected release/settlement/trace facts, injected fault schedule, timeout and redaction assertions.

Runners are official OpenAI TypeScript/Python/Go clients, Vercel AI SDK, pinned LiteLLM, a deterministic fault proxy, an OpenRouter channel simulator and post-acceptance hosted smoke. OpenRouter SDKs remain test dependencies only.

## Operations and ordered packages

Metrics separate customer-recipe and native-channel traffic. Invariant counters for channel-to-organization mutation, channel-created first-party trace, direct-provider resale and cell-accepted channel credential must remain zero. Operator controls can suspend credential, model catalog entry or channel while settlement/reconciliation remain live.

1. `DI-00`: principal-kind credential lookup and channel SQL/Valkey state using shared admission core.
2. `DI-01`: language-neutral cases and official direct-client runners.
3. `DI-02`: LiteLLM/Vercel then Cloudflare/Portkey/Helicone recipes.
4. `DI-03`: OpenRouter catalog renderer and channel simulator.
5. `DI-04`: shared-ledger/channel-balance/statement reconciliation PBT.
6. `DI-05`: 24-hour staging/economics/security packet and human onboarding gate.

No second native channel package starts until OpenRouter is live or rejected with a dated reason.
