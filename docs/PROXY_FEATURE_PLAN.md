# Proxy feature: implementation plan

Status: step 1 is implemented for Anthropic Messages. Credential
classification, request authorization, route classification, and the bounded
relay transport pass local gateway checks. Terminal usage separation, the OpenAI
routes, fallback, and proxy usage reporting are not implemented. A relayed
generation produces no terminal record yet.

This plan owns proxy scope and build order. It supersedes earlier proposals
for platform-funded provider calls and task-owned fallback settings. Supporting
transport rules are in [GW-01 through GW-05](TASK_FINE_TUNING_GATEWAY_CONTRACT.md).

## Current implementation

**Identity.** `auth::extract_credentials` separates the Gradiated key from the
optional provider credential. `RequestCoordinator::authorize_request` hashes only
the Gradiated key and loads credential, workspace, and account state from Valkey.
It rejects revoked or expired credentials and inactive or inconsistent access
state. The returned context retains the provider credential in request memory.

Hosted qualification uses `into_hosted_identity`, which keeps the prepaid
balance check. `into_provider_request` requires a matching provider credential
without gating on Gradiated balance. It authorizes identity only; it does not
resolve a model, open a connection, or bypass later routing validation.

**Route classification.** `RequestCoordinator::classify` runs before hosted
translation and admission. It parses the body for exactly one non-empty string
`model` and rejects duplicate top-level keys, so a malformed target is a local
error on every route before identity is considered. A name that resolves in the
hosted catalog always serves locally, even when a provider key accompanies the
request. An unresolved name relays only with a matching provider key for the
route; without one it stays a local `model_not_found`. This build has no provider
model registry, so the provider remains authoritative for its own names.

**Transport.** `relay::ProviderRelay` refuses redirects, asks for identity
encoding, and applies the GW-03 deadlines. A byte budget and an in-flight slot
count bound the process, and the response body holds both permits until the
caller drops it. `upstream_headers` forwards the customer provider credential
alone and rejects an inbound hop header; `downstream_headers` keeps the
provider's content headers and drops the connection headers. The Anthropic
Messages route branches before `translate_inbound`, so a relayed body and its
response cross unchanged.

**Known deviation.** The relay request cap is applied after the body is buffered.
The model name decides whether a request relays, and the name is in the body, so
the smaller relay cap cannot gate the read. A body above the cap returns 413
without opening a provider connection, and the global 32 MB limit still bounds
the read. Closing the gap needs a streaming classifier, which is not worth its
complexity before the cap is observed to matter.

**Not yet implemented.** Relay produces no terminal generation event, so relayed
traffic is absent from usage until step 2. The OpenAI routes, workspace fallback
settings, the request override, and reporting remain as described below.

## Scope

Relay OpenAI and Anthropic requests using customer provider keys only. Keep
billing for our hosted models. Add automatic provider fallback using a request
override or a workspace default for the matching provider. Report open-model
call share and estimated serving savings.

No platform provider credentials, external-provider charges, invoice settlement,
provider credit controls, or external cost reconciliation are required. Provider
usage is optional reporting data, not a Gradiated financial obligation.

Capture, training, evaluation jobs, automatic quality routing, private adapter
publication, and fleet changes are outside this build. Reporting uses terminal
metadata through the existing Valkey-to-worker path. No prompts, responses, or
provider keys are persisted. No ClickHouse client is added to the gateway.

## Identity and credentials

Every request requires a valid Gradiated workspace key. Proxy access is available
to every active workspace. There is no proxy enable flag or workspace allowlist. A provider key remains
part of the request identity, even when the requested model is hosted by us.
It is available for fallback during that request only. A Gradiated bearer key
can also accompany a provider key in `x-api-key`. Header position does not
determine the provider.

| Route | Customer provider credential | Gradiated credential |
| --- | --- | --- |
| Anthropic Messages | `x-api-key: <customer-anthropic-key>` | `x-gradiated-api-key: grad_...` |
| OpenAI Chat Completions or Responses | `Authorization: Bearer <customer-openai-key>` | `x-gradiated-api-key: grad_...` |
| Hosted inference without fallback | No provider key | A `grad_` key in the standard header or `x-gradiated-api-key` |

“Provider key with us” means a key supplied on this request. This build does not
add saved provider keys, a credential vault, or an account connection flow.
Never store provider keys in workspace JSON, Valkey, events, logs, or traces.
One `extract_credentials` function returns the Gradiated key and an optional
provider credential with a `Provider` enum. It recognizes `grad_` keys and the
`sk-ant-` and `sk-` provider namespaces. Recognition is not authentication.
Valkey validates the Gradiated key; the provider validates its own key. Before
relay, the route must match the extracted provider. Reject unknown namespaces
and ambiguous provider credentials. Accept matching Gradiated keys across
different headers. Reject duplicate, conflicting, empty, or malformed headers. Run-token
syntax is reserved and cannot become a provider key. Internal calls never relay.

