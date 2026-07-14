# Verification, acceptance and launch matrix

Status: canonical whole-system quality contract

This matrix proves that implementation packages compose into the product described in [the system manual](../SYSTEM_MANUAL.md). A passing unit test is not evidence for another layer, scope or failure mode. Every result records commit, fixture/schema digest, environment, seed, timing and evidence class.

## 1. Test tiers

| Tier | Trigger | Dependencies | Budget | Purpose |
| --- | --- | --- | --- | --- |
| T0 static | every change | none | minutes | format, lint, type, schema, dependency boundaries, secret scan |
| T1 deterministic | every change | local fakes | minutes | examples, regressions and bounded PBT |
| T2 integration | every change/main | Testcontainers/MinIO/fakes | bounded | real PostgreSQL/Valkey/protocol/state interaction |
| T3 system fake | main | complete Compose/Kind fake stack | bounded | end-to-end customer/failure journeys |
| T4 protected external | main/release/scheduled | real cheapest model/AWS/GPU/Stripe test account | explicit hard cap | compatibility and managed-service/provider claims |
| T5 staging qualification | promotion | production-shaped staging | preregistered | load, fault, recovery, security and operations |

T4/T5 jobs fail closed when required for promotion and credentials are absent. Optional scheduled probes report a classified skip. Untrusted changes receive no external credentials or mutation authority.

## 2. Language and framework requirements

| Surface | Unit | Property/state | Integration |
| --- | --- | --- | --- |
| TypeScript control/web | Vitest | fast-check command models | Testcontainers, MSW/fakes, Playwright |
| Rust gateway/router/fleet/cell | nextest | proptest, proptest-state-machine | real Valkey/PostgreSQL where applicable, fake providers/cells |
| Python research | pytest | Hypothesis | Temporal test server, fake compute/S3/ECR, tiny PyTorch runtime |
| contracts | Buf/OpenAPI/JSON Schema lint | cross-language generated sequences | golden fixtures and generated client/MCP |
| Terraform/Helm | fmt/validate/lint/test/policy | generated scenario/negative policy cases | Kind and isolated plan/apply rehearsal |

Every property failure writes seed, shrink path and canonical replay input. `grad test replay <artifact>` must reproduce it without external secrets.

## 3. Capability coverage ledger

