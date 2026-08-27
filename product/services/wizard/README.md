# @gradiated/wizard

Set up [Gradiated](https://gradiated.com) inference for your coding agent in
one command:

```sh
npx -y @gradiated/wizard
```

Gradiated hosts exact open-weight models behind an OpenAI-compatible API.
The wizard signs you up (free credit included) or logs you in with a
six-digit email code, then configures OpenCode, Codex, or both. No manual
configuration editing, no browser, no card.

## What it does

1. Detects supported coding agents (OpenCode and Codex).
2. Resolves an API key: environment, stored credential, or a quick
   account signup / login (email + code) — or paste an existing key.
3. Fetches the live model catalog with your key to prove it works.
4. Merges the Gradiated provider into the selected agent configuration.
   It preserves the normal Codex profile and the existing OpenCode default.
5. Stores the key in `~/.gradiated/credentials.json` (0600). OpenCode also
   receives its provider credential.

Start OpenCode and run `/models` to pick a Gradiated model. Start Codex with:

```sh
codex --profile gradiated
```

## Claude Code

Use the [manual Claude Code setup](https://gradiated.com/docs/claude-code/).
The wizard does not change the global Claude Code route.

## Options

```text
--signup            Create a new account (skips the menu)
--login             Log in to an existing account (skips the menu)
--key <key>         Use this API key instead of signing in
--agent <name>      Restrict the run to opencode or codex
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
provider and profile, and the stored API key. Timestamped backups of every
changed file are kept. Your other providers are never touched.

Your key is stored with owner-only permissions and is never printed. No
telemetry. Requires Node 18+.

## Links

- [Documentation](https://gradiated.com/docs)
- [Console (keys and usage)](https://console.gradiated.com)
- [OpenCode docs](https://opencode.ai/docs/providers/)