## Workspace settings and request override

Add a described, strict Zod schema for `workspaces.proxy_settings` JSONB:

```json
{
  "fallback_models": {
    "anthropic": null,
    "openai": null
  }
}
```

Each value is null or one exact provider model ID. Both default to null. No task
contains a fallback field. The workspace policy revision is stored separately.
Use the existing workspace management route with an expected revision. Project
the complete effective policy to Valkey before reporting success. Preserve
unrelated workspace settings. Reject unknown properties and invalid types.

Proposed request override: `x-gradiated-fallback-model: <exact-provider-model>`.
It applies to one request and never changes workspace settings. Reject duplicate
or malformed values. Strip it before upstream dispatch. An explicitly supplied
invalid override returns an error; it never silently selects the default.

Resolution order:

1. Use the request override if supplied.
2. Otherwise use `fallback_models[route_provider]` from the workspace policy.
3. If neither exists, fallback is unavailable.
4. Fallback also requires the matching provider key on the current request.

A workspace default alone never authorizes use of a platform account. A missing
provider key does not stop healthy hosted inference; it makes fallback
unavailable. An explicit fallback override without a provider key returns
`provider_key_required` before dispatch. A direct frontier request without its
provider key also returns that error.

Validate provider family and protocol compatibility without requiring a price.
Use the existing admitted provider model rules and an explicit compatibility
registry where necessary. Do not require a PostgreSQL model row for every
customer-key model ID. Unknown prices must not block relay or saving a default.
The provider remains authoritative for whether a model exists and the key can
use it. Saving a default does not prove provider access.

## Routing and fallback

| Request or condition | Action |
| --- | --- |
| Exact frontier model, with or without a task label | Relay that exact model with the customer key; ignore fallback selection for routing |
| Known task with a ready hosted production target | Serve that target |
| Known active task without a production target | Use the effective fallback if its key is present; otherwise return the local unavailable error |
| Known hosted model or task target with no healthy deployment before dispatch | Use the effective fallback if its key is present; otherwise return the local unavailable error |
| Exact private version | Preserve exact identity; no provider fallback |
| Unknown model/task, archived resource, tenant denial, invalid input, insufficient hosted balance, or missing policy state | Return the local error; never fallback |
| Hosted request already dispatched | Return its result or error; do not start a provider call |
| Provider error or invalid provider key | Return the error; do not retry, change model, or change account |

Workspace defaults authorize automatic fallback for hosted base-model requests
and task requests. This is an explicit exception to exact hosted-model behavior.
Private version requests remain exact. Direct frontier calls never switch to
open models. A task label is optional attribution, not a routing instruction.
A task slug as `model` selects the task production target.

For this build, automatic fallback happens only before hosted dispatch. A
runtime 429, cold-load failure, timeout after dispatch, or partial output does
not trigger it. This avoids two potentially billable executions for one call.
A later post-dispatch fallback policy needs a separate attempt/accounting design.

Snapshot the effective provider, fallback model, fallback source (`request` or
`workspace`), workspace revision, optional task revision, and requested target.
Never use another workspace's default or stale-on-error policy. Validate input
and protocol before selecting fallback. Do not use fallback to bypass admission
or parameter errors. Fallback uses the original provider-protocol request, not
a hosted translation. Replace only its top-level model value. Preserve all
other bytes with a tested bounded token-span replacement. Reject duplicate
model keys. Never leak a task slug upstream.

Expose requested and served model, route kind, and fallback reason in response
metadata and terminal events. Preserve the provider's own response model. A
single generation has one selected execution path and one terminal record.

## Transport and accounting boundary

Branch before the current hosted translation in `gateway/src/http.rs`. Keep
direct relay bodies unchanged. Preserve streams, provider status, errors, tools,
and cancellation. Use bounded memory and finite connect, header, idle, and total
deadlines from GW-03. Use fixed provider origins. Reject redirects. Strip
hop-by-hop headers, cookies, Gradiated headers, and unrelated credentials.
Never send a provider key to a hosted runtime or a different provider.

Provider relay uses proxy permits and active-workspace/account checks. It is
exempt from Gradiated balance charging and prepaid balance gating. A denied
hosted balance is not a fallback trigger. Hosted serving retains its current
admission, price snapshot, and atomic settlement. Select the route before billed
hosted admission; the no-deployment decision itself never creates a charge.

All relayed generations have `billing_mode = exempt`,
`exemption_reason = provider_relay`, and zero Gradiated charge. Keep observed
provider usage for reporting when available. Missing usage stays null. No
provider usage estimate can create a balance transaction. Exempt finalization
must be idempotent and cannot debit the customer. Keep bounded shared-stream
backpressure so relay telemetry cannot starve billed hosted finalization.

