#!/usr/bin/env node
import { CONSOLE_URL, parseArguments } from "./arguments.js";
import { resolveAccount } from "./account.js";
import { fetchCatalog, type CatalogModel } from "./catalog.js";
import { readStoredKey, storeKey } from "./credentials.js";
import { HttpError } from "./http.js";
import { detectAgents } from "./agents/detect.js";
import * as claude from "./agents/claude.js";
import * as codex from "./agents/codex.js";
import {
  buildProviderBlock,
  locateConfig,
  mergeAuthCredential,
  mergeProvider,
  readConfigDocument,
  uninstallAuthCredential,
  uninstallConfig as uninstallOpenCodeConfig,
  isInstalled as openCodeInstalled,
  writeConfig,
} from "./agents/opencode.js";
import * as ui from "./ui.js";

const HELP = `Gradiated setup wizard

Usage:
  npx -y @gradiated/wizard [command] [options]

Commands:
  install      Configure your coding agent (default)
  uninstall    Remove Gradiated from your coding agents

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

const validateCatalogKey = async (
  inferenceBaseUrl: string,
  apiKey: string,
): Promise<CatalogModel[]> => {
  try {
    return await fetchCatalog(inferenceBaseUrl, apiKey);
  } catch (error) {
    if (error instanceof HttpError && error.status === 401) {
      ui.fail(`The API key was rejected: ${error.message}`);
    }
    if (error instanceof HttpError) {
      ui.fail(
        `Could not fetch the model catalog (${error.status || "network"}): ${error.message}`,
      );
    }
    throw error;
  }
};

const pickModel = async (
  models: readonly CatalogModel[],
  options: { yes: boolean; requested: string | undefined },
): Promise<CatalogModel> => {
  const first = models[0];
  if (first === undefined) {
    ui.fail("The model catalog is empty.");
  }
  if (options.requested !== undefined) {
    const requested = options.requested.toLowerCase();
    const match = models.find((model) => model.id.toLowerCase() === requested);
    if (match === undefined) {
      ui.fail(
        `Model "${options.requested}" is not in the catalog. Available: ${models.map((model) => model.id).join(", ")}`,
      );
    }
    return match;
  }
  if (options.yes || models.length === 1) {
    return first;
  }
  const choice = await ui.selectOption(
    "Which model should Gradiated use by default?",
    models.map((model) => ({
      value: model.id,
      label: model.name,
      hint: model.id,
    })),
  );
  return models.find((model) => model.id === choice) ?? first;
};

const resolveKey = async (
  options: { yes: boolean; key: string | undefined; mode: string },
  targets: { apiBaseUrl: string; inferenceBaseUrl: string },
): Promise<string> => {
  const environmentKey = process.env.GRADIATED_API_KEY;
  if (environmentKey !== undefined && environmentKey.length > 0) {
    ui.info("Using GRADIATED_API_KEY from the environment.");
    return environmentKey;
  }
  const stored = await readStoredKey();
  if (stored !== null) {
    ui.info("Using the stored key from ~/.gradiated/credentials.json.");
    return stored;
  }
  if (options.key !== undefined) {
    return options.key;
  }

  if (options.mode === "login" || options.mode === "signup") {
    const account = await resolveAccount(targets);
    return account.apiKey;
  }

  if (options.yes) {
    ui.fail(
      `No Gradiated key found. Create one at ${CONSOLE_URL} or run without --yes.`,
    );
  }

  const choice = await ui.selectOption<"signup" | "login" | "paste">(
    "No Gradiated key found. What would you like to do?",
    [
      {
        value: "signup",
        label: "Create a free account",
        hint: "free credit included",
      },
      { value: "login", label: "Log in to an existing account" },
      { value: "paste", label: "Paste an existing API key" },
    ],
  );
  if (choice === "paste") {
    return ui.askPassword(`Paste your API key (create one at ${CONSOLE_URL}):`);
  }
  const account = await resolveAccount(targets);
  return account.apiKey;
};

const runInstall = async (): Promise<void> => {
  const options = parseArguments(process.argv.slice(2)).options;
  const targets = {
    apiBaseUrl: options.apiBaseUrl,
    inferenceBaseUrl: options.inferenceBaseUrl,
  };

  ui.intro("Gradiated setup");

  const agents = detectAgents();
  ui.agentTable(
    agents.map((agent) => ({
      name: agent.name,
      found: agent.found,
    })),
  );

  // Claude needs detection only for a friendlier table: the wrapper is a
  // standalone script, so it can be installed before claude itself is.
  const claudeRequested = options.agent === "claude";
  const claudeOnPath = agents.some(
    (agent) => agent.name === "claude" && agent.found,
  );
  if (claudeRequested && !claudeOnPath) {
    ui.warn(
      "'claude' was not found on PATH. Installing the wrapper anyway; install Claude Code before using it.",
    );
  }

  const selectedAgents = agents.filter(
    (agent) =>
      (agent.found || (agent.name === "claude" && claudeRequested)) &&
      (options.agent === undefined || agent.name === options.agent),
  );
  if (options.agent !== undefined && selectedAgents.length === 0) {
    ui.fail(
      `${options.agent} is not installed or is not on PATH. Install it, then run this wizard again.`,
    );
  }
  if (selectedAgents.length === 0) {
    ui.outro(
      "No supported coding agent was found. Install OpenCode, Codex, or Claude Code, then run this wizard again.",
    );
    return;
  }

  const apiKey = await resolveKey(options, targets);
  const models = await validateCatalogKey(targets.inferenceBaseUrl, apiKey);
  const model = await pickModel(models, {
    yes: options.yes,
    requested: options.model,
  });

  const configureOpenCode = selectedAgents.some(
    (agent) => agent.name === "opencode",
  );
  const configureCodex = selectedAgents.some((agent) => agent.name === "codex");
  const configureClaude = selectedAgents.some(
    (agent) => agent.name === "claude",
  );

  // OpenCode receives the full catalog so /models offers every Gradiated
  // model. Codex receives an opt-in profile for the selected model.
  const openCodeProvider = configureOpenCode
    ? buildProviderBlock(options.inferenceBaseUrl, models)
    : null;
  const codexProvider = configureCodex
    ? codex.buildProviderBlock(options.apiBaseUrl)
    : null;
  const codexProfile = configureCodex
    ? codex.buildProfileBlock(model.id)
    : null;

  if (options.dryRun) {
    if (openCodeProvider !== null) {
      ui.note(
        JSON.stringify(openCodeProvider, null, 2),
        "Would write this OpenCode provider",
      );
    }
    if (codexProvider !== null && codexProfile !== null) {
      ui.note(codexProvider, `Would merge into ${codex.configPath()}`);
      ui.note(codexProfile, `Would write ${codex.profilePath()}`);
    }
    if (configureClaude) {
      ui.note(
        `Would write ${claude.wrapperPath()} and add it to PATH`,
        "Claude Code wrapper",
      );
    }
    ui.outro("Dry run complete. No files were changed.");
    return;
  }

  if (openCodeProvider !== null) {
    const located = locateConfig();
    const document = await readConfigDocument(located);
    const { document: merged, defaultModel } = mergeProvider(
      document,
      openCodeProvider,
    );
    const configPath = await writeConfig(located, merged);
    ui.success(
      `Wrote the Gradiated provider to ${configPath}` +
        (defaultModel !== null ? ` (default model: ${defaultModel})` : ""),
    );
  }

  if (codexProvider !== null) {
    const written = await codex.writeConfig(options.apiBaseUrl, model.id);
    ui.success(`Wrote the Gradiated Codex provider to ${written.configPath}.`);
    ui.success(`Wrote the Gradiated Codex profile to ${written.profilePath}.`);
  }

  await storeKey(apiKey);
  ui.success("Stored the key in ~/.gradiated/credentials.json (0600).");

  if (configureOpenCode) {
    const authWritten = await mergeAuthCredential(apiKey);
    if (authWritten !== null) {
      ui.success(`Stored the credential for OpenCode in ${authWritten}.`);
    }
  }

  let claudePathUpdated: string[] = [];
  if (configureClaude) {
    const wrapper = await claude.writeWrapper(options.apiBaseUrl, model.id);
    ui.success(`Installed the claude-gradiated wrapper at ${wrapper}.`);
    claudePathUpdated = await claude.addWrapperToPath();
    if (claudePathUpdated.length > 0) {
      ui.success(
        `Added ~/.gradiated/bin to PATH in ${claudePathUpdated.join(", ")}.`,
      );
    } else if (!(await claude.hasWrapperOnPath())) {
      ui.warn(
        `Add this to your shell profile to use the wrapper:\n  export PATH="$HOME/.gradiated/bin:$PATH"`,
      );
    } else {
      ui.success("PATH already contains the Gradiated wrapper directory.");
    }
  }

  const modelsLine = models.map((entry) => entry.name).join(", ");
  const nextSteps = [
    ...(configureOpenCode
      ? [
          `OpenCode:\n  opencode\nThen use /models to switch between ${modelsLine}.`,
        ]
      : []),
    ...(configureCodex
      ? [
          "Codex:\n  codex --profile gradiated\nUse -m <model-id> to select another Gradiated model.",
        ]
      : []),
    ...(configureClaude
      ? [
          "Claude Code:\n  claude-gradiated\nYour normal `claude` is unchanged.\n  /model <id>                      switch models in a session\n  ANTHROPIC_MODEL=<id> claude-gradiated   override for one run\nNote: Claude Pro/Max login does not work through a custom gateway —\nclaude-gradiated is for Anthropic API-key setups.",
        ]
      : []),
  ].join("\n\n");
  const agentNames = selectedAgents.map((agent) => agent.name).join(" and ");
  ui.outro(
    `Ready. Gradiated is configured for ${agentNames}.\n\n${nextSteps}\n\nAffordable inference for open-weight models — https://gradiated.com/docs`,
  );
};

