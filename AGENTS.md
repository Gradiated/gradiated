# Agent Development Environment

This repository is the complete project state for the research and product-building agents. Keep durable knowledge, plans, prompts, code, measurements, reports, and generated decision artifacts here. Keep credentials, API keys, cookies, and browser profiles outside version control.

## Start here

1. Read this file.
2. Read the nearest nested instructions before touching a workstream:
   - `research/sol/AGENTS.md` for Inference Foundry.
   - `research/fable/CLAUDE.md` and `research/fable/README.md` for Sartor/Fable.
3. Read the current handoff or report before starting a new experiment.
4. Check `git status` and preserve existing user work.

## Repo-native state

- Put reusable agent procedures in `.agents/skills/`.
- Use `tasks/` for durable task packets, ownership, priorities, and handoffs.
- Put browser automation code and dependency declarations in `tools/browser/`.
- Put ephemeral browser profiles, caches, and run logs under `.agents/runtime/`; never commit them.
- Put decision-relevant browser captures and research outputs in the relevant `research/<workstream>/docs/` or `research/<workstream>/evidence/` directory.
- Use `.env.example` for variable names and external secret storage for values.
- Do not make Notion, Drive, Jira, Slack, or a remote app the source of truth.

## Agent operating contract

- State the decision, hypothesis, scope, quality gate, SLO, budget, timeout, and artifact contract before running an experiment.
- Prefer reproducible scripts and pinned inputs over one-off shell commands.
- Label evidence as measured, analytical, vendor-reported, derived, inferred, or synthetic.
- Do not transfer a result across models, workloads, hardware, or intervention sets without fresh scope-matched evidence.
- Treat negative and blocked results as durable research output.
- Never print, copy, commit, or upload credentials, cookies, tokens, private prompts, or private customer data.
- Browser agents must use a dedicated profile, an explicit domain allowlist, and a human checkpoint before login, sending, purchasing, publishing, or destructive actions.

## Skills

- `$evidence-research`: source-backed, falsifiable technical or market research.
- `$browser-research`: reproducible research on JavaScript-heavy or interactive websites.
- `$product-build`: repository-first product implementation, verification, and handoff.
- `$experiment-run`: bounded, reproducible experiments with durable artifacts and cleanup.

## Verification

Run `python3 tools/devex/check.py` first (`make devex-check` is an optional shorthand), then the narrowest relevant checks and workstream checks. GitHub Actions runs the same DevEx checks plus Rust formatting and tests for both workspaces after pushes. For Sol changes, the required Rust checks are documented in `research/sol/AGENTS.md`. For Fable changes, preserve the parity and calibration rules in `research/fable/CLAUDE.md`.

Agents may commit and push changes they own directly to `main` when the user has authorized it. Never stage or publish unrelated worktree changes, and always summarize the exact paths included.
