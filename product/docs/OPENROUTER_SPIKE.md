# OpenRouter product and architecture spike

Date: 2026-07-13. Scope: official public documentation only; no account login, network benchmark, API key, or paid request. Evidence is vendor-reported unless marked as inference/recommendation.

## Executive answer

OpenRouter does not appear to provision a separate network gateway/base URL for each environment. It presents one shared API surface and selects a logical workspace from the API key. Inside one organization/account, workspaces isolate keys and configuration while credits and billing are unified.

Its hierarchy closely matches the revised product direction:

```text
organization/account
  shared credits, billing, global policies, management keys, activity
  ├── Default workspace (all organization members)
  │     keys, budgets, guardrails, routes, presets, BYOK, observability
  ├── Production workspace
  │     independent keys and stricter policy
  └── Development workspace
        independent keys and lower limits/models
```

Our recommendation is the same logical topology: one highly available gateway URL; organization-funded shared credit; API keys bound to one workspace; configurable workspace/key limits and model/routing policy. Do not create separate Rust deployments per workspace. Physical regional gateway pools are an operator concern and all enforce the same Redis-projected policy.

## What OpenRouter actually scopes

OpenRouter says workspaces can represent teams, applications, or environments under one account and each has independent API keys, guardrails, BYOK, routing, presets, plugins, observability integrations, members, and budgets. It creates/retains a Default workspace, automatically adds organization members to it, and keeps credits/billing plus activity/logs and account-level privacy/model/provider policy above workspaces. [Workspace overview](https://openrouter.ai/docs/guides/features/workspaces/overview).

| Level | Vendor-reported behavior | Implication for us |
| --- | --- | --- |
| Organization/account | Shared credits/billing, membership/roles, cross-workspace activity, management keys, global privacy/provider/model constraints. | Organization is customer and ledger boundary. |
| Default workspace | Existing configuration starts here; organization members automatically have access. | Create atomically with organization; safe onboarding path. |
| Workspace | Keys, members, routing, presets, BYOK, observability, guardrail, interval budgets. | Workspace is policy, credentials, usage attribution, and limits boundary. |
| Member/key | More restrictive guardrails and key credit caps can layer beneath workspace/global policy. | Later add member policy; seed needs key limits and workspace policy. |
| Request | Model fallback list and provider order/allowlist/privacy/performance preferences can override only inside enforced policy. | Request routing is constrained by effective policy, never a bypass. |

OpenRouter organization docs describe a shared credit pool and organization-funded usage. [Organization management](https://openrouter.ai/docs/cookbook/administration/organization-management). This supports—though does not prove the implementation of—organization-level top-ups with workspace attribution.

## Keys and administration

- Every inference key belongs to a workspace; admins can create workspace-owned system keys, while members can create their own keys in workspaces they belong to. [Workspace overview](https://openrouter.ai/docs/guides/features/workspaces/overview).
- Key metadata includes `workspace_id`, optional credit limit/reset, usage windows, disabled state, and expiry. [Get API key](https://openrouter.ai/docs/api/api-reference/api-keys/get-key).
- Separate management keys perform administrative operations and cannot invoke completions. They can manage keys and workspaces across an account. [Management keys](https://openrouter.ai/docs/guides/overview/auth/management-api-keys).
- OpenRouter notes that extra keys do not multiply platform rate limits; capacity is governed globally/model-by-model. [Limits](https://openrouter.ai/docs/api/reference/limits).

Recommendation:

- seed inference keys are workspace-owned service keys by default, with creator/audit metadata;
- organization management keys are phase 2 but use a separate credential class/scope from inference keys;
- key limits may be daily/weekly/monthly/lifetime and always combine with workspace and organization constraints using the strictest effective result;
- creating keys never creates another credit pool.

## Budgets and hard prepaid safety

OpenRouter documents workspace daily, weekly, monthly, and lifetime budgets. It checks configured budgets before routing, but explicitly says already in-flight requests can cause slight overage. Budget limits must decrease from lifetime to monthly to weekly to daily. [Workspace budgets](https://openrouter.ai/docs/guides/features/workspaces/workspace-budgets).

This is useful UX, but not sufficient for our prepaid risk model. Our gateway will reserve maximum cost atomically against:

1. organization spendable credit;
2. organization low-credit concurrency;
3. workspace period budget remaining and workspace concurrency;
4. API-key period limit remaining and key concurrency, when set.

Active reservations count against every relevant limit. Therefore concurrent requests cannot all pass a stale “spent so far” check. Workspace budgets are caps on use of the shared organization pool, not preallocated sub-balances. A budget change does not move money.

## Guardrails and effective policy

OpenRouter guardrails can carry spend limits, model/provider allowlists, ZDR, prompt-injection checks, sensitive-information actions, and custom content filters. Account, workspace, member, and key rules compose so stricter restrictions win: model/provider allowlists intersect, ZDR enforcement combines, filters accumulate, and budgets are independently checked. [Guardrails](https://openrouter.ai/docs/guides/features/guardrails/overview).

Recommended seed policy lattice:

```text
effective models/providers = organization allowlist ∩ workspace allowlist ∩ key allowlist
effective max output/reserve = minimum of all configured maxima
effective concurrency = minimum applicable cap, plus organization low-credit cap
effective spend permission = all organization/workspace/key balance-window checks pass
effective privacy = most restrictive organization/workspace requirement
```

Ship workspace model/provider allowlists, output/reserve/concurrency limits, and period budgets first. Defer content scanning and per-member inference guardrails until evidence supports their complexity. The policy contract should be extensible, not a wholesale clone.

## Routing and reusable configurations

OpenRouter supports ordered model fallbacks, provider ordering/allowlists, optional fallback disablement, parameter-capability checks, privacy/ZDR restrictions, and sorting/filtering by price, throughput, or latency. [Provider selection](https://openrouter.ai/docs/guides/routing/provider-selection), [model fallbacks](https://openrouter.ai/docs/guides/routing/model-fallbacks).

Presets are workspace-scoped, versioned configurations containing model selection/fallbacks, provider routing, system prompts, and generation parameters. They can be referenced like `@preset/slug` and updated without deploying application code. [Presets](https://openrouter.ai/docs/guides/features/presets).

Recommendation:

- seed: workspace routes/model aliases containing allowed models, ordered targets, fallback policy, and stable config version;
- expose request overrides only where workspace policy explicitly permits;
- add versioned presets after the paid vertical path; avoid storing system prompts until privacy/retention controls exist;
- include an “effective route preview” in the dashboard, similar in spirit to eligibility preview, so admins see the models/providers a key can actually use.

## BYOK and observability

OpenRouter scopes BYOK credentials to workspaces, supports multiple credentials per provider, priority/fallback behavior, and filters by model, OpenRouter key, or member. [BYOK](https://openrouter.ai/docs/guides/overview/auth/byok). Workspaces can also have separate observability destinations or share one across workspaces. [Workspace overview](https://openrouter.ai/docs/guides/features/workspaces/overview).

Recommendation:

- BYOK is phase 2, after prepaid metering is stable; it changes which costs count against our credit/limits and needs explicit fee semantics;
- retain provider credential ownership at organization level with explicit workspace grants if customers want reuse, rather than duplicate encrypted secrets;
- seed telemetry is internal/dashboard only; customer-configured external exporters follow payload/privacy controls.

## Feature comparison and seed priority

| Capability | OpenRouter | Our seed decision |
| --- | --- | --- |
| One gateway URL | Shared API endpoint; key implies workspace (inferred from docs/examples). | Yes. No per-workspace deployment/base URL. |
| Organization credit pool | Unified credits/billing across workspaces. | Yes; PostgreSQL organization ledger/top-ups. |
| Default workspace | Yes; organization members automatically included. | Yes; created in same DB transaction as organization. |
| Multiple workspaces | Yes. | Yes. |
| Workspace keys | Yes, including workspace-owned system keys. | Yes, service keys first. |
| Workspace budgets | Daily/weekly/monthly/lifetime; may overrun in flight. | Yes, but reservations make them hard concurrent caps. |
| Per-key spend limits | Yes. | Seed or immediate follow-on; schema/admission supports it from day one. |
| Workspace model/provider policy | Yes via guardrails/routing. | Yes: allowlists, routes, fallback and max-output/reserve. |
| Organization policy ceiling | Yes. | Yes: workspace/key can only restrict. |
| Presets | Versioned model/provider/prompt/parameter configs. | Phase 2 after routes; no prompt persistence in seed. |
| BYOK | Per-workspace and filterable. | Phase 2. |
| Customer observability integrations | Per workspace/shared. | Phase 2. |
| Content guardrails/plugins/routers | Broad feature set. | Defer; not needed to validate paid inference. |
| Management API keys | Separate admin-only credential. | Phase 2; design scopes now. |

## Revised domain model

```text
User
Organization
OrganizationMembership(user, organization, org_role)
Workspace(organization, is_default, status, policy, limits)
WorkspaceMembership(user, workspace, workspace_role)
ApiKey(organization, workspace, owner_kind, scopes, limits)
OrganizationLedgerAccount / Transaction / Entry
WorkspaceBudget(interval, limit)
WorkspaceUsageWindow(workspace, interval, spent, reserved)
ApiKeyUsageWindow(key, interval, spent, reserved)
Route / ModelPolicy / ProviderGrant (workspace)
```

Creation invariant: creating an organization atomically creates its default workspace plus owner memberships at both levels. Every organization has exactly one default workspace. Seed policy makes it non-deletable. Adding an organization member automatically adds a default-workspace membership; removing them removes workspace access and revokes/transfers their user-owned keys according to explicit policy.

## Redis implication

Organization credit and nested workspace/key limits must be checked atomically. Use the organization hash tag, not workspace hash tag:

```text
gw:{org_id}:billing
gw:{org_id}:inflight
gw:{org_id}:workspace:<workspace_id>:policy
gw:{org_id}:workspace:<workspace_id>:windows
gw:{org_id}:workspace:<workspace_id>:inflight
gw:{org_id}:key:<key_id>:auth
gw:{org_id}:key:<key_id>:windows
gw:{org_id}:reservation:<reservation_id>
gw:{org_id}:events
```

That lets one Redis operation reserve organization credit and all nested limits. It creates a per-organization Redis slot/hot key, an acceptable seed tradeoff that must be load-tested for very large organizations. Sharding one organization's financial mutation requires a more complex escrow design and is deferred.

## Spike conclusion

Adopt the OpenRouter-like organization/workspace split, but differentiate on financially strict admission, simple prepaid onboarding, and our inference supply—not feature breadth. The first UI should expose organization credits/billing and workspace keys/models/routes/limits. Presets, BYOK, external observability, content guardrails, and specialized routers are informed follow-ons after revenue validation.

Confidence: high for documented feature hierarchy; medium for “one physical gateway” because public docs show one API base URL and workspace-key scoping but do not describe OpenRouter's internal deployment topology. We should copy the logical product model, not infer their infrastructure.
