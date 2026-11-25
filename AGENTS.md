# Agent Development Environment

This repository is the complete project state for the research and product-building agents. Keep durable knowledge, plans, prompts, code, measurements, reports, and generated decision artifacts here. Keep credentials, API keys, cookies, and browser profiles outside version control.

## Start here

1. Read this file.
2. Run `gradctl devex start` for the context pack and standard DevEx checks. mise puts `gradctl` on PATH in this repository; without mise, run `tools/gradctl/gradctl devex start`.
3. Read the nearest nested instructions before touching a workstream:
   - `research/lab/AGENTS.md` for the current Inference Foundry research lab.
4. Read the current handoff or report before starting a new experiment.
5. Check `git status` and preserve existing user work.

## Repo-native state

- Use `gradctl` (`tools/gradctl/`) for repository and developer operations: DevEx checks, `.env` and AWS sign-in, development GPUs, host leases, the GPU fleet tools, infrastructure, security, observability and model checks, browser captures and local product runs. It needs this machine on the Gradiated tailnet (`gradctl tailnet status`; `gradctl tailnet join` for a headless machine). Run `gradctl commands --json` for every command with its arguments, effects (read, write or destructive) and requirements, and pass `--json` for one result envelope on stdout. Add a new developer or agent command to `gradctl` instead of a standalone script, mise task or Makefile target.
- Put reusable agent procedures in `.agents/skills/`.
- Use the repository as the canonical source for implementation state, plans, prompts, measurements, reports, and generated decision artifacts.
- Use `README.md`, `docs/ARCHITECTURE.md` and `research/README.md` as the orientation map.
- Use the top-level documents in `docs/` for product architecture, data models and implementation plans; do not encode durable interfaces only in chat or issue comments.
- Treat the [security policies](https://github.com/Gradiated/gradiated-internal/blob/main/docs/security/policies/README.md) as binding company policy for security, access, change and data handling. Change a policy there by PR, then publish it to Drata.
- Pin every GitHub Action and reusable workflow to a full-length commit SHA with a version comment, e.g. `uses: actions/checkout@<sha> # v4.4.0`. The Gradiated org requires this, so a tag or branch ref fails the run. Pin new or changed `uses:` lines with [pinact](https://github.com/suzuki-shunsuke/pinact) (`pinact run`); pinact can't pin a branch ref, so switch it to a release tag first. Local `./` actions need no pin.
- Put browser automation code and dependency declarations in `tools/browser/`.
- Put temporary profiles, caches, test output, and run logs under `.agents/runtime/`; never commit them.
- Routine product, infrastructure, and CI work must not create evidence folders, dated reports, task packets, ledgers, or handoff files. Summarize checks in the PR or response. Update an existing README or plan only when behavior, operation, or a useful decision changes. Keep research deliverables only when the research task requires them.
- Put decision-relevant browser captures and research outputs in the relevant `research/<workstream>/docs/` or `research/<workstream>/evidence/` directory.
- Use `.env.example` for variable names and external secret storage for values.
- Shared development keys (model provider, OAuth, Stripe test and similar) live as one JSON object in the AWS Secrets Manager secret `gradiated/dev/env` (us-east-1), readable by the `gradiated-restricted`, `gradiated-readonly` and `gradiated-developer` profiles. Build the ignored `.env` with `gradctl env build`, or read single keys with `aws --profile gradiated-readonly secretsmanager get-secret-value`. Keys for forward-deployed customer work (model providers, an OpenRouter key pinned to zero-data-retention providers) live in `gradiated/dev/fde`; `gradctl env build --with-fde` adds them, and its values win where both secrets name a variable. Never print the values or commit the file. Ask a maintainer to add new shared dev keys there; do not put production credentials in it.
- Development training GPUs are spot or on-demand VMs from Nebius, Ornn or Spheron, created with `gradctl compute` (`search` finds available compute across them by price) using keys in `gradiated/dev/env`; see `$dev-training`. They join the tailnet as `tag:dev-training` and reach only VMs from the same provider. Keep customer data and production credentials off them, and copy results to S3 before `down`.
- Use the read-only `gradiated-readonly` profile for day-to-day AWS access and `gradctl aws login` when its credentials expire. Opt in explicitly with `gradctl aws login --profile gradiated-developer` only when a task needs developer writes, or `gradctl aws login --profile gradiated-admin` for break-glass administrative work such as bootstrap applies. Match the login task to the profile used by the command; logging in does not change the shell's `AWS_PROFILE`.
- Preserve existing on-demand GPU reservations. Repurpose running pods by changing processes over SSH, not by stopping, restarting, resetting, terminating, or changing provider image/environment settings. Those actions require explicit authorization to risk losing capacity; a file backup does not preserve the reservation. The one standing exception is the `gpu-fleet` operator's rollout in act mode, which re-images one drained host at a time onto a pinned image after its pods run elsewhere; a pin change merged to `main` authorizes it.
- Do not make issue trackers, Notion, Drive, Jira, or Slack a required source of truth. The repository owns code, research, prompts, and artifacts.
- Harness-launched `$research-director`, `$researcher`, and `$research-supervisor` turns are already claimed by their lab and project assignment. They update the lab/project logs directly and do not create a GitHub issue for every internal turn.

## Agent operating contract

- Operate autonomously until the user's objective is achieved, a preregistered terminal decision is supported, or an explicit resource limit is exhausted. Use best judgment for ordinary implementation and research choices; do not ask the user to choose among safe, in-scope, reversible alternatives.
- Treat a failed experiment, unavailable preferred resource, provider error, missing optional tool, or uncertain best candidate as a branch result, not as a reason to stop. Record the result, select the next highest-information in-scope alternative, and continue. Change placement, hardware, provider, runtime, representation, or experiment geometry when the objective permits it and the budget/evidence contract remains satisfied.
- Before declaring the objective blocked, exhaust safe in-scope diagnostics and materially distinct alternatives. Ask the user only when progress requires new authorization, credentials they have not already supplied, an irreversible or destructive external action, material scope expansion, acceptance of safety/legal risk, or spending beyond the authorized cap.
- Non-response from the user is not a blocker for a choice the agent can make within scope. Preserve momentum with the safest reversible assumption, document it, and keep working.
- A local stop rule kills only that experiment lineage unless it explicitly defines the campaign's terminal decision. Continue with the next admissible lineage while budget and objective remain open.
- State the hypothesis, scope, success criteria, budget, and timeout before running an experiment. For routine product or infrastructure checks, a short progress message is enough; no separate record is required.
- Prefer reproducible scripts and pinned inputs over one-off shell commands.
- Label evidence as measured, analytical, vendor-reported, derived, inferred, or synthetic.
- Do not transfer a result across models, workloads, hardware, or intervention sets without fresh scope-matched evidence.
- Treat negative and blocked results as durable research output.
- Never print, copy, commit, or upload credentials, cookies, tokens, private prompts, or private customer data.
- Browser agents must use a dedicated profile, an explicit domain allowlist, and a human checkpoint before login, sending, purchasing, publishing, or destructive actions.

## Skills

- `$research-director`: Sol-led opportunity selection and parallel project delegation.
- `$researcher`: autonomous execution and logging for one research project.
- `$research-supervisor`: periodic improvement of research speed and effectiveness.
- `$browser-research`: reproducible research on JavaScript-heavy or interactive websites.
- `$product-build`: repository-first product implementation, verification, and handoff.
- `$experiment-run`: bounded, reproducible experiments with cleanup; routine output stays untracked.
- `$dev-training`: spot GPU VMs for development training, isolated from production on the tailnet.
- `$internal-ai-gateway`: internal tailnet AI gateway for calling Gemini, Anthropic, and OpenAI models from team, dev, and training machines.
- `$gpu-host-lease`: lease a whole GPU host out of the serving pool for hand-run work, then hand it back to be wiped.
- `$gpu-model-rollout`: roll a risky runtime change out to a GPU model pool one replica at a time, hold at the first, compare, then finish or roll back.

## Pull request reviews

Every PR to `main` needs one approving review, from the `gradiated-review` app or a person with write access who is not the author. The app approves only after Codex or Graphite has reviewed the pull request (`.github/workflows/ai-review-gate.yml`). A review of any commit on the PR counts; commits pushed after a review are covered by required CI, the security scans and resolved review threads. After opening a PR, wait for at least one bot to complete; if neither completes, comment `@codex review` or re-run the review from the Graphite check's Details page. To re-evaluate the gate by hand, run `gh workflow run ai-review-gate.yml -f pr=123` with the PR number.

The `gradiated-review` GitHub App reviews every PR like a human reviewer, from the same workflow, and its approval is the required approving review. It approves when all of these hold:

- Codex or Graphite reviewed a commit of the PR with a passing result. For Codex, that means no P0/P1 findings; for Graphite, a successful AI Reviews check.
- Every Codex P0/P1 finding was followed by a clean Codex review of a newer commit. A resolved P1 counts only after Codex has reviewed the fix.
- Every review thread is resolved.

Until then, it posts a comment review listing what is outstanding, with links, and posts it again only when that list changes. When you push a fix for a Codex P0/P1, it comments `@codex review` itself. Codex may refuse a request from an app; if no Codex review follows, comment `@codex review` yourself. It re-checks after bot reviews and pushes, and every 15 minutes. GitHub cannot send a review request to an app. To ask for a fresh review, comment `@gradiated-review` (or start a comment with `/review`); it reacts and reviews again. Only comments from people with write access count.

When addressing a review comment, resolve its thread after the fix is pushed. When deliberately ignoring or declining a comment, briefly explain why in the thread and resolve it. Do not leave addressed or intentionally declined comments unresolved.

## Verification

Run `gradctl devex check` first, then the narrowest relevant checks and workstream checks. GitHub Actions runs the same DevEx checks plus Rust formatting and tests for the current research workspace after pushes. For research changes, the required checks are documented in `research/lab/AGENTS.md`.

Never stage or publish unrelated worktree changes, and always summarize the exact paths included. By default, create a scoped branch, commit the changes, push it, and open a pull request without asking for confirmation. Follow any different workflow requested by the user. Merging and production deployment require separate authorization unless already requested.
