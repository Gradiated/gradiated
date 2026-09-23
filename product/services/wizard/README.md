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
2. Lets you choose a detected environment key, saved credential, or a quick
   account signup / login (email + code) — or paste an existing key.
3. Fetches the live model catalog with your key to prove it works.
4. Merges the Gradiated provider into each selected agent's configuration.
   It preserves your existing defaults and other providers.
5. Stores the key in `~/.gradiated/credentials.json` (0600). The Codex
   provider and the `claude-gradiated` command read the key from this file.

Both install and uninstall are idempotent: re-running install only rewrites
files that would change (and skips the backup in that case), and re-running
uninstall after everything is removed is a clean no-op.

## Agents

- **OpenCode**: full provider with every catalog model in
  `~/.config/opencode`. The selected model becomes the default unless you
  already chose a model from another provider. Pick another with `/models`.
  The wizard writes plain JSON, so comments in `opencode.jsonc` stay only in
  the `.bak` copy.
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

The wizard stops with an error for an unknown option, a missing option value,
or an extra argument. It also stops when options conflict:

- Use only one of `--key`, `--signup` and `--login`.
- `--dry-run` does not work with `--signup` or `--login`, because they create
  an account and a key.
- `uninstall` accepts only `--agent`, `--dry-run` and `--yes`.

Interactive setup always offers signup, login, and pasting a key alongside any
detected keys. Key values are never displayed. Explicit `--key`, `--signup`,
and `--login` bypass this menu. With `--yes`, or when stdin is not a terminal,
the wizard does not prompt: it uses the environment key first, then the saved
key. OpenCode uses the selected credential saved in its auth store. A dry run
does not offer signup or login.

## Uninstall

```sh
npx -y @gradiated/wizard uninstall
```

The wizard detects which agents have Gradiated configured and lets you
select what to remove: the OpenCode provider and credential, the Codex
provider and profile, the Claude Code wrapper and PATH entry, and the stored
API key. `--agent <name>` limits the run to one agent. `--dry-run` prints the
plan and changes nothing. With `--yes`, or when stdin is not a terminal,
uninstall removes everything it finds without a prompt.

Uninstall restores shell profiles and the Codex config to their earlier
content. It keeps a timestamped `.bak` copy of the OpenCode config and each
Codex file it changes. It changes the OpenCode `auth.json` in place and makes
no backup, so that no extra file holds your keys. It deletes the stored key
file and keeps your own files in `~/.gradiated/bin`. Your other providers are
never touched.

Your key is stored with owner-only permissions and is never printed. No
telemetry. Requires Node 18.3 or later.

## Links

- [Documentation](https://gradiated.com/docs)
- [Console (keys and usage)](https://console.gradiated.com)
- [OpenCode docs](https://opencode.ai/docs/providers/)

## Development verification

From `product/`, run `pnpm --filter @gradiated/wizard check`. The check runs
unit tests in process against a temporary home and end-to-end tests against
the built CLI and a local API fixture. The end-to-end tests put stub agent
commands on `PATH`, so they do not need a coding agent. Install OpenCode, Codex
or Claude Code to also run the checks against that real client.

The publish workflow skips a version that npm already has. Bump `version` in
`package.json` to ship a change. A merge to `main` publishes that version.
