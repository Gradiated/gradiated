# Proxy feature: implementation plan

Status: step 1 is implemented in `product/services/proxy` and is not deployed.
The proxy relays any request that carries a customer provider key and does not
name a hosted model, and forwards every other request to the gateway. Its unit and end-to-end suites pass. Fallback,
the relay usage record, capture and reporting are not implemented. The gateway
still contains the earlier Anthropic relay; step 3 removes it.

This plan owns proxy scope, topology and build order. It supersedes earlier
proposals for platform-funded provider calls, task-owned fallback settings and
a relay inside the gateway. Supporting transport rules are in
[GW-01 through GW-05](TASK_FINE_TUNING_GATEWAY_CONTRACT.md).

## Decisions

| Decision | Choice |
| --- | --- |
| Topology | A separate proxy service receives all public inference traffic and forwards hosted requests to the gateway. |
| Proxy scope | Authenticate relays, read `model`, choose a destination, forward bytes, fall back, and copy bytes for capture. Nothing else. |
| Availability target | 99.99% for each calendar month for the proxy, measured as below. |
| Billing on relay | None. A relay has no balance check, no price lookup and no charge. |
| Identity on relay | The Gradiated key is required. The proxy reads PostgreSQL through an in-process cache with a stale grace window. |
| Fallback trigger | A gateway failure that is ours, before the first response byte reaches the customer. |
| Balance and rate-limit errors | Pass through. They are policy, not failure. |
| Traces | A `traces` table apart from `generations`, joined by `generation_id`. |

Proposed values that need measurement before release are marked as proposed.

## Topology

```text
customer ── ALB ──> proxy ─┬─ hosted model ──> gateway ──> runtime
                           ├─ provider model with key ──> provider
                           └─ gateway failed before first byte ──> provider (fallback)
```

The proxy is the only public inference target. The gateway becomes an internal
ClusterIP service that serves hosted models only. The proxy changes rarely; the
gateway can change often without a risk to relayed traffic.

A fallback inside the gateway process cannot survive a gateway crash, an
out-of-memory kill, a bad deploy or a bad dependency. That is why the proxy is a
separate service and does not share a process or a deploy with the gateway.

Customers with no provider key and no fallback model gain nothing from the
proxy, and their path has two services in series. The proxy must therefore stay
small enough that its own failure rate is close to zero.

## Proxy scope

The routing rule: with a provider key, a request can relay to that key's
provider, and it does unless it names a model in our hosted catalog. Without a
provider key it goes to the gateway. When the gateway fails in a
fallback-eligible way, the proxy falls back. The key alone picks the provider,
so the proxy has no list of paths or provider models: audio, images, files and
endpoints that do not exist yet relay unchanged.

The proxy does these steps for each request, in this order:

1. Read the body within the byte budget.
2. Find the top-level `model` value with one scan. A body that is not JSON, or
   has no single `model`, names no hosted model. Leave every byte unchanged.
3. Choose the destination:
   - A provider key and no hosted model: authenticate the Gradiated key, then
     relay the same method, path, query and bytes to the key's provider.
   - Anything else: forward to the gateway, which owns every local error.
4. Stream the response back. Drop the upstream request when the customer
   disconnects.

The only path the proxy knows is the gateway's own `/health` and `/metrics`,
which it refuses until the gateway serves them on an admin port of its own. The
proxy's own health, readiness and metrics use a separate admin port.

The proxy does not do billing, balance checks, translation, tokenization,
admission, usage parsing or trace construction. It has no Valkey or ClickHouse
client. It shares no crate with the gateway, so a gateway change never rebuilds
it.

## Identity and credentials

Every relayed request requires a valid Gradiated workspace key. A hosted request
is authenticated by the gateway only, so the proxy does no identity work on the
hosted path. Proxy access is available to every active workspace. There is no
proxy enable flag or workspace allowlist.

| Route | Customer provider credential | Gradiated credential |
| --- | --- | --- |
| Anthropic Messages and token counting | `x-api-key: <customer-anthropic-key>` | `x-gradiated-api-key: grad_...` |
| OpenAI Chat Completions or Responses | `Authorization: Bearer <customer-openai-key>` | `x-gradiated-api-key: grad_...` |
| Hosted inference without fallback | No provider key | A `grad_` key in the standard header or `x-gradiated-api-key` |

The format of the credential in the standard header decides the mode. A `grad_`
key is native. A provider key is proxy mode, and the Gradiated key then comes
from `x-gradiated-api-key`. `sk-ant-` is Anthropic and other `sk-` keys are
OpenAI. Recognition is not authentication: the provider validates its own key.
Reject unknown namespaces, duplicate headers, conflicting Gradiated keys and
malformed values. A key for one provider on another provider's path relays to
the key's provider, which answers for itself. A relay keeps the provider key in
the header the client used, so OAuth tokens stay in `Authorization`.