| Capability | Authority | Primary packet | Required proof | Launch blocker |
| --- | --- | --- | --- | --- |
| identity/session/recovery | Better Auth/PostgreSQL | API-01 | cookie/CSRF/session lifecycle | yes |
| recovery/invitation email | PostgreSQL token/invitation + SES transport | API-01/INFRA-02 | fake send/retry/non-enumeration and SES configuration | yes |
| organization/Default workspace | PostgreSQL | CP-01 | model-based tenancy invariants | yes |
| members/invitations/RBAC | PostgreSQL | CP-01/API-01 | cross-role/cross-tenant matrix | yes |
| workspace policy/model allowlist | PostgreSQL/Valkey projection | CP-02 | version/policy sequence PBT | yes |
| API key create/revoke/expiry | PostgreSQL/Valkey projection | CP-02/GW-01 | display-once/digest/revoke race | yes |
| self-service organization deletion | PostgreSQL workflow | CP-03 | crash/refund/purge/revoke PBT | yes |
| control REST/OpenAPI/client/docs | Zod route registry | API-00/02 | description/drift/black-box client | yes |
| MCP | allowlist + REST | API-03 | OAuth/tool parity/no direct DB | no for direct API; yes before MCP launch |
| prepaid top-up | PostgreSQL ledger | BILL-01 | signed duplicate/reorder webhook | yes |
| ledger/balance | PostgreSQL | BILL-00 | balanced/rebuild/overflow PBT | yes |
| reserve/settle/limits | Valkey scripts | BILL-02/GW-02 | real-Valkey state model | yes |
| billing posting/reconciliation | PostgreSQL + Valkey stream | BILL-03 | crash/redelivery/rebuild | yes |
| Models | Valkey release projection | GW-03 | catalog isolation/shape | yes |
| Responses | public JSON fixtures | GW-04 | official client fake/real | yes |
| Messages | public JSON fixtures | GW-05 | official client fake/real | yes |
| direct OpenAI/Anthropic | immutable direct release | GW-06 | exact identity and malformed stream | at least one provider required; both are seed target |
| encrypted trace capture | S3 ciphertext + PG metadata | TRACE-00/01 | secret fuzz/crash/idempotency | yes for Product Intelligence |
| no-retention | gateway policy | TRACE-00/CELL-01 | no payload persistence + cache isolation | yes |
| trace detail/delete | PostgreSQL auth + S3 | TRACE-02 | grant race/cross-tenant/crypto delete | yes |
| PostgreSQL usage analytics | PostgreSQL | TRACE-02 | query plan/SLO/tenant bounds | yes |
| recommendations/evaluations | PostgreSQL | REC-00 | authority/budget/no-auto-switch | no for first paid slice |
| immutable release/alias | PostgreSQL | CP-04 | activation/canary/rollback PBT | yes before Grad launch |
| inference router | in-memory authenticated registry | IR-00 | exact digest/churn/cancel | yes before Grad launch |
| cell enrollment/runtime | PostgreSQL tokens/PCA + bundle | CELL-00 | identity/attestation/runtime fault | yes before Grad launch |
| KV/prefix cache | ephemeral cell state | CELL-01 | cross-scope noninterference | yes before Grad launch |
| SQL fleet/planner | PostgreSQL | FLEET-00 | lease/budget/concurrency PBT | yes before Grad launch |
| provider driver/cleanup | PostgreSQL + provider | FLEET-01/02 | lifecycle/orphan suite | yes before provider use |
| runtime adapter/custom component | signed runtime image/bundle | RUNTIME-00/01 | oracle, streaming/metering/cache and ABI/hardware checks | yes before Grad launch |
| multi-node | exact topology bundle | CELL-02 | partial/member-loss/cleanup | yes before public owned inference |
| research domain/workflows | PostgreSQL + Temporal | RF-00/01 | state/budget/replay/cleanup | yes before always-on research |
| bundle/reproducibility | S3/ECR digest | BUNDLE-00/RF-03 | canonical rebuild/signature | yes before Grad launch |
| independent qualification | qualification report | QUAL-00 | known-bad/positive exact scopes | yes before Grad launch |
| human promotion | catalog release authority | RF-04/CP-04 | signed approval and rollback | yes before Grad launch |
| customer gateway recipes | config fixtures | DIST-00 | black-box supported profiles | no for direct launch |
| OpenRouter native channel | channel ledger/gateway | DIST-01/02 | exposure/metering/partner conformance | yes before listing |
| AWS/EKS/data/GitOps | Terraform/Argo | INFRA packets | plan/policy/failover/rebuild | yes for production |
| security/observability/DR | code + runbooks | OPS packets | negative reachability, alerts, drills | yes for production |

## 4. Property and state-machine suites

### 4.1 Tenancy and authorization

Generate users, organizations, memberships, roles, workspaces, invitations, keys, session expiry and concurrent commands. Prove:

- exactly one Default workspace per organization and it cannot be deleted;
- only a non-Default workspace can be archived; archival is terminal, revokes its keys and preserves attributed evidence;
- organization owner/admin workspace visibility and explicit non-admin workspace membership;
- no query/mutation returns or affects another organization;
- last owner cannot be removed or demoted;
- revoked/reissued/expired invitation tokens cannot create membership and concurrent acceptance has one effect;
- revoked/expired membership invalidates current authorization, not just the next login;
- key secret is returned once and never recoverable;
- organization deletion removes every former access path.

### 4.2 REST/OpenAPI/MCP

Generate route manifests and nested schemas. Prove:

