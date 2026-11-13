// Runs the radar once. The only file that reads the environment and builds
// the real objects; everything else is handed what it uses.
//
//   node tools/model-radar/main.ts            scan, post to Slack, save
//   node tools/model-radar/main.ts --dry-run  scan and print, save nothing
//
// Environment:
//   MODEL_RADAR_SLACK_WEBHOOK  Slack incoming webhook (not needed for --dry-run)
//   MODEL_RADAR_STATE          seen-IDs file (default .agents/runtime/model-radar/seen.json)

import { readFile } from "node:fs/promises";
import process from "node:process";
import { HuggingFaceSource } from "./huggingface.ts";
import type { Notifier } from "./model.ts";
import { ConsoleNotifier, SlackNotifier } from "./notifiers.ts";
import { OpenRouterSource } from "./openrouter.ts";
import { Radar } from "./radar.ts";
import { SeenStore } from "./seen-store.ts";
import { Watchlist } from "./watchlist.ts";

const dryRun = process.argv.includes("--dry-run");
const webhook = process.env.MODEL_RADAR_SLACK_WEBHOOK ?? "";
const statePath =
  process.env.MODEL_RADAR_STATE || ".agents/runtime/model-radar/seen.json";

if (!dryRun && !webhook) {
  console.error(
    "MODEL_RADAR_SLACK_WEBHOOK is not set. Use --dry-run to print alerts instead.",
  );
  process.exit(1);
}

const watchlist = Watchlist.parse(
  JSON.parse(
    await readFile(new URL("./watchlist.json", import.meta.url), "utf8"),
  ),
);
const notifiers: Notifier[] = [
  new ConsoleNotifier((line) => console.log(line)),
  ...(dryRun ? [] : [new SlackNotifier(fetch, webhook)]),
];

const { failures } = await new Radar({
  sources: [
    new HuggingFaceSource(fetch, watchlist.owners("Hugging Face")),
    new OpenRouterSource(fetch, watchlist.owners("OpenRouter")),
  ],
  watchlist,
  store: new SeenStore(statePath),
  notifiers,
  log: (line) => console.log(line),
  save: !dryRun,
}).run();

if (dryRun) console.log("Dry run: nothing was sent or saved.");
if (failures.length) process.exit(1);