The proxy never sends a provider key to the gateway. Before it forwards a
request, it removes every `Authorization` and `x-api-key` value that is not a
Gradiated key. This rule does not depend on credential parsing, so it also
covers routes the proxy does not inspect.

"Provider key with us" means a key supplied on this request. This build does not
add saved provider keys, a credential vault, or an account connection flow.
Never store provider keys in workspace JSON, Valkey, events, logs, or traces.

### Identity cache

One PostgreSQL query reads the key, its workspace and its organization. The
proxy caches the answer in process by key digest. The raw key is never stored.

| Setting | Proposed value | Reason |
| --- | --- | --- |
| Fresh lifetime | 15 s | Revocation latency that is already accepted for the gateway. |
| Stale grace | 1 h | During a PostgreSQL failure, a known key keeps working for this long. |
| Capacity | 100,000 entries | Bounds memory; the oldest entry leaves first. |
| Concurrent loads | 32 | Bounds a flood of random keys; excess loads return 503. |

A key that the proxy has never seen cannot be authenticated during a PostgreSQL
failure. That request returns `serving_state_unavailable`. A revoked key keeps
working for up to the stale grace only while PostgreSQL is unavailable.

The hosted catalog is the set of model IDs in PostgreSQL. The proxy refreshes it
every 5 s and keeps the last good set when a refresh fails. A pod that has never
loaded the catalog is not ready. A model added a moment ago can reach a
provider until the next refresh if the request also carries a provider key; the
provider then returns its own 404.

The hosted catalog holds global hosted models only. Task slugs and private
versions are unique only within a workspace, so they must never enter it: a
global set would grow with every workspace, route one workspace's request by
another workspace's names, and reveal which private names exist. When tasks
arrive (step 7), the identity query also returns the workspace's task slugs and
private version names, cached with the identity. A request with a provider key
goes to the gateway when its model is a global hosted model or one of its own
workspace's names, and relays otherwise. A request without a provider key needs
no identity lookup, because it always goes to the gateway.

Routing by name format, such as relaying only `claude-` or `gpt-` names, was
rejected. OpenAI model names share no single prefix, so each new model family
would need a proxy release.

## Fallback contract

The proxy falls back to the effective fallback model only when all of these are
true:

1. The request targets a hosted model or a task.
2. The request carries a provider key for the route's provider.
3. A fallback model exists from the request override or the workspace default.
4. The gateway failed in a way that is ours, and no response byte has reached
   the customer.

| Gateway result | Proxy action |
| --- | --- |
| Connection refused, reset or TLS failure | Fall back |
| A streaming request with no response headers within the header deadline | Fall back |
| Any 5xx | Fall back |
| 429 marked as Gradiated capacity | Fall back |
| 404 `model_unavailable`: an operator marked the hosted model unavailable | Fall back |
| 400 `context_length_exceeded` or `unsupported_parameter`: a limit of our model that the provider may not have | Fall back |
| `insufficient_balance`, or a 429 without the capacity mark | Pass through |
| Any other 4xx: malformed request, key, tenant, unknown model | Pass through |
| Success status | Stream it; never fall back after this point |

The gateway marks a capacity 429, `model_unavailable`,
`context_length_exceeded` and `unsupported_parameter` with a response header,
`x-gradiated-fallback: allowed`. The proxy never falls back on a 4xx
without it, because 429 means both "our capacity" and "your limit".

The gateway must not send success headers until the runtime has accepted the
request and produced its first token. Queueing and cold-load failures then
arrive as error statuses that the proxy can act on. A failure in the middle of a
stream stays an error for the customer.

The header deadline applies to streaming requests only. A non-streaming hosted
response has no headers until its whole generation ends, so a short deadline
would cut healthy long generations. For those requests, fallback depends on
the gateway reporting queue and cold-load failures as statuses.

LLM inference has no side effects, so a hosted attempt followed by a provider
call can cost money twice but cannot produce a wrong result. The gateway
finalizes a replaced hosted generation as failed with zero charge. The proxy
records the fallback, its reason and the served model in the relay usage record,
and returns `x-gradiated-served-model` and `x-gradiated-fallback-reason` headers.

Fallback uses the original provider-protocol request. The proxy replaces only
the top-level `model` value with a bounded token-span replacement and keeps
every other byte. It never leaks a task slug upstream.

### Request bodies

