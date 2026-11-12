# Model radar

`.github/workflows/model-radar.yml` posts to `#model-radar` in Slack when a lab
on the watch list publishes a new model. It runs every 15 minutes and can be
started by hand from the Actions tab.

- **Hugging Face** is where weights go live. The radar posts when a new public
  repo appears under a watched org.
- **OpenRouter** usually lists a model when it is announced or gets API access,
  often before the weights. The radar posts when a new model appears under a
  watched prefix.

Both APIs are free and public, so the only secret is the Slack webhook.

## What a run does

1. Restores `seen.json`, the model IDs earlier runs saw, from the Actions
   cache.
2. Lists every repo of each watched Hugging Face org, and every model on
   OpenRouter. It lists every repo, not just the newest, because labs often
   create a repo privately and make it public weeks later, and the repo keeps
   its original creation date.
3. Keeps the models not seen before. It skips OpenRouter's `:free` and `:batch`
   listings and `~lab/...-latest` aliases, which repeat a model already listed.
4. Posts one Slack message per lab per source, with a line per model.
5. Saves the updated IDs to the cache for the next run.

An org or prefix seen for the first time is recorded without posting, so the
first run, and the first run after a lab is added, post nothing. A model that
disappears and comes back is not posted again. If one source fails, the other
still runs, the failed source's IDs are kept, and the run is marked as failed.
If Slack fails, nothing is saved and the next run posts again.

## Add a lab

Add an entry to [`watchlist.json`](watchlist.json) in a pull request:

```json
{ "lab": "Tencent", "huggingface": ["tencent"], "openrouter": ["tencent"] }
```

- `lab`: the name shown in the alert.
- `huggingface`: the lab's orgs, as in `huggingface.co/<org>`. Leave it out
  for a lab that doesn't publish weights.
- `openrouter`: the start of the lab's model IDs, as in
  `openrouter.ai/<prefix>/<model>`. Leave it out for a lab not on OpenRouter.
- `include` (optional): only models whose ID contains one of these words, for
  an org that publishes a lot of unrelated repos, such as `["gemma"]` for
  Google.

The quickest way to find both names is the lab's model page on OpenRouter,
which links to its Hugging Face repo. The pull request runs the tests, which
check the file, and a dry run against the real APIs. The new lab posts from
its next new model after the pull request merges.

## Dry run

Run the workflow by hand with **dry run** checked, or locally:

```bash
mise exec -- node tools/model-radar/main.ts --dry-run
```

A dry run prints the alerts it would send and saves nothing. Locally,
`MODEL_RADAR_STATE` sets the seen-IDs file (default
`.agents/runtime/model-radar/seen.json`). With no file yet, every org and
prefix is new, so it prints what it would record and no alerts.

## Setup

- A Slack app with an incoming webhook for `#model-radar`, stored as the
  `MODEL_RADAR_SLACK_WEBHOOK` repository secret. Scheduled runs fail with a
  clear error until it is set.

## Code

Each part is handed what it uses (`fetch`, a file path, the webhook URL), so
the tests pass fakes in and never replace anything global.

- [`main.ts`](main.ts) reads the environment and wires the parts together.
- [`radar.ts`](radar.ts) runs one scan: compare, alert, save.
- [`huggingface.ts`](huggingface.ts) and [`openrouter.ts`](openrouter.ts) list
  models. Each implements `Source` from [`model.ts`](model.ts).
- [`notifiers.ts`](notifiers.ts) has `SlackNotifier` and `ConsoleNotifier`.
  Another channel is another class implementing `Notifier`.
- [`seen-store.ts`](seen-store.ts) reads and writes `seen.json`.
- [`watchlist.ts`](watchlist.ts) reads and checks `watchlist.json`.

Run the tests and the type check:

```bash
mise exec -- node --test tools/model-radar/*.test.ts
cd product && pnpm exec tsc -p ../tools/model-radar/tsconfig.json
```
