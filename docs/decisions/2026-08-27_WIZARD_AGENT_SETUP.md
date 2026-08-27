# Wizard agent setup

- Date: 2026-08-27
- Status: implemented
- Decision: configure OpenCode and Codex in the wizard. Document manual
  Claude Code setup.

## What changed and why

The wizard now detects OpenCode and Codex. The `--agent` option restricts one
run to either client. A bare run configures all detected supported clients.
This feature releases as `@gradiated/wizard` version `0.2.0`.

OpenCode keeps its existing default model. Codex receives an opt-in
`gradiated` profile. The wizard does not change the default Codex provider.
Codex reads the owner-only Gradiated credential through its command-backed
provider authentication.

Claude Code setup remains manual. Its environment variables select the base
URL, token, and model for one shell. The wizard does not change the global
Claude Code route.

Terraform static CI now shares one provider plugin cache across module roots.
It removes each temporary `.terraform` directory after validation. This stops
repeated AWS provider copies from exhausting the runner disk.

## Files and interfaces

- `product/services/wizard/src/agents/codex.ts` owns the Codex provider and
  profile merge.
- `product/services/wizard/src/bin.ts` dispatches detected agent installs.
- `product/services/wizard/src/arguments.ts` defines `--agent`.
- `product/website/src/docs/` contains the OpenCode, Codex, and Claude Code
  setup pages.
- `.github/workflows/tests.yml` and
  `.github/workflows/wizard-publish.yml` install the real Codex client.
- `.github/workflows/terraform.yml` controls provider cache reuse and cleanup.

## Run from the repository

```sh
cd product
pnpm --filter @gradiated/wizard build
pnpm --filter @gradiated/wizard check
pnpm --filter gradiated-com build
pnpm format:check
```

## Verification

- Wizard build: passed.
- Wizard TypeScript and Vitest checks: 7 tests passed.
- Real Codex strict-config and local Responses request: passed in Vitest.
- Website production build: passed.
- Product formatting check: passed.
- GitHub Terraform format and static validation job: passed in 3m20s. The
  former disk exhaustion did not recur.

## Limits and external requirements

The real client test uses the installed `codex` executable. CI installs
`@openai/codex` and `opencode-ai` before it runs the wizard checks. No external
credentials are required. The test uses a local HTTP stub and a synthetic API
key.

The GitHub-hosted runner verified the Terraform disk fix. A later production
apply failure is outside the static validation fix.

## Next safe action

Run the GitHub Actions product, wizard, and Terraform workflows. Confirm that
the Terraform static job completes without runner disk exhaustion.