Fallback sends the customer's original body with only the top-level `model`
value replaced. It never translates between protocols: an Anthropic Messages
request falls back to an Anthropic model, and a Chat Completions or Responses
request falls back to an OpenAI model.

Every Gradiated extension is therefore an `x-gradiated-*` request header, never a
body field, so the body stays a valid provider body. The proxy strips these
headers before any provider call. The gateway today reads `service_tier` and
`session_id` from the body. Before fallback ships, it accepts
`x-gradiated-service-tier` and `x-gradiated-session-id` headers instead. The
body fields are deprecated, and a request that still uses them cannot fall back
cleanly. OpenAI's own `service_tier` body field then reaches OpenAI unchanged.

### Thread continuity

Chat Completions, Anthropic Messages and stateless Responses carry the whole
conversation in each request, so a fallback turn has the full context. Fallback
stays per request; a thread returns to the hosted model on its next healthy
turn. Switching costs one prompt-cache miss. Stateful Responses requests
(`previous_response_id`, `conversation`) are rejected by the gateway with a 400,
so they never fall back.

A switch breaks only when the history holds content that the next provider
rejects. Measured on 2026-09-24 with `claude-sonnet-5` (adaptive thinking) and
`gpt-5.1` (`store: false`), replaying real gateway output through the proxy
(`product/services/proxy/test/live/thread-continuity.test.ts`):

| Our output replayed to the provider | Result |
| --- | --- |
| Messages: empty text block beside a tool call | 400 `text content blocks must be non-empty` |
| Messages: our reasoning as a `thinking` block with an empty signature | 400 `Invalid signature in thinking block`, in a tool loop and at a new turn |
| Messages: the same turn without both | Accepted |
| Responses: our reasoning item | 400; without `status`, 400 on `content`; as a summary, `Item with id … not found` |
| Responses: the same turn without our reasoning items | Accepted |
| Chat Completions: assistant message with `reasoning_content` | Accepted |

The other direction needs no change. Claude's signed and redacted thinking and
OpenAI's encrypted reasoning items arrive at our model, and the gateway's
translation drops them before the runtime; the proxy end-to-end suite holds this.

Neither provider accepts reasoning it did not produce, in any form. So the
gateway returns our model's reasoning only where it is portable:

- Anthropic Messages: no `thinking` blocks, and no empty text blocks.
- OpenAI Responses: no reasoning items.
- Chat Completions: `reasoning_content` stays.

Messages and Responses clients do not see our model's reasoning; Anthropic's
newest models also return empty thinking text by default.

**Known limitation: our model never sees its own earlier reasoning.** Each
request still reasons in full; only the reasoning history is lost. The
gateway's translation already strips earlier reasoning before the runtime, and
the rule above means clients cannot send it back, so this holds for every
Messages and Responses thread, not only threads that switch models. Across user
turns this matches how open models are meant to run. Within one tool loop,
interleaved-thinking models are trained to keep their earlier steps' reasoning,
so long agent loops may re-plan more and use more tokens. The size of this loss
is not measured.

A future option keeps that reasoning without breaking switching: the gateway
caches our model's reasoning for a short time, keyed by the tool call IDs it
returned, and re-inserts it when the matching tool result arrives. The client
never holds it, so the history stays portable, and a thread that returns from a
fallback within the cache window gets it back. Build it only if an agent eval
shows that in-loop reasoning improves our models enough.

### Routing rules

| Request or condition | Action |
| --- | --- |
| Exact provider model, with or without a task label | Relay that exact model with the customer key; never select a fallback |
| Known task with a ready hosted production target | Serve that target |
| Known active task without a production target | Use the effective fallback if its key is present; otherwise return the local unavailable error |
| Hosted model or task target fails in a fallback-eligible way | Use the effective fallback if its key is present; otherwise return the gateway error |
| Exact private version | Preserve exact identity; the gateway never marks its errors as fallback-eligible |
| Unknown model or task, archived resource, tenant denial, malformed input, insufficient balance | Return the local error; never fall back |
| Provider error or invalid provider key | Return the error; do not retry, change model, or change account |

Workspace defaults authorize automatic fallback for hosted base-model requests
and task requests. This is an explicit exception to exact hosted-model behavior.
Direct provider calls never switch to open models. A task label is optional
attribution, not a routing instruction. A task slug as `model` selects the task
production target.

### Circuit breaker

After repeated fallback-eligible gateway failures, the proxy skips the gateway
for a short open period and sends eligible requests straight to the provider.
It then lets a small number of probe requests through before it closes. This
prevents every request from waiting for a deadline while the gateway is down.
Requests without a fallback still go to the gateway and get its real error.

