# Agent Development Environment

This repository is the complete project state for the research and product-building agents. Keep durable knowledge, plans, prompts, code, measurements, reports, and generated decision artifacts here. Keep credentials, API keys, cookies, and browser profiles outside version control.

## Start here

1. Read this file.
2. Run `python3 tools/devex/start.py` for the context pack and standard DevEx checks.
3. Read the nearest nested instructions before touching a workstream:
   - `research/sol/AGENTS.md` for Inference Foundry.
   - `research/fable/CLAUDE.md` and `research/fable/README.md` for Sartor/Fable.
4. Read the current handoff or report before starting a new experiment.
5. Check `git status` and preserve existing user work.

## Repo-native state

- Put reusable agent procedures in `.agents/skills/`.
- Use GitHub Issues for canonical cross-agent work tracking and GitHub Projects for the active execution view.
- Use `tasks/` for detailed local execution packets when an issue needs a reproducible experiment contract or offline handoff; link the issue and do not maintain a second status system.
- Use `docs/CONTEXT_INDEX.md` and `research/README.md` as the orientation map; update them when adding a workstream or changing the resume contract.
- Use `docs/ARCHITECTURE.md` and `docs/decisions/` for cross-agent product architecture decisions; do not encode durable interfaces only in chat or issue comments.
- Put browser automation code and dependency declarations in `tools/browser/`.
- Put ephemeral browser profiles, caches, and run logs under `.agents/runtime/`; never commit them.
- Put decision-relevant browser captures and research outputs in the relevant `research/<workstream>/docs/` or `research/<workstream>/evidence/` directory.
- Use `.env.example` for variable names and external secret storage for values.
- Do not make Notion, Drive, Jira, or Slack a required source of truth. GitHub Issues/Projects own work state; the repository owns code, research, prompts, and artifacts.

## Agent operating contract

- Operate autonomously until the user's objective is achieved, a preregistered terminal decision is supported, or an explicit resource limit is exhausted. Use best judgment for ordinary implementation and research choices; do not ask the user to choose among safe, in-scope, reversible alternatives.
- Treat a failed experiment, unavailable preferred resource, provider error, missing optional tool, or uncertain best candidate as a branch result, not as a reason to stop. Record the result, select the next highest-information in-scope alternative, and continue. Change placement, hardware, provider, runtime, representation, or experiment geometry when the objective permits it and the budget/evidence contract remains satisfied.
- Before declaring the objective blocked, exhaust safe in-scope diagnostics and materially distinct alternatives. Ask the user only when progress requires new authorization, credentials they have not already supplied, an irreversible or destructive external action, material scope expansion, acceptance of safety/legal risk, or spending beyond the authorized cap.
- Non-response from the user is not a blocker for a choice the agent can make within scope. Preserve momentum with the safest reversible assumption, document it, and keep working.
- A local stop rule kills only that experiment lineage unless it explicitly defines the campaign's terminal decision. Continue with the next admissible lineage while budget and objective remain open.
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

GitHub workflow instructions and the CLI helper live in `docs/GITHUB_OPERATING_SYSTEM.md` and `tools/github/agent.py`.

## Verification

Run `python3 tools/devex/check.py` first (`make devex-check` is an optional shorthand), then the narrowest relevant checks and workstream checks. GitHub Actions runs the same DevEx checks plus Rust formatting and tests for both workspaces after pushes. For Sol changes, the required Rust checks are documented in `research/sol/AGENTS.md`. For Fable changes, preserve the parity and calibration rules in `research/fable/CLAUDE.md`.

Agents may commit and push changes they own directly to `main` when the user has authorized it. Never stage or publish unrelated worktree changes, and always summarize the exact paths included.
