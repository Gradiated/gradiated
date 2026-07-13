# Agent operating system

This repository is intended to support a small startup run primarily by Codex agents. The operating model is repository-first, parallel by explicit scope, and evidence-backed.

## Work lanes

- Product: user-facing behavior, APIs, UI, deployment, and support tools.
- Research: source review, experiments, benchmarks, and decision briefs.
- Operations: dependency updates, security, release checks, and environment maintenance.

Every task belongs to one lane, has one owner, and leaves a durable packet in `tasks/`.

## Parallel-agent rules

- Split by directory or artifact, not by vague responsibility.
- Give each agent a narrow acceptance contract and a verification command.
- Do not let two agents edit the same task packet, ledger, generated report, or lockfile concurrently.
- Have a reviewer agent inspect the diff and evidence after implementation, before the owner pushes.
- Push only the owned files; the worktree may contain unrelated research in progress.

## Autonomous loop

1. Intake a task or research question.
2. Create or claim a task packet.
3. Inspect the relevant nested instructions and current state.
4. Form a plan and write the acceptance checks before changing code.
5. Implement or investigate with bounded time, spend, and scope.
6. Run tests, smoke checks, or evidence validation.
7. Update the task packet and durable docs.
8. Ask for a human decision only for credentials, irreversible external actions, spending, legal/compliance claims, or a failed quality gate.
9. Commit and push the owned change to `main` when authorized.

## Speed without drift

Prefer one canonical command (`make devex-check`), one task format, local skills, reusable scripts, and small reviewable commits. Avoid adding SaaS project-management state, undocumented shell aliases, or agent-specific memory that another agent cannot read from the repository.
