# Agent context index

This is the shortest reliable reset path for a new agent. GitHub Issues and Projects track ownership and priority; this repository contains the implementation, research, evidence, prompts, and handoffs needed to resume work.

## Reset protocol

From the repository root:

```sh
python3 tools/devex/start.py
git status --short --branch
```

For same-workspace process safety, claim a packet atomically before editing:

```sh
python3 tools/devex/claim.py start 2026-07-13-example \
  --issue https://github.com/joshsny/gradiated/issues/123 \
  --scope research/sol/experiments/example
```

Release it with `python3 tools/devex/claim.py release 2026-07-13-example --status done` or `--status blocked`. This local lock is a collision guard, not a replacement for the GitHub Issue or Project.

Then read, in order:

1. [`AGENTS.md`](../AGENTS.md) — repository invariants and safety rules.
2. The linked GitHub issue and its Project status — canonical scope, owner, and state.
3. [`docs/AGENT_OPERATING_SYSTEM.md`](AGENT_OPERATING_SYSTEM.md) — concurrency and handoff rules.
4. The nearest workstream instructions and start document from [`research/README.md`](../research/README.md).
5. The task packet in `tasks/active/`, or the most recent handoff/report named by the context command.

Do not infer current state from filenames, chat history, or an old report when a newer handoff, issue, or machine-readable status artifact exists.

## Durable state map

| State | Canonical location | Purpose |
| --- | --- | --- |
| Ownership and priority | GitHub Issue + Project | One active owner, status, dependencies, and cross-agent coordination |
| Execution contract | `tasks/inbox/` or `tasks/active/` | Scope, acceptance checks, budget, timeout, artifact paths, and resume instructions |
| Product source | Product workstream directory | Code, tests, configuration, and implementation handoffs |
| Research source material | `research/<workstream>/evidence/` | Raw captures, measurements, logs, hashes, and provenance |
| Research synthesis | `research/<workstream>/docs/` | Reports, decision briefs, and uncertainty-labeled conclusions |
| Current workstream state | Workstream `README`, `AGENTS.md`/`CLAUDE.md`, handoff, or report | The latest accepted facts, blockers, and next decisive actions |
| Ephemeral runtime state | `.agents/runtime/` | Caches, browser profiles, temporary logs, and resumable process state; never commit |

## Handoff minimum

Every completed or blocked task must leave a packet or durable report containing:

- decision or user outcome;
- exact scope and non-scope;
- files and interfaces changed;
- evidence class and provenance;
- checks run and their result;
- known limitations or failed/blocked paths;
- exact resume command and next safe action.

Prefer one artifact per run and append-only ledgers. When a shared report must change, reserve it in the issue and have one owner update it after the run; parallel agents should write separate evidence artifacts first.

## Fast orientation by workstream

See [`research/README.md`](../research/README.md) for the workstream map. The context helper accepts `--workstream sol` or `--workstream fable` to print only the relevant reset pack.

For the complete startup, begin with [`docs/STARTUP_ARCHITECTURE.md`](STARTUP_ARCHITECTURE.md), [`docs/SIMPLICITY_REVIEW.md`](SIMPLICITY_REVIEW.md), and [`docs/IMPLEMENTATION_COVERAGE.md`](IMPLEMENTATION_COVERAGE.md). For the inference-gateway product, then read [`product/AGENTS.md`](../product/AGENTS.md) and [`product/HANDOFF.md`](../product/HANDOFF.md). The bounded-context implementation blueprints and subagent work packages are indexed from [`product/README.md`](../product/README.md).

For its AWS platform, next read [`infra/AGENTS.md`](../infra/AGENTS.md), [`infra/README.md`](../infra/README.md), [`infra/docs/PLATFORM_IMPLEMENTATION.md`](../infra/docs/PLATFORM_IMPLEMENTATION.md), and [`infra/docs/DELIVERY_PLAN.md`](../infra/docs/DELIVERY_PLAN.md). The cross-workstream runtime decision is [`docs/decisions/0001-aws-eks-platform.md`](decisions/0001-aws-eks-platform.md). Infrastructure plans are implementation contracts, not evidence that cloud resources exist.
