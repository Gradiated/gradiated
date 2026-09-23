#!/usr/bin/env node
import { createRequire } from "node:module";
import { parseArguments } from "./arguments.js";
import { runInstall } from "./commands/install.js";
import { runUninstall } from "./commands/uninstall.js";
import { failureMessage } from "./errors.js";
import { isRecord } from "./guards.js";
import { resolveWizardPaths } from "./paths.js";
import * as ui from "./ui.js";

const HELP = `Gradiated setup wizard

Usage:
  npx -y @gradiated/wizard [command] [options]

Commands:
  install      Configure your coding agent (default)
  uninstall    Remove Gradiated from your coding agents

Both commands are safe to run repeatedly; re-running install only rewrites
files that would change.

Options:
  --signup            Create a new account (skips the menu)
  --login             Log in to an existing account (skips the menu)
  --key <key>         Use this API key instead of signing in
  --agent <name>      Restrict the run to opencode, codex, or claude
  --model <id>        Use this model from the catalog
  --api-base-url <u>  Override the API base URL (staging)
  --dry-run           Show what would be written; change nothing
  --yes               Non-interactive: first model, no extra prompts
  --help              Show this help
  --version           Show the version
`;

const packageVersion = (): string => {
  const manifest: unknown = createRequire(import.meta.url)("../package.json");
  if (isRecord(manifest) && typeof manifest.version === "string") {
    return manifest.version;
  }

  throw new Error("The package manifest has no version.");
};

const main = async (): Promise<void> => {
  const command = parseArguments(process.argv.slice(2), {
    stdinIsTTY: Boolean(process.stdin.isTTY),
    environmentKey: process.env.GRADIATED_API_KEY || null,
  });

  switch (command.kind) {
    case "help":
      console.log(HELP);
      return;
    case "version":
      console.log(packageVersion());
      return;
    case "install":
      await runInstall(command.options, resolveWizardPaths());
      return;
    case "uninstall":
      await runUninstall(command.options, resolveWizardPaths());
      return;
  }
};

main().catch((error: unknown) => {
  ui.fail(failureMessage(error));
});
