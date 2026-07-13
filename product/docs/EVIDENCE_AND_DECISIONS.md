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
| The product has curated direct provider/model and first-party Grad lanes, not a marketplace. | Exact OpenAI/Anthropic/Google identities make migration easy; `grad/<effort>/<speed>` makes differentiated owned inference explicit. | User decision plus analytical product design. |
| Direct IDs never cross provider/model/version; Grad IDs never leave owned inference or change effort/speed. | Trustworthy migration requires the requested identity to mean what it says. | User strategy plus analytical reliability decision. |
| Grad uses four effort × four speed identities with immutable fixed-price releases. | Separates inference compute/quality from serving latency/capacity while preserving auditable pricing/change control. | User decision plus derived architecture. |
| OpenRouter upstream is operator-only; OpenRouter downstream lists only owned/differentiated supply. | Avoids rebuilding a broad marketplace, circular routing and undifferentiated resale while retaining distribution. | Current provider docs plus analytical commercial decision. |
| Product Intelligence retains encrypted bounded traces by default; Private/No Retention is an opt-in workspace/request mode. | Trace-derived history, analytics and migration recommendations are core product value; customers retain explicit control. | User decision plus derived security architecture. |
| Trace retention does not authorize global model training; migration never auto-switches traffic. | Product features and training/traffic control are materially different permissions. | Analytical trust boundary. |
| ClickHouse Cloud is the content-free trace analytics projection; PostgreSQL owns auth/control/money and S3 owns encrypted payloads. | Trace analytics needs high-cardinality interactive scans, while managed merge/backup deletion behavior makes ClickHouse unsuitable as the sole raw-content custodian. | Current ClickHouse vendor docs plus analytical architecture; see `CLICKHOUSE_TRACE_ANALYTICS_DECISION.md`. |
| AWS inference edge plus isolated external-provider cells is the owned Grad fleet boundary. | Representative suppliers expose different container/VM/Kubernetes APIs; a cell/lease contract pools them without putting provider lifecycle or a global Kubernetes control plane on the request path. | Current vendor docs plus analytical architecture; see `MULTI_PROVIDER_GPU_EVIDENCE_2026-07-13.md`. |
| Active and prefix KV cache remain enabled for no-retention Grad requests. | Cache is required for serving economics and can be isolated by opaque trust-domain salt while remaining ephemeral and absent from durable trace/data stores. | User requirement, current vLLM vendor docs, and derived security design. |

## Source-backed framework facts

