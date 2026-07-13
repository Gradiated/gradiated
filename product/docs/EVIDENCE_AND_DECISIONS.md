# Evidence and decisions

Evidence labels follow the repository contract: vendor-reported, analytical, derived, inferred, synthetic, or measured. This planning artifact made no live provider request and spent $0.

## Accepted decisions

| Decision | Rationale | Evidence class |
| --- | --- | --- |
| Direct prepaid gateway is the seed; provider listings are distribution. | Direct traffic creates immediate revenue/customer feedback; one serving surface avoids duplicate metering and protocol work. | Analytical product decision. |
| Vite React console plus separate Hono Node API and worker. | Clean static/app separation, Hono native Request/Response fits tRPC fetch adapter, and financial/webhook workers remain explicit. | Vendor-reported framework capability plus analytical design. |
| tRPC only for first-party UI; REST/OpenAPI for webhooks/public management. | End-to-end TS ergonomics without making external customers depend on private router types. | Analytical. |
| Product owns organization/workspace membership; auth library owns users/sessions. | Prevents competing tenant authorities and keeps role policy in domain/database tests. | Analytical. |
| Organization is the customer/billing root; workspaces isolate keys, models, limits, and usage. | Matches the requested commercial hierarchy and OpenRouter's documented logical separation without creating funded sub-wallets. | User requirement plus vendor-reported reference plus analytical. |
| Every organization receives a Default workspace. | Makes simple onboarding unchanged while allowing later isolation. | User requirement plus OpenRouter vendor-reported pattern. |
| PostgreSQL organization ledger is the financial source of truth; Redis is durable serving projection/event transport. | Durable append-only audit/rebuild plus one low-latency atomic gateway dependency. | User requirement plus analytical distributed-systems design. |
| Redis is the gateway's only internal dependency and admission fails closed. | No unmetered provider cost can be created when balance/event durability is uncertain. | User requirement plus analytical risk control. |
| Low-credit cap is organization-wide and calculated after reserve; workspace/key caps are nested. | Avoids stale flags and cross-workspace bursts spending the same remaining credit while preserving workspace control. | Derived design. |
| Internal shared contracts use Protobuf/Buf; public inference uses OpenAPI/JSON fixtures. | Protobuf gives TS/Rust generation and compatibility checks, while public JSON/SSE presence/union semantics need exact wire fixtures. | Vendor-reported tooling plus analytical. |
| PBT is mandatory in TS and Rust, with portable minimized traces. | Billing/admission are concurrent state machines; generated sequences and shrinking expose edge cases agents will miss with examples alone. | User requirement; vendor-reported framework capabilities; analytical test design. |
| Real providers run only in protected CI; fake official-client tests run on every PR. | Verifies live compatibility without exposing secrets to untrusted code or making CI expensive/nondeterministic. | Analytical security/test decision. |

## Source-backed framework facts

- Hono documents runtime adapters and native web request/response behavior: [Hono getting started](https://hono.dev/docs/getting-started/basic). Vendor-reported.
- tRPC's fetch adapter accepts native `Request` and returns native `Response`, fitting a Hono route: [tRPC fetch adapter](https://trpc.io/docs/server/adapters/fetch). Vendor-reported; exact glue must be integration-tested.
- shadcn/ui publishes a Vite setup: [shadcn Vite installation](https://ui.shadcn.com/docs/installation/vite). Vendor-reported.
- Buf provides configured code generation; generation versions/configuration must be pinned: [Buf generate](https://buf.build/docs/reference/cli/buf/generate/). Vendor-reported.
- fast-check supports command-based model testing, scheduled async execution, shrinking, and replay data: [fast-check model-based testing](https://fast-check.dev/docs/advanced/model-based-testing/). Vendor-reported.
- proptest state-machine exposes reference/SUT transitions, invariants, shrinking, and timeouts: [proptest state machines](https://proptest-rs.github.io/proptest/proptest/state-machine.html). Vendor-reported.
- OpenRouter currently publishes provider model metadata and routing-performance behavior: [provider integration](https://openrouter.ai/docs/guides/community/for-providers). Vendor-reported and time-sensitive.
- OpenAI and Anthropic publish official TypeScript SDKs and changing model catalogs: [OpenAI SDK](https://github.com/openai/openai-node), [OpenAI models](https://developers.openai.com/api/docs/models/gpt), [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-typescript), [Anthropic model choice](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model). Vendor-reported and time-sensitive.

## Falsifiable architecture hypotheses

1. A single durable Redis dependency can keep p95 gateway overhead below 25 ms while atomically reserving organization credit, nested workspace/key limits, leasing, and appending an event. Measure with real Redis and representative cross-workspace concurrency; do not infer from in-memory tests.
2. `appendfsync everysec` plus replication and fencing gives an acceptable acknowledged-write loss envelope when coupled with reconciliation. Validate managed-service failover and restore; change persistence/architecture if loss exceeds risk tolerance.
3. Conservative max-cost reservation can cover supported provider behavior without making small balances unusable. Measure reserve utilization and overage frequency per model/protocol.
4. PostgreSQL plus Redis Streams is sufficient at seed volume. Track posting lag, stream memory, reconciliation time, and write load; introduce a separate durable bus/analytics store only outside the gateway path when thresholds are measured.
5. Protocol compatibility and owned-model economics are enough for external gateway distribution. Test against source-dated conformance and a bounded soak before application.

## Known uncertainties

- Redis managed-service persistence/failover semantics differ; the deployment provider is undecided and must be experimentally qualified.
- Exact accounting account names, revenue recognition, tax, refunds, and unclaimed balances require professional accounting/legal review.
- Stripe product/currency/geography requirements and fraud thresholds need launch-market decisions.
- Current cheapest real-smoke model IDs and SDK behavior will change; protected environment configuration must be reviewed monthly.
- Provider-reported usage may arrive only at stream completion or be absent after failures; adapters need scope-matched conservative estimation evidence.
- OpenRouter onboarding backlog, commercial terms, and acceptance are externally controlled.
- A secondary analytics store may become necessary; no evidence yet justifies adding it to seed.

## Rejected alternatives

- Provider integration only: delays direct billing/customer learning and makes us dependent on external acceptance.
- A second durable queue in the gateway: violates the one-internal-dependency requirement and adds another partial-failure transaction; Redis Streams is the seed event transport.
- Gateway-to-PostgreSQL balance checks: creates hot-path coupling and cannot safely handle bursts without a separate atomic reservation mechanism.
- Credit on payment redirect: forgeable/racy and not evidence of settled payment.
- Boolean-only low-credit flag: stale under concurrent spend; calculated post-reserve organization mode is safer.
- Independently funded workspace wallets: create transfer/allocation complexity and stranded balances; hard workspace budgets against shared organization credit satisfy the current need.
- Shared TypeScript-only schemas: does not provide idiomatic checked Rust generation or wire compatibility discipline.
- Protobuf as the OpenAI/Anthropic public wire model: likely loses JSON field presence, unions, and streaming semantics.
- Examples-only billing tests: insufficient for duplicate, reorder, crash, race, and long command-sequence behavior.

## Evidence update protocol

Implementation/experiment reports must state model/provider/region/runtime/version, test seed/trace, workload, budget, dates, raw artifact paths, and evidence label. A result from one model, deployment, or provider is not transferred to another without a fresh test. Negative integration and billing outcomes remain durable artifacts.
