# @gradiated/wizard

Set up [Gradiated](https://gradiated.com) inference for your coding agent in
one command:

```sh
npx -y @gradiated/wizard
```

Gradiated hosts exact open-weight models behind an OpenAI-compatible API.
The wizard signs you up (free credit included) or logs you in with a
six-digit email code, then configures your coding agents. No manual
configuration editing, no browser, no card.

## What it does

1. Detects supported coding agents (OpenCode, Codex, Claude Code).
2. Resolves an API key: environment, stored credential, or a quick
   account signup / login (email + code) — or paste an existing key.
3. Fetches the live model catalog with your key to prove it works.
4. Merges the Gradiated provider into each selected agent's configuration.
   It preserves your existing defaults and other providers.
5. Stores the key in `~/.gradiated/credentials.json` (0600).

Both install and uninstall are idempotent: re-running install only rewrites
files that would change (and skips the backup in that case), and re-running
uninstall after everything is removed is a clean no-op.

## Agents

- **OpenCode**: full provider with every catalog model. Pick one with
  `/models`.
- **Codex**: an opt-in `gradiated` provider and profile. Start with
  `codex --profile gradiated`. Your default Codex provider is unchanged.
- **Claude Code**: a `claude-gradiated` command installed to
  `~/.gradiated/bin` and added to your shell PATH (zsh, bash and fish). The
  wizard detects your shell and prints the exact command to enable it in the
  current terminal (e.g. `source ~/.zshrc`); otherwise open a new terminal.
  Your normal `claude` is unchanged. See the
  [Claude Code docs](https://gradiated.com/docs/claude-code/).

## Options

```text
--signup            Create a new account (skips the menu)
--login             Log in to an existing account (skips the menu)
--key <key>         Use this API key instead of signing in
--agent <name>      Restrict the run to opencode, codex, or claude
--model <id>        Use this model from the catalog
--api-base-url <u>  Override the API base URL (staging)
--dry-run           Show what would be written; change nothing
--yes               Non-interactive: first model, no extra prompts
```

## Uninstall

```sh
npx -y @gradiated/wizard uninstall
```

The wizard detects which agents have Gradiated configured and lets you
multiselect what to remove: the OpenCode provider and credential, the Codex
provider and profile, the Claude Code wrapper and PATH entry, and the stored
API key. `--agent <name>` scopes detection and output to one agent, and
`--dry-run` prints the plan without touching anything. Timestamped backups
of every changed file are kept. Your other providers are never touched.

Your key is stored with owner-only permissions and is never printed. No
telemetry. Requires Node 18+.

## Links

- [Documentation](https://gradiated.com/docs)
- [Console (keys and usage)](https://console.gradiated.com)
- [OpenCode docs](https://opencode.ai/docs/providers/)
