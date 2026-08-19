# Product handoff

## Current decision

Build the exact-model product in [ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [Kimi K3 provider launch plan](../docs/KIMI_K3_PROVIDER_LAUNCH_PLAN.md), the [canonical data model](../docs/DATA_MODEL.md), and the [product API contract](../docs/API.md).

The direct product remains: Vite/React/shadcn UI served by a TypeScript/Hono API, a TypeScript worker from the same image, organizations/workspaces, API keys, usage and billing. OpenRouter and direct customers use the same Rust gateway. Kimi K3 is the first model and SGLang is the initial external GPU runtime.

## Current implementation

The application slice includes Better Auth, organizations, workspaces, API
keys, the model/deployment catalog, durable balances, Stripe Checkout top-ups,
and the TypeScript settlement worker foundations. Model writes pass through a
normalizing Zod schema before PostgreSQL and Valkey, so the Rust gateway reads a
complete `GatewayModel` projection without supplying catalog defaults.

The Rust gateway includes its HTTP health shell, typed configuration, Valkey
Cluster reads, authentication/access primitives, strict model/deployment
contracts, request-envelope parsing, and the pre-admission
`RequestCoordinator`. The coordinator performs credential, workspace, account,
balance, exact-model, deployment, streaming, output-limit, and model-parameter
qualification. The concrete `ModelTokenizer` resolves and caches the selected
deployment's pinned Hugging Face tokenizer artifacts, renders its
Transformers-compatible chat template, counts locally on CPU, and enforces
prompt and combined context limits. The downstream value retains only
`input_tokens`; rendered prompts and token IDs are discarded. The pinned local
Qwen artifact smoke test passes.

`ValkeyServingState::admit` now executes one versioned Lua script across the
co-slotted account, in-flight lease, and settlement-stream keys. It validates
the complete mutable serving state before writing, applies balance-funded
prepaid concurrency with the default cap of 50, leaves invoiced concurrency
uncapped even at negative balance, applies settlement backlog pressure, removes
only leases beyond the cleanup grace period, and creates the fixed lease with
`ZADD NX`. Focused tests run the script against the real one-node Valkey
Cluster, including simultaneous boundary admissions and `CROSSSLOT` behavior.
The product-only `tests.yml` workflow has independent unit, integration, and
end-to-end jobs so all three run in parallel. Its integration job starts the
complete product Docker Compose dependency stack, waits for Valkey cluster
initialization and service health, and runs this ignored real-cluster suite.
The workflow runs on pull requests and main pushes only when `product/**`
changes. The E2E suite uses an automatic per-test fixture that creates and funds
a unique user, organization, and workspace, allowing its spec files to execute
concurrently without shared account state. The adapter exists, but the public
HTTP request path does not yet invoke it and no runtime is called.

## Next product work

Connect qualification and local tokenization to the admission adapter in the
request lifecycle, then wire non-streaming SGLang dispatch and atomic terminal
settlement. The public Chat Completions route must not dispatch work until
admission is present.

Do not add a second or general gateway, provider router, alias system, generalized fleet service or speculative product surface without a new decision record.
