# Gradiated

Gradiated builds inference infrastructure for AI applications and coding agents.
It serves open-weight models through an OpenAI-compatible API and OpenRouter,
with a customer console for workspaces, API keys, usage, and billing.

This monorepo contains the product, GPU serving runtimes, production
infrastructure, and model optimization research.

## The product

- **Hosted inference:** streaming model APIs backed by a Rust gateway that handles
  authentication, capacity, routing, and usage accounting.
- **Provider relay and traces:** call Anthropic or OpenAI with your own provider
  key, with optional task-scoped trace capture for inspecting application traffic.
- **Console and integrations:** manage accounts and model access in the React
  console, or use the setup CLI to configure OpenCode, Codex, and Claude Code.
- **Training work in progress:** task-based fine-tuning interfaces and Temporal
  orchestration are present; the current executor is a mock, not a production
  training backend.

See the [website](https://gradiated.com), [developer docs](https://gradiated.com/docs),
and [console](https://console.gradiated.com). For coding-agent setup, start with
the [wizard](product/services/wizard/README.md).

## Monorepo map

| Path | Contents |
| --- | --- |
| [`product/services/`](product/services/) | Management API, workers, console, Rust gateway/proxy/collector, setup CLI, and operations MCP. |
| [`product/packages/`](product/packages/) | Shared contracts, configuration, control-plane logic, and datastore integrations. |
| [`product/website/`](product/website/) | Public website, developer documentation, and articles. |
| [`product/inference/`](product/inference/) | Native C++/CUDA engine, model runtimes, runtime bundles, and serving benchmarks. |
| [`infra/`](infra/) | Terraform/Terragrunt infrastructure, Kubernetes/Argo CD deployments, and GPU host configuration. |
| [`research/`](research/) | Model analysis, simulation, validation, and research tooling. |
| [`tools/`](tools/) | Development checks, browser automation, and model/operations utilities. |
| [`docs/`](docs/) | Architecture, data contracts, deployment guides, and feature plans. |

All paths in this table are relative to the repository root.

The application uses TypeScript/Node and React, with pnpm and Turborepo managing
the product workspace. Rust services handle inference and trace collection;
GPU runtimes execute models separately. PostgreSQL holds durable product state,
Valkey supports inference admission and accounting, ClickHouse holds usage
history, and S3 stores captured content and artifacts.

## Local development

Install the toolchain pinned in [`mise.toml`](mise.toml), plus Docker, Python 3,
and `lsof`. From the repository root:

```sh
mise install
python3 tools/devex/start.py
cd product
mise exec -- pnpm install
mise exec -- pnpm exec turbo run build --filter=@gradiated/api --filter=@gradiated/worker
mise exec -- pnpm dev
```

The launcher opens mprocs, runs datastores in Docker Compose, and starts the
application services locally. On a fresh database, start the `migrate-postgres`
and `migrate-clickhouse` panes, then the `seed` pane (select each and press `s`).
Open the console at `http://localhost:3000`; the local inference base URL is
`http://127.0.0.1:3003/v1`.

Hosted inference needs a model runtime. The optional local SGLang/MLX process
supports Apple Silicon; see the [product guide](product/README.md) for model
setup, service ports, optional integrations, and smoke checks.

## Working in the repository

Read [AGENTS.md](AGENTS.md) and the instructions in the area you are changing.
Run `python3 tools/devex/check.py` from the root, followed by the relevant
workstream checks (`pnpm check` from `product/` for product changes).
Keep credentials and local run output out of version control.

For deeper context, see the [architecture](docs/ARCHITECTURE.md),
[data model](docs/DATA_MODEL.md), [deployment guide](docs/DEPLOYMENT.md),
[infrastructure guide](infra/README.md), and [research overview](research/README.md).
