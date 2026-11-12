# Docs refresh

`.github/workflows/docs-refresh.yml` keeps the developer docs in
`product/website/src/docs/` in step with the product. It runs every day at
06:23 UTC and can be started by hand from the Actions tab.

## What a run does

1. Finds the open pull request from `automation/docs-refresh`. If one exists,
   it checks out that branch and merges `main` into it. If not, it starts a
   new branch from `main`.
2. Collects context: commits on `main` since the last docs refresh pull
   request merged (14 days on the first run, 30 at most), the open pull
   request's unresolved review threads and new maintainer comments, and
   proposals closed without merging in the last 60 days.
3. Audits the docs in four read-only sessions, one per group of pages, on
   Kimi K3.1 Pro through Gradiated's own API ([`audit-prompt.md`](audit-prompt.md)).
   Each returns the claims that the code contradicts, with evidence.
4. Runs Claude Opus 5.5 ([`prompt.md`](prompt.md)) with the context and the
   audit findings. It checks each finding in the code, edits the pages, runs
   the website build, and ends with a structured result: the pull request
   description, the day's update, replies to review threads, and notes.

   Both stages run on the [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview)
   ([`agent.mjs`](agent.mjs)) with the Claude Code tools. They read and search
   the whole repository and run read-only `git` and shell commands. Only the
   Opus stage can edit, and a hook blocks edits outside the docs paths.
   Neither stage has a GitHub token.
5. Discards changes outside the docs paths, builds the website, commits, and
   pushes with the Gradiated Docs app token. It opens the pull request, or
   updates its description, comments with the day's changes, and replies to
   and resolves the review threads it addressed.

A day with no needed change pushes nothing and opens nothing.

## Steer it

- Leave review comments on the pull request. The next run reads unresolved
  threads and new comments from maintainers and from Codex or Graphite.
- Push your own commits to `automation/docs-refresh`. Later runs keep them.
- Close the pull request to reject a proposal. The next run starts fresh and
  avoids proposals closed in the last 60 days unless the code changed.
- Change the writing and judgment rules in [`prompt.md`](prompt.md). The
  shared writing standard lives in `docs/DEVELOPER_DOCS.md`.
- Run it by hand with **dry run** to see the diff in the job log without
  pushing. A pull request that changes this directory or the workflow gets a
  dry run too. The prompt, audit findings and agent output are uploaded as the
  `docs-refresh` artifact.

If the branch conflicts with `main`, the run comments on the pull request and
fails. Merge `main` into the branch, or close the pull request.

## Setup

- Create the Gradiated Docs GitHub App:
  `gradctl github-apps create docs`. It stores `DOCS_APP_CLIENT_ID` and
  `DOCS_APP_PRIVATE_KEY` in this repository.
- Add an Anthropic API key as the `DOCS_REFRESH_ANTHROPIC_API_KEY` repository
  secret.
- Create a Gradiated API key named `docs-refresh` in the Gradiated workspace
  and add it as the `DOCS_REFRESH_GRADIATED_API_KEY` repository secret. Without
  it, the audits run on Claude Sonnet 5.5 (`DOCS_REFRESH_FALLBACK_AUDIT_MODEL`)
  with the Anthropic key.
- Optional repository variables: `DOCS_REFRESH_MODEL` (default
  `claude-opus-5-5`), `DOCS_REFRESH_EFFORT` (default `high`),
  `DOCS_REFRESH_MAX_BUDGET_USD` (default `20`), `DOCS_REFRESH_AUDIT_MODEL`
  (default `moonshotai/kimi-k3.1-pro`) and `DOCS_REFRESH_AUDIT_CONCURRENCY`
  (default `2`, which keeps audit load on the shared Kimi replica low).

## Run locally

Use a clean checkout, such as a spare worktree, with `product/` dependencies
installed and `ANTHROPIC_API_KEY` set or Claude Code logged in. `prepare`
switches the checkout to `automation/docs-refresh`, so run a copy of the tool:

```bash
cp -R tools/docs-refresh /tmp/docs-refresh
npm ci --prefix /tmp/docs-refresh
GH_TOKEN=$(gh auth token) mise exec -- node /tmp/docs-refresh/refresh.mjs prepare
mise exec -- node /tmp/docs-refresh/refresh.mjs agent
DOCS_REFRESH_DRY_RUN=true mise exec -- node /tmp/docs-refresh/refresh.mjs publish
```

A manual run from a branch uses that branch's prompt and script, so you can
try prompt changes with a dry run before you merge them.
