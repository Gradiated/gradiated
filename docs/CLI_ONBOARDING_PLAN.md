# CLI onboarding plan

- status: proposal
- date: 2026-08-27
- owner: Gradiated Ltd
- related: [ARCHITECTURE.md](ARCHITECTURE.md), [OPENROUTER_PROVIDER_README.md](OPENROUTER_PROVIDER_README.md)

## Goal

Zero-friction onboarding. A person who has never used Gradiated runs:

```sh
npx -y @gradiated/wizard
```

and ends up with their coding agent (OpenCode first) pointed at Gradiated
inference, a verified key, and one successful generation. Time from command to
first completed generation: under two minutes, no manual file edits.

## Why a Node CLI

- Everyone who can run a coding agent already has Node: Claude Code requires
  it, OpenCode installs through npm, and Codex users overwhelmingly have it.
  There is no meaningful audience that lacks Node but would use the wizard.
- `npx -y` is the lowest-friction entry point that exists on that base: no
  install step, no platform matrix, no binaries to build or sign.
- A single pure-JavaScript package removes the entire release surface that a
  Rust core plus npm wrapper would need: per-platform optionalDependencies,
  checksums, zig/cross builds, Gatekeeper questions. None of that earns its
  cost for a script that writes config files and makes two HTTPS calls.
- A Rust CLI can come later for things Node cannot do well. Nothing in the
  v1 flow needs it.

## Compatibility contract

- `engines: ">=18"` and behavior verified on Node 20, 22, and 24. Node 18
  is end-of-life but still common; the wizard uses nothing newer than Node
  16 syntax plus stable built-ins, so it runs everywhere regularly used.
- Minimal runtime dependencies in v1: `@clack/prompts` for the TUI and at
  most `picocolors`. HTTP uses the built-in `fetch` on Node 18+; JSONC
  merging uses a small vendored comment/tail-comma-aware merger (adopt
  `jsonc-parser` as an additional dependency only if the vendored merger
  proves fragile).
- No postinstall scripts, no native modules, no child processes beyond
  spawning nothing (agent detection is PATH lookup only).

## Competitive note

Sail (sailresearch.com) is the reference for agent onboarding: a docs MCP
server, workflow skills, and per-agent config pages. Their agent coverage
comes from serving three protocols from one host: Chat Completions, Responses
(Codex), and Anthropic Messages (Claude Code). Gradiated serves Chat
Completions only, so:

| Agent    | Configurable now | Blocked by                     |
| -------- | ---------------- | ------------------------------ |
| OpenCode | yes              | -                              |
| Codex    | no               | gateway lacks `/v1/responses`; Codex `wire_api` supports only `responses` |
| Claude Code | no            | gateway lacks `/v1/messages` (Anthropic protocol) |

The wizard is structured so adding an agent is one new module, not a rewrite.
When the gateway adds the two routes, the same command covers all three
agents. The docs MCP server idea is independent of the wizard and can be
adopted from Sail's playbook at any time.

## The install flow

`npx -y @gradiated/wizard` (install is the default command):

1. **Detect agents**: check `opencode`, `codex`, `claude` on PATH. Print a
   status table. If only unsupported agents exist, print what would unlock
   them and exit 0 with a link to the docs.
2. **Resolve the key**, in order:
   - `GRADIATED_API_KEY` env var;
   - stored credential at `~/.gradiated/credentials.json` (0600);
   - OpenCode's `auth.json` credential for the `gradiated` provider;
   - offer the branch: **Create a free account ($5 credit)**, **Log in to an
     existing account** (email + code, creates a new `wizard` key), or
     **paste an existing key** — see
     [SIGNUP_ONBOARDING_PLAN.md](SIGNUP_ONBOARDING_PLAN.md) for the account
     and login design. `--key` exists for scripted use but prints a warning
     when stdin is a TTY.
3. **Validate and fetch the catalog**: `GET /openai/v1/models` with the key.
   A failed call is a hard error with the response body's error message, not
   a guess. This step proves the key before anything is written.
4. **Pick the default model**: interactive numbered list from the catalog;
   `--model <id>` for non-interactive use; recommended default first.
5. **Write OpenCode config**:
   - find `opencode.json`, `opencode.jsonc`, or `opencode.json5` (user
     config dir first, then project); create the user-level file if absent;
   - merge `provider.gradiated` with `baseURL`, `apiKey: "{env:GRADIATED_API_KEY}"`,
     and per-model `limit.context` / `limit.output` taken from the catalog
     response;
   - preserve all existing providers and comments (JSONC-aware merge, never a
     full rewrite); write a timestamped `.bak` next to the file before the
     first write in a run;
   - set top-level `model` to `gradiated/<id>` only if unset; report the kept
     value otherwise.
6. **Store the credential**:
   - write `~/.gradiated/credentials.json` (0600);
   - merge the key into `~/.local/share/opencode/auth.json` as the
     `gradiated` provider credential so OpenCode works with no env var (same
     effect as `/connect`);
   - offer (default yes, `--no-env` to skip) to append the
     `export GRADIATED_API_KEY=...` line to the shell profile for shells and
     CI where auth.json is not read.
7. **Smoke test**: one minimal Chat Completions request (`max_tokens: 16`,
   `stream: false`). Print model, prompt/completion tokens, derived cost, and
   wall time. A failure here prints the exact gateway error and what to
   change, and does not roll back the config (the config is correct; the
   problem is account or capacity).
8. **Next steps**: how to start the agent, how to switch models, and the
   unsupported-agent notices for codex/claude when present.

