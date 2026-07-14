# Implementation path ownership registry

Status: canonical parallel-write contract

This registry turns [the work packages](WORK_PACKAGES.md) into mechanically disjoint repository scopes. Paths are planned roots and may be created by the owning packet. A packet may read any repository file but writes only its row plus its issue/task/handoff evidence. If a required edit falls under another row, the current owner provides a proposal/fixture and the path owner integrates it.

## 1. Shared-file rules

- `DB-00` is the sole writer of `product/packages/db/src/schema/**` and `product/packages/db/migrations/**`. Domain packets place migration requirements and failing fixtures under their own test path; DB-00 integrates them serially.
- `FND-01` is the sole writer of generated contract output. Consumers change schema source only through FND-01 ownership or a contract issue.
- `API-00` owns the route registry/generator; resource packets own disjoint route module directories and cannot change registry semantics.
- `INFRA-04` owns chart templates and Argo application roots. Service packets own chart value-schema proposals under their service tests/docs; the infrastructure integrator lands chart changes.
- `OPS-00` owns shared workflow files. Packets own reusable test scripts under their path and submit workflow requirements to OPS-00.
- `LAUNCH-03` owns the final launch index/risk register. Earlier launch packets own independent evidence directories.
- Root/product/infra/research README, handoff and architecture indexes are changed only by the wave integrator after packet commits.
- Active `research/factory/**` work keeps its current issue owner. RF rows below become claimable only after that workstream explicitly hands off compatible paths.

## 2. Foundation and local development

| Packet | Exclusive writable paths |
| --- | --- |
| FND-00 | `/package.json`, `/pnpm-workspace.yaml`, `/pnpm-lock.yaml`, `/Cargo.toml`, `/Cargo.lock`, `/rust-toolchain.toml`, root formatter/linter/tool-version configs |
| FND-01 | `product/proto/**`, `product/generated/contracts/**`, `tools/contracts/**` |
| FND-02 | `product/schemas/inference/**`, `product/fixtures/contracts/inference/**`, `tools/inference-schema/**` |
| FND-03 | `product/packages/testkit/**`, `product/crates/testkit/**`, `product/fixtures/pbt/**`, `tools/pbt/**` |
| FND-04 | `product/packages/config/**`, `product/packages/observability/**`, `product/crates/config/**`, `product/crates/observability/**` |
| DEV-00 | `tools/grad/**`, `compose.yaml`, `mprocs.yaml`, `product/fixtures/local/**` |

## 3. PostgreSQL, domain and control API

| Packet | Exclusive writable paths |
| --- | --- |
| DB-00 | `product/packages/db/**` including all schema and migrations |
| CP-00 | `product/packages/domain/src/kernel/**`, `product/packages/domain/src/ports/**`, `product/packages/authz/**` |
| CP-01 | `product/packages/domain/src/tenancy/**`, `product/apps/control/src/application/tenancy/**` |
| CP-02 | `product/packages/domain/src/keys/**`, `product/packages/domain/src/policy/**`, `product/apps/control/src/application/keys/**` |
| CP-03 | `product/packages/domain/src/deletion/**`, `product/apps/control/src/application/deletion/**`, `product/apps/control/src/roles/deletion/**` |
| CP-04 | `product/packages/domain/src/catalog/**`, `product/apps/control/src/application/catalog/**`, `product/apps/control/src/roles/release/**` |
| API-00 | `product/packages/api-contract/**`, `product/apps/control/src/http/kernel/**`, `product/openapi/**`, `tools/openapi/**` |
| API-01 | `product/packages/auth/**`, `product/apps/control/src/http/routes/auth/**`, `product/apps/control/src/http/middleware/auth/**`, `product/apps/control/src/adapters/mail/**` |
| API-02 | `product/apps/control/src/http/routes/{organizations,members,workspaces,keys,billing,models,usage,traces,recommendations}/**` |
| API-03 | `product/apps/control/src/mcp/**`, `product/generated/mcp/**`, `tools/mcp/**` |

## 4. Web console

| Packet | Exclusive writable paths |
| --- | --- |
| WEB-00 | `product/apps/web/src/{app,components,lib,styles}/**`, web build/test configs |
| WEB-01 | `product/apps/web/src/features/{onboarding,organizations,workspaces,keys,members}/**` |
| WEB-02 | `product/apps/web/src/features/{billing,models,usage}/**` |
| WEB-03 | `product/apps/web/src/features/{traces,recommendations,deletion}/**` |