- operation IDs and method/path pairs are unique;
- all request/response/error/field schemas are described and example-valid;
- bounded usage CSV preserves tenant/time/row limits, deterministic order and spreadsheet-formula escaping without creating export state;
- runtime and generated-client validation agree;
- sensitive operations never enter MCP allowlist;
- every MCP tool maps to one REST operation and uses OAuth actor context;
- unknown mutation fields and malformed cursors/idempotency keys fail consistently.

### 4.3 Ledger and top-ups

Generate top-up, webhook, usage, refund, chargeback, correction and duplicate/reorder/crash commands. Prove:

- entries balance to zero in USD;
- unique business event has one effect;
- balance projection equals ledger reconstruction;
- immutable entries never update/delete;
- checked arithmetic never wraps;
- conflicting duplicate suspends/alerts instead of overwriting;
- checkout intent alone never creates credit.

### 4.4 Admission and settlement

Generate balances, limits, keys, releases, concurrent reserves, streams, cancellations, provider usage, lease expiry and projection changes. Prove:

- no accepted reservation exceeds organization credit/channel exposure;
- workspace/key monthly and concurrency limits compose with organization account;
- low balance applies fixed stricter organization cap;
- accepted reservation atomically contains event/hold/concurrency/lease;
- each reservation reaches one terminal state;
- duplicate equal reserve/settle is idempotent and conflicting input fails;
- actual over reserve closes account and preserves evidence;
- billing stream cannot be evicted by trace backlog.

### 4.5 Protocol and provider streams

Generate legal canonical item/event sequences, provider chunk boundaries, retries, malformed chunks, usage omissions, timeouts and cancellation. Prove:

- parse/encode round trip preserves supported semantics;
- unsupported semantics fail before reserve;
- direct release never changes provider/model/version;
- retry occurs only before usable output and within release/deadline/buy-risk bounds;
- one public terminal response and one settlement result;
- provider body/secrets are absent from errors/logs/artifacts.

### 4.6 Traces and retention

Generate data mode, retention, payload shapes, secret markers, stream/object/DB failures, grants, membership changes and deletion races. Prove:

- no-retention emits no payload envelope/object/wrapped key;
- Product Intelligence ciphertext decrypts only through authorized one-use path;
- trace backlog can shed without affecting billing correctness;
- duplicate envelope converges; conflicting digest alerts;
- key destruction makes payload inaccessible before object cleanup;
- expiry/deletion/tombstone prevents reads after restore;
- KV/prefix cache remains enabled and isolated for every retention class.

### 4.7 Release and routing

Generate releases, qualifications, stable/canary aliases, health sets, sessions and rollback. Prove:

- activation requires exact valid non-expired qualification;
- alias deterministic assignment is stable for a generation;
- request remains on admitted digest through projection changes;
- health removes but never invents endpoint/cell membership;
- Grad never routes direct or across effort/speed;
- rollback stops new bad assignments while preserving in-flight identity/price.

### 4.8 Fleet and multi-node

Generate target changes, planner races, provider unknown outcomes, resource/member events, interruption and cleanup. Prove:

- one active lease owner/epoch performs each allocation transition;
- target maximum, hourly budget and concentration are never exceeded;
- all required members must be ready before cell publication;
- partial allocation rolls back all acquired resources;
- required member loss fences the complete cell;
- delete completes only after every member/resource absence is proven;
- uncertain cleanup freezes new source acquisition and independent sweep converges;
- router never observes ranks or provider resource identity.

### 4.9 Research and promotion

Generate hypotheses, campaigns, immutable specs, run outcomes, artifact failure, qualification and approval. Prove:

- campaign/run never exceeds budget/deadline/authority;
- Temporal retries do not duplicate side effects;
- negative result remains durable evidence;
- claims do not transfer across model/workload/hardware/intervention scope;
- bundle digest covers every production-relevant artifact/topology;
- qualification cannot be self-approved by experiment writer;
- no autonomous state transition moves public alias without signed human approval.

## 5. Whole-system E2E scenarios