| Setting | Proposed value |
| --- | --- |
| Gateway header deadline before fallback | 10 s, then measure cold-load and queue times |
| Open after | 20 eligible failures within 10 s |
| Open period | 5 s, then half-open with 5 probes |

## Transport and accounting boundary

Relay bodies cross unchanged. Preserve streams, provider status, errors, tools,
and cancellation. Use fixed provider origins and reject redirects. A customer
never supplies an upstream URL, because that would let any key holder send
requests from inside our network. Later support for other providers and
provider regions, such as Azure OpenAI or Bedrock, uses named providers from a
reviewed allowlist, each with its own origin rule and authentication. Strip
hop-by-hop headers, cookies, Gradiated headers, edge headers and unrelated
credentials. The client's own `Accept-Encoding` reaches the provider, and a
compressed response crosses undecoded with its `Content-Encoding`.

| Limit | Proposed value | Reason |
| --- | --- | --- |
| Request body | 32 MB | Same limit as the gateway. |
| Body budget | 256 MB | Bodies are buffered to read `model` and counted as they arrive. Excess returns 503. |
| Body read | 60 s | A slow upload holds an in-flight slot. Expiry returns 408. |
| In-flight requests | 4,000 per pod | Bounds memory and sockets. |
| Provider connect | 10 s | |
| Provider response headers | 630 s | Equal to the total. The proxy never cuts a provider call before the client SDK would. |
| Idle stream | 630 s | Equal to the total, for the same reason. |
| Total request | 630 s | The official SDKs time out after 600 s. The margin is 30 s. |

**Known limitation: a request cannot run longer than 630 s.** A stream that is
still producing output at that point is cut. Most customers never reach it. A
very long output, such as a large agent turn at maximum output tokens, can. The
limit is deliberate: the pod drain window is sized from the total, so a longer
total slows every rollout and node scale-down.

A relay has `billing_mode = exempt`, `exemption_reason = provider_relay` and zero
Gradiated charge. Keep observed provider usage for reporting when available.
Missing usage stays null. No provider usage estimate can create a balance
transaction. Exempt finalization is idempotent and cannot debit the customer.
Hosted serving keeps its current admission, price snapshot and atomic
settlement in the gateway.

The proxy does not parse provider usage. It copies response bytes into the
capture queue and the collector extracts usage after the request completes. A
change in a provider's usage format therefore needs no proxy deploy.

## Availability

The target is 99.99% of each calendar month, about 4.3 minutes. The service
level indicator is the fraction of requests that did not fail because of
Gradiated, measured at the ALB. Caller 4xx errors and provider errors on
relayed calls do not count against it. The ALB's own AWS service level is also
99.99%, so this is a target for the parts we control, not an end-to-end
promise. Surviving a regional failure needs multi-region serving, which is a
separate project.

- **Placement.** At least three replicas across three availability zones, a
  PodDisruptionBudget, and a node group apart from the gateway's, so a gateway
  load spike or node failure cannot starve the proxy.
- **No hard dependency on shared state.** Readiness does not depend on
  PostgreSQL after the first catalog load. A database failure must not remove
  every pod from the load balancer. Relays keep working through the identity
  grace window.
- **Draining.** On SIGTERM, readiness fails first, the pod waits for endpoint
  removal, then stops accepting connections and lets open streams finish up to
  the total deadline. The pod grace period and the ALB deregistration delay
  match that window.
- **Gateway isolation.** A gateway outage affects hosted requests only. Relays
  and fallbacks continue.
- **Gateway deploys.** A refused connection to a terminating gateway pod is a
  fallback-eligible failure. The proxy retries once on another gateway
  connection before it falls back, because nothing was dispatched.
- **Kill switch.** An environment setting sends every request to the gateway
  and disables relay dispatch. Rolling back the ALB route to the gateway is the
  second-level rollback.

Monitor request outcomes by destination, gateway and provider error rates,
added latency, in-flight requests, identity cache stale serves, catalog age and
circuit state. Do not put keys or arbitrary model names in metric labels.
Alert on the error-budget burn rate and on catalog age.

## Capture and traces

Capture is opt-in for each workspace. The proxy copies request and response
bytes into a bounded, non-blocking queue that sends them to a separate collector
service. When the queue is full, the proxy drops the copy, never the request.
The collector owns parsing, schema, storage and retention.

The proxy creates the `generation_id` at the front door and passes it to the
gateway, so `generations` and `traces` join without guessing.

