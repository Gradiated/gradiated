# Product architecture handoff

## Current decision

Build the direct paid gateway first, while making the serving surface eligible for external-gateway provider onboarding. The control plane is a Vite React application plus a separate Hono/tRPC Node API. The data plane is Rust. An organization is the customer and billing boundary; its workspaces are isolated key, policy, limit, membership, and usage-attribution boundaries.

Creating an organization atomically creates a Default workspace and owner memberships. PostgreSQL owns the organization-level append-only credit ledger. The gateway depends internally only on Redis, which holds versioned organization/workspace/key/config projections, atomic reservations, nested limits, low-credit concurrency state, and Redis Streams billing events. A Node worker projects committed PostgreSQL changes to Redis, consumes gateway events into PostgreSQL idempotently, and continuously reconciles both views.

## Non-negotiable behavior

- A raw API key resolves to one organization and one workspace. Top-ups and ledger entries are organization-scoped; usage and configurable limits are also attributed to workspace/key.
- A top-up credits the organization only from a verified, idempotently processed Stripe webhook, never from a browser redirect.
- No upstream call begins unless one Redis operation authenticates, checks organization/workspace/key status, reserves worst-case organization spend, reserves all nested limits, increments permitted concurrency, creates a lease, and appends the reservation event.
- Insufficient organization credit returns `402 insufficient_credits`. Low organization credit activates an organization-wide in-flight cap in addition to workspace/key caps; excess requests return `429 low_balance_concurrency_limit`.
- Redis failure before admission is fail-closed. PostgreSQL is not queried by the gateway.
- Settlement and stream consumption are idempotent. PostgreSQL ledger corrections are append-only.
- Internal TS/Rust contracts are Protobuf-generated and checked for drift. External OpenAI/Anthropic JSON behavior is fixture-tested separately.
- Billing and authorization logic require PBT state machines in fast-check and proptest, with seeds/replay artifacts emitted by CI.

## Implementation order

1. Scaffold pnpm/Rust workspaces, Buf contracts, CI, fake providers, PBT replay tools, and local/CI containers.
2. Implement PostgreSQL organization/workspace memberships, keys, budgets, and organization ledger invariants.
3. Implement Vite/shadcn UI, Hono/tRPC API, Better Auth sessions, and organization/workspace authorization.
4. Implement Stripe top-ups, transactional outbox, Redis projector, stream consumer, and reconciliation.
5. Implement Rust Redis admission/settlement scripts and state-machine tests before provider dispatch.
6. Add OpenAI Chat Completions and Anthropic Messages ingress plus generic provider adapters and streaming conformance.
7. Add official-client protected CI smoke tests and operational dashboards.
8. Extend the completed documentation spike into measured OpenRouter/provider conformance, soak, economics, and then human-approved onboarding.

Detailed ownership and acceptance checks are in `docs/DELIVERY_PLAN.md`.

## Infrastructure decision

The AWS/EKS plan is now specified under `../infra/`. Each environment has an isolated AWS account/VPC/private EKS cluster. The Vite console is served by S3/CloudFront; separate ALBs front the Hono API and Rust gateway. Aurora PostgreSQL Serverless v2 owns financial/configuration state. Production admission targets node-based ElastiCache Valkey 9 synchronous durability, but launch is blocked until exact command, failover, no-acknowledged-loss, memory-pressure, and latency qualification passes; serverless Valkey is limited to disposable environments until equivalent evidence exists.

Terraform modules plus Terragrunt implicit stacks use versioned/KMS S3 state with native lock files. Argo CD pulls Helm desired state, KEDA scales pods, Karpenter supplies bounded nodes, and GitHub OIDC avoids static AWS credentials. Docker Compose and mprocs/dekit sit behind a Rust `grad` CLI so agents can run and verify the stack without owner-local execution. See `../infra/docs/DELIVERY_PLAN.md` and `../docs/decisions/0001-aws-eks-platform.md`.

## OpenRouter spike result

Official public docs show one shared API surface with organization/account-level credits and billing, plus workspaces that independently scope API keys, members, routing, guardrails, BYOK, presets, observability, and interval budgets. The Default workspace contains the simple-path setup and organization members automatically receive access. Our design adopts that logical hierarchy but uses stricter atomic maximum-cost reservations so in-flight requests cannot overrun organization credit or workspace/key budgets. See `docs/OPENROUTER_SPIKE.md`.

## Environment names planned

```text
DATABASE_URL
REDIS_URL
BETTER_AUTH_SECRET
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
OPENAI_API_KEY
OPENAI_E2E_MODEL
ANTHROPIC_API_KEY
ANTHROPIC_E2E_MODEL
PBT_SEED
```

Secrets belong in deployment/GitHub environments only. Provider smoke tests must never print payloads or tokens.

## Coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/1
- Completed packet: `tasks/done/2026-07-13-gateway-architecture-revision.md`
- GitHub issue #1 is closed. GitHub Project mutation was unavailable to the current fine-grained token; the local scope has been released.
- Infrastructure plan issue: https://github.com/joshsny/gradiated/issues/2; completed packet: `tasks/done/2026-07-13-infrastructure-platform-plan.md`.
- No code has been implemented and no provider request has been made in this planning task.

## Resume

```sh
python3 tools/devex/context.py
sed -n '1,260p' product/docs/DELIVERY_PLAN.md
sed -n '1,320p' infra/docs/DELIVERY_PLAN.md
```

Claim exactly one work package and its paths before implementation. Begin with product WP-00 and infrastructure I-00 as coordinated contract/toolchain work; no AWS mutation begins until the platform checkpoint inputs and authority in the infrastructure plan are satisfied.
