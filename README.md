# Gradiated

Gradiated post-trains open-source models on production workloads and serves them
at low latency and cost. Applications route traffic through our OpenAI-compatible
gateway and provider relay to capture production traces, post-train open-weight
models on real tasks, and deploy the resulting checkpoints onto dedicated GPU
serving runtimes.

This monorepo contains the product, GPU serving and training runtimes, and model
optimization research. Our post-training library lives in
[`Gradiated/autotrain`](https://github.com/Gradiated/autotrain), and production
infrastructure lives in the private
[`Gradiated/infrastructure`](https://github.com/Gradiated/infrastructure)
repository (see [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md)).

## The product

- **Post-training on production workloads:** turn captured production traces into
  task-specific fine-tuned and RL-trained open-weight models using Temporal
  orchestration, GPU training runtimes, and
  [`Gradiated/autotrain`](https://github.com/Gradiated/autotrain).
- **Provider relay and trace capture:** call Anthropic, OpenAI, or open-weight
  models through a Rust proxy with task-scoped trace capture for dataset
  curation and evaluation.
- **High-throughput open-weight serving:** streaming model APIs backed by a Rust
  gateway (authentication, capacity, routing, and usage accounting) and custom
  GPU inference runtimes and kernels.
- **Console and integrations:** manage workspaces, traces, training runs, API
  keys, usage, and billing in the React console, or use the setup CLI to
  configure OpenCode, Codex, and Claude Code.

See the [website](https://gradiated.com), [developer docs](https://gradiated.com/docs),
and [console](https://console.gradiated.com). For coding-agent setup, start with
the [wizard](product/services/wizard/README.md).

## Monorepo map

| Path | Contents |
| --- | --- |
| [`product/services/`](product/services/) | Management API, workers, console, Rust gateway/proxy/collector, setup CLI, and operations MCP. |
| [`product/packages/`](product/packages/) | Shared contracts, configuration, control-plane logic, and datastore integrations. |
| [`product/website/`](product/website/) | Public website, developer documentation, and articles. |
| [`product/inference/`](product/inference/) | Native C++/CUDA engine, serving and training runtimes, runtime bundles, and benchmarks. |
| [`docs/INFRASTRUCTURE.md`](docs/INFRASTRUCTURE.md) | Pointer to the private `Gradiated/infrastructure` repo (Terraform/Terragrunt, Kubernetes/Argo CD, and GPU host configuration). |
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
Tailscale and `lsof`. Connect to the Gradiated tailnet, which
[`gradctl`](tools/gradctl/README.md) requires. From the repository root:

```sh
mise install
gradctl devex start
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
Run `gradctl devex check` from the root, followed by the relevant
workstream checks (`pnpm check` from `product/` for product changes).
Keep credentials and local run output out of version control.

For deeper context, see the [architecture](docs/ARCHITECTURE.md),
[data model](docs/DATA_MODEL.md), [deployment guide](docs/DEPLOYMENT.md),
[infrastructure guide](docs/INFRASTRUCTURE.md), and [research overview](research/README.md).
