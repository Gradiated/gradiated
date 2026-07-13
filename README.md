# Gradiated agent workspace

This repository is the durable project state for a startup built with Codex agents. It contains product code, research, prompts, experiments, evidence, tests, and handoffs. Credentials, cookies, browser profiles, and other private runtime state stay outside Git.

## Start here

```sh
python3 tools/devex/start.py
```

Read [`AGENTS.md`](AGENTS.md) and [`docs/CONTEXT_INDEX.md`](docs/CONTEXT_INDEX.md) before taking work. Claim one GitHub Issue, confirm its Project status and owner, reserve a narrow file/artifact scope, and leave a task packet or durable report another agent can resume.

## Repository map

- [`research/README.md`](research/README.md) — research workstream map and evidence conventions.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — product architecture boundaries and decision-record contract.
- [`research/sol/`](research/sol/) — Inference Foundry; read its `AGENTS.md`, `README.md`, and current handoff.
- [`research/fable/`](research/fable/) — Sartor/Fable; read its `CLAUDE.md`, `README.md`, and current report.
- [`tasks/`](tasks/) — detailed execution packets in `inbox/`, `active/`, and `done/`.
- [`.agents/skills/`](.agents/skills/) — reusable research, browser, experiment, and product-build procedures.
- [`tools/github/agent.py`](tools/github/agent.py) — dependency-free Issue, PR, label, and Project helper.
- [`docs/GITHUB_OPERATING_SYSTEM.md`](docs/GITHUB_OPERATING_SYSTEM.md) — GitHub operating model.

GitHub Issues are the canonical cross-agent work objects and Projects are the execution view. The repository remains the canonical source for implementation and research state.