type UninstallTarget = "opencode" | "codex" | "claude" | "key";

interface UninstallSelection {
  targets: readonly UninstallTarget[];
}

const detectUninstallTargets = async (): Promise<UninstallTarget[]> => {
  const present: UninstallTarget[] = [];
  if (await openCodeInstalled()) present.push("opencode");
  if (await codex.isInstalled()) present.push("codex");
  if (claude.isWrapperInstalled()) present.push("claude");
  if ((await readStoredKey()) !== null) present.push("key");
  return present;
};

const runUninstall = async (): Promise<void> => {
  const options = parseArguments(process.argv.slice(2)).options;
  ui.intro("Gradiated uninstall");

  const present = await detectUninstallTargets();
  if (present.length === 0) {
    ui.outro("No Gradiated configuration was found. Nothing to remove.");
    return;
  }

  const labels: Record<UninstallTarget, { label: string; hint: string }> = {
    opencode: {
      label: "OpenCode",
      hint: "provider block and credential in auth.json",
    },
    codex: {
      label: "Codex",
      hint: "provider block and gradiated profile",
    },
    claude: {
      label: "Claude Code wrapper",
      hint: "claude-gradiated command and PATH entry",
    },
    key: {
      label: "Stored API key",
      hint: "~/.gradiated/credentials.json",
    },
  };

  let selection: readonly UninstallTarget[];
  const preset =
    options.agent !== undefined
      ? present.filter((target) => target === options.agent)
      : present;
  if (options.yes) {
    selection = preset;
  } else if (options.dryRun) {
    selection = present;
  } else {
    selection = await ui.selectMany<UninstallTarget>(
      "Which agents should Gradiated be removed from?",
      present.map((target) => ({
        value: target,
        label: labels[target].label,
        hint: labels[target].hint,
      })),
    );
    if (selection.length === 0) {
      ui.outro("Nothing selected. No files were changed.");
      return;
    }
    const proceed = await ui.confirm(
      "Remove the selected configuration? Backups (.bak) are kept.",
    );
    if (!proceed) {
      ui.outro("Cancelled. No files were changed.");
      return;
    }
  }
  const confirmed: UninstallSelection = { targets: selection };

  const removed: string[] = [];
  for (const target of confirmed.targets) {
    if (target === "opencode") {
      const configPath = await uninstallOpenCodeConfig();
      const authPath = await uninstallAuthCredential();
      if (configPath !== null) removed.push(`OpenCode config (${configPath})`);
      if (authPath !== null) removed.push(`OpenCode credential (${authPath})`);
    }
    if (target === "codex") {
      const configRemoved = await codex.uninstallConfig();
      const profileRemoved = await codex.uninstallProfile();
      const authRemoved = await codex.removeAuth();
      if (configRemoved) removed.push(`Codex provider (${codex.configPath()})`);
      if (profileRemoved)
        removed.push(`Codex profile (${codex.profilePath()})`);
      if (authRemoved) removed.push(`Codex credential (${codex.authPath()})`);
    }
    if (target === "claude") {
      const wrapperPath = await claude.uninstallWrapper();
      const profilesUpdated = await claude.removeWrapperFromPath();
      if (wrapperPath !== null)
        removed.push(`claude-gradiated wrapper (${wrapperPath})`);
      for (const profile of profilesUpdated) {
        removed.push(`PATH entry (${profile})`);
      }
    }
    if (target === "key") {
      const { clearStoredKey } = await import("./credentials.js");
      const path = await clearStoredKey();
      if (path !== null) removed.push(`Stored key (${path})`);
    }
  }

  if (removed.length === 0) {
    ui.outro("Nothing to remove for the selected agents.");
    return;
  }
  ui.outro(
    `Removed Gradiated configuration from:\n${removed.map((entry) => `  - ${entry}`).join("\n")}\n\nBackups with a .bak timestamp were kept next to each changed file.`,
  );
};

const main = async (): Promise<void> => {
  const parsed = parseArguments(process.argv.slice(2));
  if (parsed.command === "help") {
    console.log(HELP);
    return;
  }
  if (parsed.command === "version") {
    console.log("0.2.2");
    return;
  }
  if (parsed.command === "uninstall") {
    await runUninstall();
    return;
  }
  await runInstall();
};

main().catch((error: unknown) => {
  if (error instanceof HttpError) {
    ui.fail(error.message);
  }
  ui.fail(error instanceof Error ? error.message : "Unexpected failure.");
});
