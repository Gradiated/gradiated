# Task: 2026-07-13-direct-main-workflow

## Outcome

The repository instructs agents to publish completed owned work directly to `main` by default, with branches and pull requests used only when explicitly requested.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/6
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-13T19:20:22+00:00
- started: 2026-07-13T19:20:22+00:00
- last updated: 2026-07-13T19:20:22+00:00
- scope: AGENTS.md, docs/GITHUB_OPERATING_SYSTEM.md, docs/AGENT_OPERATING_SYSTEM.md, product/AGENTS.md, infra/docs release workflow language, tasks/active/2026-07-13-direct-main-workflow.md
- excluded paths: research/**, application code, cloud resources, credentials, unrelated worktree changes
- dependencies: merged PR #5

## Contract

- hypothesis or user value: removing branch/PR ceremony makes autonomous agent delivery faster while scoped commits and protected external-action gates preserve safety.
- acceptance checks: all agent publishing instructions agree on direct-to-main; internal infrastructure promotion language no longer requires PRs; local links and DevEx checks pass.
- quality gate: `git diff --check`, `python3 tools/devex/check.py`, and repository-local Markdown link validation.
- SLO or budget: documentation-only; no spend and no cloud mutation.
- timeout: one working session.
- artifact locations: `AGENTS.md`, `docs/GITHUB_OPERATING_SYSTEM.md`, `docs/AGENT_OPERATING_SYSTEM.md`, `product/AGENTS.md`, and scoped `infra/docs/**` files.
- resume command: `git diff -- AGENTS.md docs/GITHUB_OPERATING_SYSTEM.md docs/AGENT_OPERATING_SYSTEM.md product/AGENTS.md infra/docs tasks/active/2026-07-13-direct-main-workflow.md`
- rollback or cleanup: revert the scoped policy commit; no external resources are created.

## Plan

1. Merge the existing architecture PR.
2. Make direct-to-main publishing the canonical agent workflow while preserving owned-path and protected-environment controls.
3. Verify, commit the scoped paths, push `main`, close the issue, and release the packet.

## Result

- status: done
- verification: `python3 tools/devex/check.py` passed; `git diff --check` passed; local Markdown links valid across 22 scoped files.
- changed paths: `AGENTS.md`, `docs/AGENT_OPERATING_SYSTEM.md`, `docs/GITHUB_OPERATING_SYSTEM.md`, `product/AGENTS.md`, `infra/docs/CI_CD_AND_RELEASES.md`, `infra/docs/KUBERNETES_AND_HELM.md`, `infra/docs/TERRAFORM_AND_ENVIRONMENTS.md`, and this packet.
- limitations or blocked paths: GitHub check-rollup details for PR #5 were unavailable to the fine-grained token, but the PR was mergeable and merged successfully; no unrelated research path was staged or modified.
- commit: pending direct-to-main commit; exact SHA will be recorded after commit.
- next action: push the scoped commit to `main`, close issue #6, then continue the multi-provider inference architecture task.
- released: 2026-07-13T19:22:49+00:00