## 5. Money, admission and reconciliation

| Packet | Exclusive writable paths |
| --- | --- |
| BILL-00 | `product/packages/domain/src/billing/**`, `product/apps/control/src/application/billing/ledger/**`, `product/apps/control/src/adapters/billing/postgres/**` |
| BILL-01 | `product/apps/control/src/application/billing/topups/**`, `product/apps/control/src/adapters/stripe/**`, `product/apps/control/src/http/routes/webhooks/stripe/**` |
| BILL-02 | `product/valkey/{kernel,organization}/**`, `product/apps/control/src/adapters/valkey/publisher/**`, `product/services/gateway/src/adapters/valkey/**` |
| BILL-03 | `product/apps/control/src/roles/financial/**`, `product/apps/control/src/application/billing/{consumer,reconciliation,rebuild}/**` |

## 6. Public gateway and direct providers

| Packet | Exclusive writable paths |
| --- | --- |
| GW-00 | `product/services/gateway/src/{server,lifecycle,canonical,errors}/**`, `product/crates/gateway-core/**`, gateway crate manifests |
| GW-01 | `product/services/gateway/src/{auth,catalog}/**` excluding BILL-02 Valkey adapter |
| GW-02 | `product/services/gateway/src/{admission,metering,settlement}/**` |
| GW-03 | `product/services/gateway/src/protocol/models/**` |
| GW-04 | `product/services/gateway/src/protocol/responses/**` |
| GW-05 | `product/services/gateway/src/protocol/messages/**` |
| GW-06 | `product/crates/provider-core/**`, `product/services/gateway/src/providers/{openai,anthropic}/**` |
| INT-00 | `product/tests/e2e/paid-direct/**`, `product/fixtures/e2e/paid-direct/**` |

## 7. Traces and intelligence

| Packet | Exclusive writable paths |
| --- | --- |
| TRACE-00 | `product/services/gateway/src/traces/**`, `product/crates/trace-envelope/**` |
| TRACE-01 | `product/apps/control/src/roles/intelligence/persistence/**`, `product/apps/control/src/adapters/traces/{s3,kms,valkey}/**` |
| TRACE-02 | `product/apps/control/src/application/traces/**`, `product/apps/control/src/roles/trace-access/**`, `product/apps/control/src/application/analytics/**` |
| REC-00 | `product/packages/domain/src/recommendations/**`, `product/apps/control/src/application/recommendations/**`, `product/apps/control/src/roles/intelligence/evaluations/**` |

## 8. Bundles, runtime, router, cells and fleet

| Packet | Exclusive writable paths |
| --- | --- |
| BUNDLE-00 | `product/schemas/artifacts/model-stack-bundle/**`, `product/crates/inference-core/src/bundle/**`, `product/fixtures/contracts/bundles/**` |
| IR-00 | `product/services/inference-router/**` |
| CELL-00 | `product/services/cell-agent/src/{enrollment,identity,supervisor,connection}/**` |
| CELL-01 | `product/services/cell-agent/src/{scheduler,cache}/**`, `product/fixtures/cells/cache/**` |
| CELL-02 | `product/services/cell-agent/src/topology/**`, `product/fixtures/cells/multinode/**` |
| RUNTIME-00 | `product/services/runtime-stock/**`, `product/fixtures/runtime/stock/**` |
| RUNTIME-01 | `product/services/runtime-custom/**`, `product/schemas/artifacts/runtime-component/**`, `product/fixtures/runtime/custom/**` |
| FLEET-00 | `product/services/fleet-planner/**`, `product/crates/fleet-core/src/{target,lease,planner}/**` |
| FLEET-01 | `product/services/fleet-driver/src/{controller,sweeper,drivers/fake}/**`, `product/crates/fleet-core/src/driver/**` |
| FLEET-02 | `product/services/fleet-driver/src/drivers/native-primary/**`, `product/fixtures/providers/native-primary/**` |
| FLEET-03 | `product/services/fleet-driver/src/drivers/managed-kubernetes/**`, `product/fixtures/providers/managed-kubernetes/**` |
| FLEET-04 | `product/services/fleet-driver/src/drivers/<approved-provider>/**`, `product/fixtures/providers/<approved-provider>/**` |
| INFRA-03 | `product/services/enrollment/**`, `infra/modules/{cell-connect,private-ca,cell-artifact-role}/**`, `infra/tests/cells/**` |