Price data is optional analytics metadata. Use reviewed public provider prices
with a source and effective revision for estimates only. A missing or incomplete
price produces an unknown estimate. It never blocks relay. Customer provider
invoices and discounts remain outside Gradiated accounting.

## Open-model share

Use the customer label “Open-model calls.” Here, open model means a model with
available weights that Gradiated hosts, including its private trained variants.
It does not claim that every model has an unrestricted open-source license.
Store a catalog classification; never infer it from a model name or price.

A call is one customer generation that reached dispatch and has a terminal
record. Internal evaluation/training calls, token counting, model listings,
pre-dispatch rejections, and health checks are excluded. Failed and cancelled
calls that reached dispatch count because they consumed a routing decision.
Show their outcomes separately. Retries within one generation count once.

```text
open_model_share = 100 * open_model_calls / dispatched_customer_calls
```

Both counts use the same workspace, time range, task, and key filters. Use
terminal completion time and a half-open UTC interval `[from, to)`, consistent
with existing usage. An empty denominator returns null, not zero percent.
Unknown model classification remains in the denominator and has a separate
count. Show classification coverage beside the share when it is incomplete.

Deduplicate terminal records by generation ID before every aggregate. Conflicting
records are excluded with a data-quality alert. Do not multiply calls through
joins to prices or tasks. Report separate counts for direct frontier calls,
provider fallback calls, hosted base calls, and private trained-model calls.

This is a share of recorded calls. Process loss can remove a terminal record
under the existing gateway contract. Show ingestion delay and monitoring gaps;
do not claim a complete traffic ledger during those periods.

## Savings method, version 1

Calculate savings for successful calls served by an open model with an effective
customer-key fallback, with or without a task. Each needs
complete authoritative serving usage, an exact customer charge, and a frozen
frontier fallback price. The request override or workspace default selects the
replacement baseline for the route provider. It is
separate from the evaluation reference. Requests with no baseline remain in
usage totals but have no savings value.

Version 1 uses a same-token price comparison. Apply the fallback's standard
uncached input and output rates to the observed open-model token counts. This
is an estimate, not a replay of the frontier model. Different tokenizers,
response lengths, reasoning, caching, and negotiated discounts can change the
real alternative cost. Do not send a second frontier call to calculate savings.

Only enable this method for text calls whose usage can be mapped without double
counting to total input and total output. Include reasoning exactly once when
it is part of output. Do not transfer open-model cache hits to the frontier
baseline. Exclude media, tool execution fees, tiered prices, or other dimensions
that the version 1 estimator cannot represent. Record an exclusion reason.

```text
baseline_i = input_tokens_i * fallback_uncached_input_price_i
           + total_output_tokens_i * fallback_output_price_i
savings_i = baseline_i - gradiated_charge_i
estimated_savings = sum(savings_i over eligible open-model calls)
savings_percent = 100 * estimated_savings / sum(baseline_i over the same calls)
savings_coverage = 100 * eligible_open_calls / successful_open_calls
```

Prices use nano-USD per token. Perform all money arithmetic with checked
integers. Round only for display. Return signed money strings and nullable
percentages. A zero baseline has no savings percentage. Preserve negative
savings and show “Estimated extra cost” when the aggregate is negative.
Never average call-level percentages.

Freeze price revision, workspace policy revision, optional task revision,
fallback source, baseline model, usage mapping, and method
version per generation. New prices or a changed fallback affect future calls
only. The worker derives savings from this immutable metadata. No request body
is needed. Do not derive old baselines from the workspace's current settings.

For provider calls, estimate customer provider spend from observed usage and published price snapshots,
with separate coverage. Do not claim that this matches a customer invoice.
Provider calls generate no open-model savings. Failed and cancelled calls stay
in the charge totals but are excluded from the successful-call savings cohort.
Show that cohort explicitly; do not present it as total account cost reduction.

Synthetic acceptance example: 100 recorded calls include 60 open-model calls
and 40 provider calls. Open-model share is 60%. If 50 open-model calls have a
$10 estimated baseline and a $3 Gradiated charge, savings are $7, or 70%, for
those 50 calls. If all 60 open calls succeeded, savings coverage is 83.33%.
The other 10 calls remain unknown; they do not receive zero-cost estimates.


## Data, API, and console

