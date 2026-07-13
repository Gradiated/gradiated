# GitHub operating system for agents

Use GitHub Issues as the canonical work objects and GitHub Projects as the shared execution view. Keep implementation, research evidence, prompts, tests, and generated artifacts in this repository.

GitHub CLI supports creating issues, adding them to Projects, listing Project items, listing fields, and editing single-select field values. Project operations require the `project` authorization scope. The repo helper in `tools/github/agent.py` wraps those operations and resolves opaque Project IDs for agents.

## Initial setup

Install the official GitHub CLI for Debian using the [official instructions](https://github.com/cli/cli/blob/trunk/docs/install_linux.md), then authenticate once outside the repository:

```sh
gh auth login
gh auth refresh -s project
gh auth status
python3 tools/github/agent.py auth-check
python3 tools/github/agent.py bootstrap-labels
```

The helper never prints token values. Keep `gh` credentials in its external credential store, not in the repository or task packets.

Create one private Project for the startup, normally named `Startup OS`:

```sh
gh project create --owner @me --title "Startup OS" --format json
gh project field-create PROJECT_NUMBER --owner @me --name Lane \
  --data-type SINGLE_SELECT --single-select-options Product,Research,Operations
gh project field-create PROJECT_NUMBER --owner @me --name Priority \
  --data-type SINGLE_SELECT --single-select-options P0,P1,P2,P3
```

Keep the built-in `Status` field with these values: `Backlog`, `Ready`, `In Progress`, `Blocked`, `Review`, and `Done`. Use labels for work type and lane when repository-wide search is useful; do not duplicate Status in labels.

## Agent lifecycle

1. Create or find one issue for the work. Use the feature, bug, or research template.
2. Set `Lane` and `Priority`, add the issue to `Startup OS`, and set `Status` to `Ready`.
3. Assign the issue to the agent or human owner. An agent must claim an issue before changing code or starting spend-bearing research.
4. Move to `In Progress`, add a branch or task packet link when needed, and work inside the declared scope.
5. Open a PR linked to the issue. Put tests, evidence, risks, and rollback information in the PR body.
6. Move the Project item to `Review`. A reviewer agent checks the diff and the issue contract.
7. Merge or push the authorized change, then move the issue to `Done` only after CI and artifact handoff pass.

Use `Blocked` for missing access, failed quality gates, unavailable hardware, or a user decision. Record the exact blocker and the next unblock action in the issue.

## Common commands

```sh
# Work tracking
python3 tools/github/agent.py issue-create --title "..." --body-file tasks/body.md --project PROJECT_TITLE
python3 tools/github/agent.py issue-start ISSUE_NUMBER --project PROJECT_NUMBER --status "In Progress"
python3 tools/github/agent.py issue-list --state open

# Projects
python3 tools/github/agent.py project-list --owner @me
python3 tools/github/agent.py project-items --project PROJECT_NUMBER --owner @me
python3 tools/github/agent.py project-set-status --project PROJECT_NUMBER --owner @me \
  --issue ISSUE_NUMBER --status "Blocked"

# Pull requests
python3 tools/github/agent.py pr-create --title "..." --body-file tasks/pr-body.md --issue ISSUE_NUMBER
gh pr checks --watch
gh pr view --web
```

Use `gh issue develop ISSUE_NUMBER --name agent/ISSUE_NUMBER-short-name` when a linked branch is useful. Do not check out or mutate another agent's branch.

## Rules for autonomous agents

- One issue has one active owner. Split work when scopes overlap.
- Do not create duplicate issues; search first with `gh issue list` or the helper.
- Never put credentials, cookies, customer data, or private tokens in an issue, PR, Project field, or comment.
- Put durable conclusions and evidence in the repository, then link the path from the issue.
- Keep Project status synchronized after every meaningful state transition.
- Use direct pushes to `main` only for owned changes when authorized; use PRs for substantial or reviewer-sensitive work.
