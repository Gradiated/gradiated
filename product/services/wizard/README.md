# @gradiated/wizard

Set up [Gradiated](https://gradiated.com) inference for your coding agent in
one command:

```sh
npx -y @gradiated/wizard
```

Gradiated hosts exact open-weight models behind an OpenAI-compatible API.
The wizard signs you up (free credit included) or logs you in with a
six-digit email code, then writes the provider block into your OpenCode
config. No manual JSON editing, no browser, no card.

## What it does

1. Detects your coding agents (OpenCode, Codex, Claude Code).
2. Resolves an API key: environment, stored credential, or a quick
   account signup / login (email + code) — or paste an existing key.
3. Fetches the live model catalog with your key to prove it works.
4. Merges the Gradiated provider into your OpenCode config, preserving
   everything already there (a backup is written first).
5. Stores the key in `~/.gradiated/credentials.json` (0600) and OpenCode's
   own credential store.

Start OpenCode and run `/models` to pick a Gradiated model.

## Codex and Claude Code

These agents are detected but not configured yet: Codex speaks only the
Responses API and Claude Code the Anthropic Messages API. Gradiated's
protocol coverage is listed in [the docs](https://gradiated.com/docs).

## Options

```text
--signup            Create a new account (skips the menu)
--login             Log in to an existing account (skips the menu)
--key <key>         Use this API key instead of signing in
--model <id>        Use this model from the catalog
--api-base-url <u>  Override the API base URL (staging)
--dry-run           Show what would be written; change nothing
--yes               Non-interactive: first model, no extra prompts
```

Your key is stored with owner-only permissions and is never printed. No
telemetry. Requires Node 18+.

## Links

- [Documentation](https://gradiated.com/docs)
- [Console (keys and usage)](https://console.gradiated.com)
- [OpenCode docs](https://opencode.ai/docs/providers/)