- Hono documents runtime adapters and native web request/response behavior: [Hono getting started](https://hono.dev/docs/getting-started/basic). Vendor-reported.
- tRPC's fetch adapter accepts native `Request` and returns native `Response`, fitting a Hono route: [tRPC fetch adapter](https://trpc.io/docs/server/adapters/fetch). Vendor-reported; exact glue must be integration-tested.
- shadcn/ui publishes a Vite setup: [shadcn Vite installation](https://ui.shadcn.com/docs/installation/vite). Vendor-reported.
- Buf provides configured code generation; generation versions/configuration must be pinned: [Buf generate](https://buf.build/docs/reference/cli/buf/generate/). Vendor-reported.
- fast-check supports command-based model testing, scheduled async execution, shrinking, and replay data: [fast-check model-based testing](https://fast-check.dev/docs/advanced/model-based-testing/). Vendor-reported.
- proptest state-machine exposes reference/SUT transitions, invariants, shrinking, and timeouts: [proptest state machines](https://proptest-rs.github.io/proptest/proptest/state-machine.html). Vendor-reported.
- OpenRouter currently publishes provider model metadata and routing-performance behavior: [provider integration](https://openrouter.ai/docs/guides/community/for-providers). Vendor-reported and time-sensitive.
- OpenRouter's current documentation index spans protocols, modalities, routing variants, workspaces/budgets, privacy/logging, plugins/tools, SDKs and provider onboarding: [complete docs index](https://openrouter.ai/docs/llms.txt). Vendor-reported and time-sensitive; the grouped inventory is in `OPENROUTER_FEATURE_DECISIONS.md`.
- OpenAI and Anthropic publish official TypeScript SDKs and changing model catalogs: [OpenAI SDK](https://github.com/openai/openai-node), [OpenAI models](https://developers.openai.com/api/docs/models/gpt), [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-typescript), [Anthropic model choice](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model). Vendor-reported and time-sensitive.
- Google publishes partner/gateway guidance distinguishing native and OpenAI-compatible integration paths: [Gemini partner integration](https://ai.google.dev/gemini-api/docs/partner-integration). Vendor-reported and time-sensitive.
- ClickHouse documents [PrivateLink connectivity](https://clickhouse.com/docs/cloud/security/connectivity/private-networking), [encryption/TDE/CMEK](https://clickhouse.com/docs/cloud/security/cmek), [merge-driven TTL](https://clickhouse.com/docs/guides/developer/ttl), [lightweight-delete physical-delay behavior](https://clickhouse.com/docs/sql-reference/statements/delete), and [Cloud backups](https://clickhouse.com/docs/cloud/manage/backups/overview). Vendor-reported and time-sensitive; the dated synthesis is `CLICKHOUSE_TRACE_ANALYTICS_DECISION.md`.

## Falsifiable architecture hypotheses

1. A single durable Redis dependency can keep p95 gateway overhead below 25 ms while atomically reserving organization credit, nested workspace/key limits, leasing, and appending an event. Measure with real Redis and representative cross-workspace concurrency; do not infer from in-memory tests.
2. `appendfsync everysec` plus replication and fencing gives an acceptable acknowledged-write loss envelope when coupled with reconciliation. Validate managed-service failover and restore; change persistence/architecture if loss exceeds risk tolerance.
3. Conservative max-cost reservation can cover supported provider behavior without making small balances unusable. Measure reserve utilization and overage frequency per model/protocol.
4. PostgreSQL plus Redis Streams is sufficient for authoritative posting at seed volume, with ClickHouse outside the gateway path as a derived analytical projection. Track posting/projection lag, stream memory, reconciliation time, query load and Cloud cost; introduce a separate durable bus only when thresholds are measured.
5. Protocol compatibility and owned-model economics are enough for external gateway distribution. Test against source-dated conformance and a bounded soak before application.
6. Four effort and four speed labels are understandable and operationally monotonic. Measure selection/support, task quality by effort and TTFT/throughput/queue distributions by speed; hide cells that do not differentiate.
7. Curated direct-provider traffic can retain positive margin and produce credible Grad migration candidates. Measure workload retention, support cost, recommendation precision and experiment conversion per provider/model.
8. Default Product Intelligence retention creates more customer value than trust/activation cost. Measure opt-out/deletion, trace-feature use, recommendation conversion and security/support incidents.
9. Trace-derived replay/evaluation can identify safe Grad candidates. Measure false recommendations, evaluator disagreement, canary rollback and quality regressions; never infer equivalence from metadata alone.
10. ClickHouse Cloud improves trace UX/cost over Aurora-only reads at seed volume. Measure realistic tenant-filtered query latency/concurrency, ingestion/rebuild/delete behavior and monthly Cloud/PrivateLink cost; use the Aurora read model temporarily if it fails the ADR-0004 falsification gate.
11. A stable AWS inference edge and cell-local scheduler can preserve exact-release streaming SLOs across provider classes. Measure edge overhead, network jitter, startup, stream failure and pre/post-output retry semantics on one native and one Kubernetes provider class.
12. Diversified external spot capacity lowers effective cost per successful token after warm idle, failed starts, interruptions, transfer and egress. Reject a provider/release when measured successful-token cost or concentration fails its margin/speed gate.
13. Salted always-on prefix cache prevents cross-workspace/channel/release/retention-class reuse without destroying useful hit rate. Test timing isolation, hit/eviction, salt rotation, teardown, no-log/no-backup and abrupt preemption.

## Known uncertainties

- Redis managed-service persistence/failover semantics differ; the deployment provider is undecided and must be experimentally qualified.
- Exact accounting account names, revenue recognition, tax, refunds, and unclaimed balances require professional accounting/legal review.
- Stripe product/currency/geography requirements and fraud thresholds need launch-market decisions.
- Current cheapest real-smoke model IDs and SDK behavior will change; protected environment configuration must be reviewed monthly.
- Provider-reported usage may arrive only at stream completion or be absent after failures; adapters need scope-matched conservative estimation evidence.
- OpenRouter onboarding backlog, commercial terms, and acceptance are externally controlled.
- Public docs do not prove authenticated dashboard behavior or private provider terms; those require a human-owned onboarding checkpoint.
- Grad effort/speed thresholds, speed monotonicity and representative quality workloads are unmeasured; no cell is launch-qualified yet.
- Thirty-day default raw retention, deletion SLO and exact legal notices require security/legal review before launch.
- Recommendation quality and the fraction of direct workloads that can move to Grad are unknown.
- ClickHouse Cloud sizing, Enterprise TDE/CMEK cost, PrivateLink price/region support, and deletion/backup legal interpretation are unmeasured; ADR-0004 requires a bounded spike and preserves an Aurora-only launch fallback.
- External GPU provider capacity, interruption frequency, DPA/support access, network quality, startup distribution, host isolation, billing cleanup and successful-token economics are unmeasured; no provider is production-qualified by the architecture brief.
- The AWS inference edge direct/tunnel transport, vLLM topology, cache hierarchy and managed-Kubernetes fixed cost require implementation spikes. Multi-node, disaggregated prefill and remote cache are not seed assumptions.

## Rejected alternatives

- Provider integration only: delays direct billing/customer learning and makes us dependent on external acceptance.
- A second durable queue in the gateway: violates the one-internal-dependency requirement and adds another partial-failure transaction; Redis Streams is the seed event transport.
- Gateway-to-PostgreSQL balance checks: creates hot-path coupling and cannot safely handle bursts without a separate atomic reservation mechanism.
- Credit on payment redirect: forgeable/racy and not evidence of settled payment.
- Boolean-only low-credit flag: stale under concurrent spend; calculated post-reserve organization mode is safer.
- Independently funded workspace wallets: create transfer/allocation complexity and stranded balances; hard workspace budgets against shared organization credit satisfy the current need.
- Shared TypeScript-only schemas: does not provide idiomatic checked Rust generation or wire compatibility discipline.
- Protobuf as the OpenAI/Anthropic/Google public wire model: likely loses JSON field presence, unions, and streaming semantics.
- Examples-only billing tests: insufficient for duplicate, reorder, crash, race, and long command-sequence behavior.
- An OpenRouter feature-for-feature clone: maximizes surface area before differentiated supply/revenue is proven and makes provider mechanics the customer problem.
- OpenRouter as default upstream breadth: adds a marketplace hop and variable behavior without improving our owned inference differentiation.
- Every provider/reseller and customer-configured provider weights/fallback arrays: increases support/identity risk and undermines a curated migration lane.
- Silent parameter dropping, context transformation, response healing, or model-family fallback: apparent availability at the cost of correctness and auditability.
- Hidden owned-inference preference for a direct provider request: makes migration untrustworthy; Grad adoption must be explicit and evidence-backed.
- No payload retention by default: rejected by product direction because workload intelligence is core; retained traces require explicit controls and no-retain escape hatch instead.
- Raw payloads in ClickHouse or ClickHouse as authorization/ledger truth: rejected because content custody, immediate revocation, merge-based physical deletion and analytical mutation behavior require the PostgreSQL/S3 split.
- One Kubernetes cluster stretched across GPU providers: rejected because provider/node/network control surfaces differ and a WAN control plane enlarges blast radius.
- Karmada or a custom Cluster API provider as the universal seed fleet manager: deferred/rejected because neither replaces provider acquisition, spend, signed bootstrap, cache-aware request routing or interruption semantics.
- Disabling KV/prefix cache for no-retention: rejected; no-retention suppresses durable trace payloads while transient salted serving cache remains mandatory.

## Evidence update protocol

Implementation/experiment reports must state model/provider/region/runtime/version, test seed/trace, workload, budget, dates, raw artifact paths, and evidence label. A result from one model, deployment, or provider is not transferred to another without a fresh test. Negative integration and billing outcomes remain durable artifacts.