Every scenario runs with synthetic payloads. The `fake` variant is required on main. A protected variant is required only where listed.

| ID | Scenario | Fault/variant | Required assertions |
| --- | --- | --- | --- |
| E2E-01 | first organization activation | concurrent create/retry | one org/owner/Default workspace/audit/outbox |
| E2E-02 | Stripe top-up | duplicate/reordered/conflicting webhook | one balanced credit and monotonic Valkey snapshot |
| E2E-03 | key lifecycle | revoke during requests | new admission stops inside projection objective; existing request settles |
| E2E-04 | funded Responses non-stream | fake and protected OpenAI client | exact model, reserve before upstream, usage/ledger/UI agree |
| E2E-05 | funded Responses stream | cancel before/after usable output | protocol terminal and settlement/credit policy correct |
| E2E-06 | funded Messages non-stream | tool use/result | native shape and exact provider identity |
| E2E-07 | funded Messages stream | fragmented/malformed provider stream | bounded retry/error and exactly one settlement |
| E2E-08 | insufficient/low balance | concurrent burst | no overspend; fixed low-balance cap; useful error |
| E2E-09 | workspace/key monthly and concurrency limits | clock/window boundary | atomic combined policy and no independent wallet |
| E2E-10 | Valkey unavailable/unknown script result | failover/partition | fail closed, recover idempotently, no unreserved upstream |
| E2E-11 | financial worker crash | before DB commit/after commit/before ack | one usage/charge; pending entry recovers |
| E2E-12 | Product Intelligence trace | S3/DB/ack crash | one ciphertext/object row; authorized detail only |
| E2E-13 | no-retention request | warm prefix reuse | no durable payload; isolated cache hit allowed |
| E2E-14 | trace delete/expiry | concurrent read and restored backup fixture | key revocation wins; no post-delete plaintext |
| E2E-15 | recommendation evaluation | budget stop and failed quality | ordinary traffic unchanged; evidence/stop visible |
| E2E-16 | organization deletion | cancel, crash each stage, reconciliation block | suspension/refund/purge/revoke/pseudonymization invariant |
| E2E-17 | direct provider outage | eligible pre-output retry and post-output failure | exact identity, retry bound, one terminal charge |
| E2E-18 | Grad single-node request | cell churn | exact digest and cache scope; router removes stale cell |
| E2E-19 | Grad multi-node request | missing/failed member | no partial readiness; whole cell fenced; exact fallback cell only |
| E2E-20 | provider allocation | timeout/unknown create/preemption/delete | idempotent observe/recovery and zero orphans |
| E2E-21 | research experiment | worker crash/cancel/budget stop | replay, evidence and cleanup; no alias movement |
| E2E-22 | bundle promotion | known-bad qualification and rollback | bad blocked; approved exact digest canary; prior pointer restores |
| E2E-23 | customer gateway recipe | each advertised gateway config | workspace accounting equals direct request |
| E2E-24 | OpenRouter channel | duplicate request/statement mismatch | channel exposure/accounting isolated and reconciled |
| E2E-25 | Aurora outage/restore | control unavailable while gateway serves | bounded serving, queued posting, restored ledger integrity |
| E2E-26 | EKS rebuild | delete/recreate cluster | managed state survives; Argo restores exact digests |
| E2E-27 | certificate/secret rotation | overlap and compromise revoke | no new use of old identity; live safe transition |
| E2E-28 | protected paid-provider budget | missing secret and hard cap | fail/skip classified; no cap escape or payload artifact |

## 6. Load and SLO hypotheses

Initial targets are promotion gates only after a dated production-shaped measurement. Tests report distributions, not a single average.