`FLEET-04` replaces `<approved-provider>` in its issue before claiming paths; two FLEET-04 issues cannot claim the same provider directory.

## 9. Research and qualification

| Packet | Exclusive writable paths after active-factory handoff |
| --- | --- |
| RF-00 | `research/factory/src/grad_research/{domain,application,adapters/postgres}/**`, `research/factory/tests/domain/**` |
| RF-01 | `research/factory/src/grad_research/{workflows,activities}/**`, `research/factory/tests/workflows/**` |
| RF-02 | `research/factory/src/grad_research/harnesses/**`, `research/factory/tests/harnesses/**` |
| RF-03 | `research/factory/src/grad_research/{bundles,evidence}/**`, `research/factory/tests/{bundles,evidence}/**` |
| RF-04 | `research/factory/src/grad_research/portfolio/**`, `research/factory/tests/portfolio/**` |
| QUAL-00 | `research/factory/src/grad_research/qualification/**`, `research/factory/tests/qualification/**`, `product/fixtures/qualification/**` |

## 10. Distribution

| Packet | Exclusive writable paths |
| --- | --- |
| DIST-00 | `product/integrations/customer-gateways/**`, `product/tests/integrations/customer-gateways/**` |
| DIST-01 | `product/packages/domain/src/distribution/**`, `product/apps/control/src/application/distribution/**`, `product/apps/control/src/http/routes/distribution/**`, `product/valkey/channel/**` |
| DIST-02 | `product/integrations/openrouter/**`, `product/tests/integrations/openrouter/**` |

## 11. AWS and Kubernetes infrastructure

| Packet | Exclusive writable paths |
| --- | --- |
| INFRA-00 | `infra/bootstrap/**`, `infra/modules/state/**`, `infra/live/_root/**`, `infra/tests/bootstrap/**` |
| INFRA-01 | `infra/modules/{vpc,dns,acm,waf,cloudfront,public-alb}/**`, `infra/live/*/{network,edge}/**`, `infra/tests/network/**` |
| INFRA-02 | `infra/modules/{aurora,valkey,s3,ecr,kms,secrets,ses,cloudwatch}/**`, `infra/live/*/data/**`, `infra/tests/data/**` |
| INFRA-04 | `infra/modules/eks/**`, `infra/charts/{control,web,gateway,inference-router,fleet,enrollment,cell-agent,shared-library}/**`, `infra/gitops/{bootstrap,applications,environments/nonprod,environments/staging}/**`, `infra/policies/kubernetes/**`, `infra/live/*/compute/**`, `infra/tests/{eks,helm,gitops}/**` |
| INFRA-05 | `infra/modules/temporal/**`, `infra/charts/{temporal,research-*}/**`, `infra/live/*/research/**`, `infra/tests/research/**` |

`INFRA-04` and `INFRA-05` chart roots are disjoint by chart directory. The infrastructure integrator owns shared chart-library/schema changes.

## 12. Delivery, operations and launch

| Packet | Exclusive writable paths |
| --- | --- |
| OPS-00 | `.github/workflows/**`, `.github/actions/**`, `tools/release/**`, `infra/gitops/releases/**` |
| OPS-01 | `infra/observability/{dashboards,alerts,slos}/**`, `product/observability/**` |
| OPS-02 | `infra/policies/security/**`, `infra/tests/security/**`, `docs/security/**` |
| OPS-03 | `docs/runbooks/**`, `infra/tests/recovery/**`, `tools/recovery/**` |
| LAUNCH-00 | `product/tests/acceptance/**`, `docs/launch/product/**` |
| LAUNCH-01 | `product/tests/qualification/{financial,protocol}/**`, `docs/launch/financial-protocol/**` |
| LAUNCH-02 | `product/tests/qualification/{owned,research}/**`, `docs/launch/owned-research/**` |
| LAUNCH-03 | `docs/launch/{README.md,RISK_REGISTER.md,GO_LIVE.md}`, `infra/gitops/production/**` release declaration only |

## 13. Claim-time check

Before implementation, the agent expands braces/placeholders into literal paths and records them in its task claim. The wave integrator rejects a claim when:

- any active claim owns an ancestor, descendant or generated output of the proposed path;
- the packet dependency commit/contract digest is absent;
- a shared-file edit lacks the named integrator owner;
- a migration/chart/workflow edit bypasses its serialized owner;
- the packet attempts to write a historical evidence document as implementation authority.

Completion records the exact changed paths. Any unclaimed path in a packet commit is an integration failure even when tests pass.