Non-interactive mode: `--yes` skips prompts (first model, no profile edit)
and requires the key to resolve without typing. This is the CI and dotfiles
path.

## Commands and flags

| Command   | Purpose                                                            |
| --------- | ------------------------------------------------------------------ |
| `install` | the flow above; default when invoked bare                          |
| `doctor`  | diagnose: agent versions, key present/valid, config parse, reachability, model availability; exit nonzero on failure |
| `models`  | print the catalog table (id, context, output, price)                |
| `test`    | send one smoke request against the configured or `--model` target   |
| `key`     | `set` (prompt or stdin), `clear`, `status`                          |
| `uninstall` | remove the provider block, auth.json entry, credential file       |

Global flags: `--dry-run` (print the exact writes, change nothing),
`--base-url` (staging), `--agent` (restrict to one), `--yes`, `--json`
(machine-readable output for scripts and docs).

## Architecture

```text
product/cli/wizard/        @gradiated/wizard npm package
  package.json             bin: gradiated-wizard, engines >=18, typed
  src/
    bin.ts                 arg parsing, command dispatch
    agents/opencode.ts     detect, config locate, JSONC merge, auth.json
    agents/codex.ts        stub: status + unlock notice (wire_api=responses)
    agents/claude.ts       stub: status + unlock notice (ANTHROPIC_BASE_URL)
    catalog.ts             fetch /models, normalize limits and prices
    credentials.ts         store/read/clear, 0600 enforcement
    account.ts             signup/login email-code exchange (P2)
    http.ts                fetch wrapper: timeouts, error bodies, retries off
    ui.ts                  clack prompts, theme, spinners
  test/                    vitest suites, incl. e2e against a stub server
  tsconfig.json
```

TypeScript throughout, compiled to ESM and published as JS + `.d.ts`
(`tsc` only; no bundler needed for this shape). Prompts and TUI polish use
[clack](https://github.com/bombshell-dev/clack) (`@clack/prompts`): small,
zero-config, and the same `intro`/`outro`, spinner, `select`, `text`, and
`confirm` primitives the flow needs — no heavyweight framework like Ink for
a dozen prompts. The earlier hand-rolled JSONC merger stays vendored; clack
does not change that.

The earlier `product/website/public/setup.sh` is retired once the wizard
ships; the wizard subsumes it.

## Release and distribution

- npm is the only distribution channel in v1: `npm publish` of
  `@gradiated/wizard` from CI on a `wizard-v*` tag, with `npm provenance`
  enabled through GitHub Actions OIDC.
- No brew tap, no binary releases, no checksums to maintain. The version pin
  problem disappears because `npx -y` always resolves the latest published
  version; a `--version` flag reports it.
- `@gradiated` scope ownership is the supply-chain control: enable 2FA on the
  org, require provenance, and never add dependencies without review.

## Testing

- Unit tests (vitest) for the JSONC merge: comments, trailing commas,
  unknown keys, existing `gradiated` block (replace), missing `$schema`.
- End-to-end tests run the real CLI against a local stub server that serves
  `/openai/v1/models` and `/chat/completions` fixtures, with `HOME`
  pointed at a temp directory, asserting the exact files written (the stub
  and fixtures already exist from the `setup.sh` work).
- `doctor` and `test` run in CI against staging nightly with a staging key
  stored as a secret.
- The wizard is exercised on Node 20, 22, and 24 in the CI matrix.

## Security and privacy

- The key is never logged, never echoed, and never written to any file other
  than the credential store and the shell profile the user approved.
- Credential files are 0600; the wizard refuses a world-readable credentials
  path and fixes it with a warning.
- No telemetry in v1. Usage measurement comes from gateway generations, not
  the client. If telemetry is ever added it is opt-in and documented in the
  privacy page first.
- Two runtime dependencies (`@clack/prompts`, `picocolors`) keep the npm
  supply-chain surface small; provenance and 2FA bound the rest. Never add
  a dependency without review.

## Docs and website changes

- `quickstart.mdx`: the primary path becomes `npx -y @gradiated/wizard`;
  manual steps stay as "Advanced: manual configuration".
- `opencode.mdx`: add an "Automatic setup" section at the top; keep the
  manual JSON for reference and for users who prefer editing config files.
- `index.mdx` and homepage: the CTA becomes the one-liner.
- `codex.mdx`: state the Responses-API dependency and link the roadmap.
- New `docs/wizard.mdx`: command reference generated from `--help` output.

## Roadmap

1. **P1 - OpenCode onboarding**: wizard `install` with OpenCode support,
   `--dry-run`/`--yes`, npm publish with provenance, docs and homepage.
2. **P2 - trust surface**: `doctor`, `models`, `test`, `key`, `uninstall`,
   auth.json merge polish, nightly staging checks.
3. **P3 - full agent coverage**: implement `/v1/messages` then
   `/v1/responses` in the Rust gateway (each needs its own decision record
   and conformance fixtures); add the claude and codex modules to the wizard;
   evaluate a docs MCP server on `docs.gradiated.com`.
4. **Later - Rust CLI**: only if a capability demands it (large binary
   distribution, offline tooling, shared gateway types). The wizard's agent
   modules port directly.

## Decision points

- **Package name**: `@gradiated/wizard` (user decision). Check and hold the
  bare `gradiated` npm name if available.
- **Where the OpenCode key lives**: auth.json merge (primary) plus optional
  env export (compatibility). OpenCode reads `{env:GRADIATED_API_KEY}` from
  the config; the wizard writes both so either path works.
- **Minimum Node**: 18 with a 20/22/24 test matrix; raise to 20 only when
  Node 18 usage in the wild is negligible.