| Surface | Initial target | Test shape |
| --- | --- | --- |
| gateway availability | 99.9% monthly excluding exact upstream outage | multi-AZ fault/load model |
| gateway added p95 latency | less than 25 ms regional excluding provider/client upload | sustained stream/non-stream mix |
| healthy funded reserve success | 99.99% | real qualified Valkey under target concurrency |
| suspension projection | p95 less than 10 s; hard less than 30 s | publish-to-reject timestamps |
| top-up projection | p95 less than 30 s after verified webhook commit | webhook/outbox/Valkey path |
| usage posting | p95 less than 30 s, p99 less than 2 min | mixed request duration and consumer restart |
| bounded usage query | p95 less than 500 ms at seed retention/cardinality | `EXPLAIN ANALYZE` fixture and concurrency |
| trace searchable | p95 less than 30 s after completion | stream/S3/PG path |
| alias rollback projection | p95 less than 30 s; canary halt less than 2 min | bad release synthetic signal |
| Grad release availability | 99.9% where qualified capacity exists | interruption/cell churn model |
| Aurora recovery | RPO at most 5 min, RTO at most 30 min | isolated restore drill |
| Valkey acknowledged write | target RPO at most 1 s; no forgotten admitted liability | failover and conservative rebuild |
| trace delete | 100% logical/cryptographic cutoff within published command target | grant/read/delete race and object sweep |

If PostgreSQL analytics misses its target, first inspect query/index/partition/rollup options. ClickHouse requires the documented measured trigger and a new ADR; agents do not add a dormant adapter.

## 7. Security verification matrix

| Boundary | Positive proof | Negative proof |
| --- | --- | --- |
| browser -> control | valid secure session and CSRF flow | wrong origin, fixation, expired membership rejected |
| MCP -> REST | OAuth PKCE user/org token calls allowlisted route | no DB/KMS/Stripe grant; destructive tool absent |
| client -> gateway | valid workspace/channel credential | malformed/dual-conflict/revoked key rejected before reserve |
| gateway -> dependencies | Valkey, exact provider/router only | no Aurora/Stripe/KMS decrypt/K8s/provider lifecycle route |
| financial role | ledger/stream/Stripe operations | no trace decrypt/GPU acquisition/release publication |
| trace-access | one grant/one object decrypt | no bucket list/ledger/catalog/provider access |
| inference router | mTLS exact cell stream | no DB/K8s/provider lifecycle/trace/ledger access |
| fleet driver | one provider API + fleet rows | no customer ingress/Stripe/trace decrypt/Private CA issue |
| cell | artifacts/router/required telemetry | no customer key/balance/provider lifecycle/trace decrypt |
| research/evaluator | scoped artifacts/compute/domain commands | evaluator cannot modify evidence source or alias |
| GitHub CI | OIDC scoped environment role | fork receives no secret or cloud mutation |

Automated reachability runs from each workload identity where practical. IAM policy simulation alone is not sufficient for network proof.

## 8. Infrastructure qualification

| Component | Required evidence before production |
| --- | --- |
| Terraform state | lock contention, version recovery, least privilege and protected destructive plan |
| VPC/edge | three-AZ route/reachability, WAF bounds, streaming timeout and DDoS/rate behavior |
| Aurora | failover, PITR restore, transaction pool saturation and ledger/tenant invariants |
| Valkey | exact commands/scripts, synchronous acknowledged-write behavior, failover, noeviction, headroom and load latency |
| EKS | private access, Pod Identity, NetworkPolicy, AZ/node/pod disruption, upgrade and rebuild |
| EKS Auto Mode | placement, disruption, identity, policy and cost; otherwise use managed node groups |
| Argo/Helm | digest-only desired state, schema/policy, sync/rollback and no dynamic business objects |
| KEDA | metric outage fallback, static floors, max saturation and no admission semantic effect |
| Temporal | deterministic replay/versioning, DB backup/restore, cancellation and serving isolation |
| Kueue/JobSet | quota/coordinated job behavior only when a real job consumes them |
| Private CA | one-use enrollment, short-lived rotation/revoke and exact attestation binding |
| provider driver | budget/tag/idempotency/interruption/cleanup/orphan evidence per provider/region/resource class |

## 9. Recovery drills