| Owner | Changes |
| --- | --- |
| PostgreSQL | Workspace proxy JSON and revision; minimal tasks with production target but no fallback; optional public price metadata |
| Valkey | Complete workspace policy and task/model projections; no provider secrets |
| Rust event | Requested/served identity, dispatch outcome, route kind, provider, fallback source/reason, revisions, nullable usage and baseline price snapshot |
| Worker and ClickHouse | Deduplicated terminal metadata, billable/exempt separation, versioned estimates and unknown reasons |
| API | Workspace settings, minimal task management, extended workspace usage and generation routes |
| Console | Provider defaults in workspace settings; task production target; usage share, estimates, coverage, and generation details |

Reuse the existing workspace `/usage` and `/generations` routes, tenant checks,
93-day query bound, pagination, and generated client. Add optional task and route
filters. Every card, chart, and table uses the same filtered cohort. Keep signed
savings separate from unsigned hosted charges. Preserve old event meanings and
show unknown historical classifications or baselines rather than inventing them.

Show open-model share, Gradiated hosted charges, estimated customer-provider
spend, and estimated serving savings as separate values. Display estimate
coverage and ingestion freshness. Show null metrics as unavailable, not zero.
A daily chart separates hosted open-model calls and provider calls. Generation
detail explains the requested target, served target, and fallback reason.

Workspace settings show one fallback field for Anthropic and one for OpenAI.
Show the SDK credential headers and request override. The task page has no
fallback editor. A task usage breakdown can show the effective baseline from
individual calls, which can differ because of request overrides or policy
changes. It must not claim that a task owns that baseline.

## Build sequence

1. **Anthropic customer-key relay.** Add strict credential classification, the
   workspace authorization, and the bounded transport before hosted translation.
   Verify stream/non-stream bytes, errors, cancellation, and key isolation.
2. **Terminal usage separation.** Add compatible event readers and an idempotent
   exempt event path. Verify zero provider debits, deduplication, unknown usage,
   and unchanged hosted billing. Keep the existing stream key where possible.
3. **OpenAI customer-key relay.** Add Chat Completions and Responses using the
   same transport. Verify protocol-specific headers, usage, streams, and errors.
   Qualify model listings and Anthropic token counting separately.
4. **Workspace fallback.** Add typed JSON settings, revision checks, projection,
   request override, and pre-dispatch resolution. Cover no key, no default,
   override precedence, provider mismatch, policy races, and exact-version rules.
5. **Minimal task integration.** Add or connect task identity, workspace, slug,
   production target, status, and revision. No fallback or training fields.
   Verify taskless hosted fallback and unpromoted task fallback both work.
6. **Usage and savings.** Add optional price snapshots, estimator, API fields,
   cards, chart, and details. Verify the synthetic example, negative savings,
   nulls, duplicate/late events, old schema versions, and tenant isolation.
7. **Release checks.** Add SDK examples, edge header tests, disable controls,
   bounded customer-key provider smoke tests, and release verification.

Each step ends with focused tests and a local demonstration. Release only after
the transport and reporting checks pass. No per-workspace enablement is required. The first complete release
includes relay, fallback, and usage reporting. Capture and training are not
prerequisites. Do not implement platform-funded relay or a provider billing
catalog as a hidden foundation.

## Code ownership and verification

Use `product/packages/contracts` for described schemas and generated fixtures.
Use `product/services/gateway` for identity, transport, resolution, and terminal
finalization. Keep workspace/task services, projections, ingestion, and usage
queries inside `product/packages/control`. Extend existing API routes and the
console workspace, task, and usage pages through the generated client.

Update canonical architecture, data model, and product instructions alongside
implementation. Scope the provider-routing exception to this contract. Do not
restore the removed gateway deployment-capacity leases; the runtime owns hosted
capacity admission. Do not implement capture paths from the larger training
contract as part of this proxy build.

Run DevEx, focused Rust and TypeScript tests, generated-contract checks, and
`git diff --check`. Run gateway format, Clippy, and tests before completing a
code slice. Use synthetic fixtures and a local HTTP test provider first. Cover
provider 401/429/5xx, missing usage/prices, duplicate headers/model keys, memory
limits, slow streams, disconnects, state outages, and projection races.

Before real provider tests, define exact models, customer-key spend cap, request
count, timeout, and cleanup. No paid calls or production enablement are part of
this plan change. Proposed unmeasured release targets are less than 25 ms p95
gateway overhead under qualified load, usage visible within 60 s p95, and a
93-day usage query below 2 s p95 on the qualified dataset. These are not SLAs.

Monitor routing outcomes, transport errors, unknown usage, estimate coverage,
and ingestion lag. Do not put keys or arbitrary task/model names in metric
labels. Disable new relay dispatch during rollback; keep terminal ingestion and
hosted settlement running. Provider price-feed failure affects estimates only.

Done means a customer can relay with their key, get automatic fallback from a
request override or provider-specific workspace default, and inspect open-model
share and estimated savings. It works without a task, stored provider keys,
external-provider accounting, capture, or training.