| Table | Holds | Rows |
| --- | --- | --- |
| `generations` | Facts about a call: identity, model, route, status, usage, charge, latency, fallback reason | Exactly one for each call the proxy or gateway sees. Always written. |
| `traces` | Content: messages, response, tools, and training metadata | One for each captured call, plus uploaded and imported traces. `generation_id` is nullable, and `source` is `proxy`, `hosted`, `upload` or `import`. |

Billing, usage and reporting read `generations` only. Training reads `traces`
only. The two tables have different lifecycles: billing records are immutable,
and content must expire and be deletable on request.

OpenAI and Anthropic outputs cannot be training targets. A trace from a frontier
call carries `trainable = false` for its response. Its prompt can still supply
training inputs and evaluation references.

## Rollout

1. **Local and CI.** Unit tests and the end-to-end suite pass.
2. **Deploy dark.** Deploy the proxy with no public route. Run synthetic hosted
   requests through it inside the cluster and compare with direct gateway
   results.
3. **Relay canary.** Send one design-partner workspace's relay traffic through
   the proxy with a bounded, customer-approved provider spend cap. Check stream
   bytes, errors, cancellation and latency.
4. **Weighted shift.** Move the public inference route from the gateway target
   group to the proxy target group with ALB weights: 1%, 10%, 50%, 100%. Hold
   each step long enough to see the error-budget burn rate. The rollback is the
   weight change.
5. **Gateway internal.** Remove the public route to the gateway and remove its
   relay code.
6. **Fallback.** Enable fallback for one workspace, then for every workspace with
   a fallback model.

Before real provider tests, define exact models, the customer-key spend cap,
request count, timeout and cleanup.
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
Use the existing workspace management route with an expected revision. The
proxy reads the policy from PostgreSQL through its identity cache, so a change
takes effect within the cache lifetime. Preserve unrelated workspace settings.
Reject unknown properties and invalid types.

Proposed request override: `x-gradiated-fallback-model: <exact-provider-model>`.
It applies to one request and never changes workspace settings. Reject duplicate
or malformed values. The proxy strips it before it sends the request upstream. An explicitly supplied
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
| Proxy event | Requested/served identity, dispatch outcome, route kind, provider, fallback source/reason, revisions, nullable usage and baseline price snapshot |
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

1. **Thin proxy service.** Credential extraction, the identity cache, the hosted
   catalog, routing, the gateway forward, Anthropic and OpenAI relays, limits,
   draining, metrics and the admin port. End-to-end tests run the real proxy
   and gateway binaries against PostgreSQL, Valkey, a mock runtime and a mock
   provider.
2. **Deployment.** Proxy workload, service account, database role, secret,
   node group, disruption budget, target group and the weighted route in
   Terraform and Argo manifests. Dashboards and burn-rate alerts. Rollout steps
   2 to 4.
3. **Gateway internal.** Remove the gateway's relay code and public route.
4. **Relay usage record.** Exempt generation events from the proxy through the
   existing ingestion path. Verify zero debits, deduplication, unknown usage and
   unchanged hosted billing.
5. **Fallback.** Gradiated extensions as headers, the gateway fallback header
   and first-token commit, the model swap, the circuit breaker, workspace
   settings and the request override. End-to-end tests for each row of the
   fallback table. Portable reasoning output from the gateway, held by the
   real-provider thread continuity suite.
6. **Capture.** The byte-copy queue, the collector, the `traces` table and the
   workspace opt-in.
7. **Task integration and reporting.** Task production targets, price
   snapshots, the estimator, API fields and console views.

Each step ends with focused tests and a local demonstration. No per-workspace
enablement is required for relay. Do not implement platform-funded relay or a
provider billing catalog as a hidden foundation.

## Code ownership and verification

`product/services/proxy` owns the proxy. It is a standalone Rust crate with its
own lockfile, image and tests. `product/services/gateway` owns hosted serving
and terminal finalization. Keep workspace services, ingestion and usage queries
in `product/packages/control`. Extend existing API routes and console pages
through the generated client.

Run DevEx, proxy format, Clippy and unit tests, and the proxy end-to-end suite
before completing a slice. Use synthetic fixtures and local HTTP test providers.
Cover provider 401, 429 and 5xx, duplicate headers and model keys, memory
limits, slow streams, disconnects, gateway outages, PostgreSQL outages and
draining during a stream.

Proposed release targets, not yet measured: less than 5 ms p95 added latency
for the proxy hop, usage visible within 60 s p95, and a 93-day usage query
below 2 s p95. These are not SLAs.

Done means a customer can relay with their key, get automatic fallback from a
request override or provider-specific workspace default, and inspect open-model
share and estimated savings. It works without a task, stored provider keys,
external-provider accounting, capture or training.