Each drill has incident commander, hypothesis, blast radius, synthetic data, abort condition, timestamps, reconciliation query, expected alarms, rollback and issue output.

Required before paid direct production:

- Aurora restore and application reconnect;
- Valkey failover, uncertain reservation handling and full projection rebuild;
- financial stream lag/pending/poison recovery;
- gateway/control AZ loss;
- Stripe outage/duplicate/refund/chargeback;
- organization deletion/refund/payload purge;
- trace cryptographic delete and KMS denial;
- EKS rebuild and GitOps restore;
- direct release rollback and key/secret rotation.

Required before public owned inference:

- router loss and cell reconnect;
- single/multi-node preemption/member loss;
- provider unknown create/delete and independent zero-orphan sweep;
- cell certificate compromise/revocation;
- bundle/runtime rollback and cache cold start;
- Temporal workflow crash/replay and research GPU cleanup.

## 10. Evidence artifact format

Every nontrivial integration/load/fault/paid test writes a small content-safe report:

```json
{
  "schema_version": 1,
  "test_id": "E2E-10",
  "commit": "<sha>",
  "contract_digests": {},
  "environment": "fake|staging|provider-name",
  "scope": {},
  "seed": "<optional>",
  "started_at": "<UTC>",
  "completed_at": "<UTC>",
  "result": "passed|failed|blocked|skipped",
  "evidence_class": "synthetic|measured|vendor-reported",
  "assertions": [],
  "cost_micros": 0,
  "cleanup": "confirmed|not-applicable|uncertain",
  "artifact_refs": []
}
```

Reports contain no secret, request body, provider response body or private customer data. Large logs remain ephemeral unless a redacted excerpt is decision-relevant.

## 11. Release gates by product stage

### Stage A — Internal fake demo

- W0-W4 packets complete against fakes.
- E2E-01 through E2E-13 fake variants pass.
- No production/cloud claim is made.

### Stage B — Bounded paid direct beta

- tenancy, money, reserve/settle, Responses/Messages for advertised providers, trace/no-retention and deletion blockers pass;
- protected model-provider tests and accounting/security/legal review pass;
- AWS data/edge/EKS, observability, recovery and on-call gates pass;
- owned Grad and native channel entries remain hidden if their gates are incomplete.

### Stage C — Public Grad-owned inference

- immutable bundle/research/qualification/catalog chain passes;
- one single-node and one multi-node exact topology pass even if only one is customer-visible initially;
- external provider margin, availability, interruption, identity and zero-orphan evidence passes;
- exact-release rollback and cache isolation pass.

### Stage D — OpenRouter native listing

- channel principal/exposure/ledger/statement isolation passes;
- exact advertised OpenRouter protocol/catalog profile passes;
- signed commercial, privacy, security, support and reconciliation gates pass;
- Grad public gateway remains the admission/metering boundary.

## 12. Final completeness review

Before declaring the startup plan implementable, reviewers answer yes with a source link for every subsystem:

- Is the customer/actor and successful outcome explicit?
- Are all inputs bounded, described and versioned?
- Is each durable and ephemeral fact assigned one authority?
- Are idempotency, retry, timeout, cancellation and duplicate behavior explicit?
- Are money, identity, data-policy and exact-model invariants fail closed?
- Are security/IAM/network/secret boundaries explicit?
- Are metrics, alerts and operator actions explicit and payload-safe?
- Is local/fake verification possible without owner action?
- Is protected external proof scoped and budgeted?
- Are migration, mixed-version deployment, rollback and cleanup explicit?
- Does a work packet own every implementation path without overlap?
- Is any “optional” field/service actually absent until a named trigger?

Any “no” is an architecture defect, not an implementation detail for a junior agent to invent.

Paid launch is limited to jurisdictions approved by legal/accounting for prepaid inference credit. Stripe receipts are the seed payment document; tax registration, invoices and customer tax IDs are not guessed into the schema. If an approved launch jurisdiction requires them, that requirement blocks paid launch there and receives a separate contract/migration packet.
