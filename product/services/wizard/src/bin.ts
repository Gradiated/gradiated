#!/usr/bin/env node
import {
  DEFAULT_API_BASE_URL,
  INFERENCE_BASE_URL,
  CONSOLE_URL,
  parseArguments,
} from "./arguments.js";
import { resolveAccount } from "./account.js";
import { fetchCatalog, type CatalogModel } from "./catalog.js";
import { readStoredKey, storeKey } from "./credentials.js";
import { HttpError } from "./http.js";
import { detectAgents } from "./agents/detect.js";
import {
  authPath,
  buildProviderBlock,
  locateConfig,
  mergeAuthCredential,
  mergeProvider,
  readConfigDocument,
  writeConfig,
} from "./agents/opencode.js";
import * as ui from "./ui.js";

const HELP = `Gradiated setup wizard

Usage:
  npx -y @gradiated/wizard [command] [options]

Commands:
  install      Configure your coding agent (default)

Options:
  --signup            Create a new account (skips the menu)
  --login             Log in to an existing account (skips the menu)
  --key <key>         Use this API key instead of signing in
  --model <id>        Use this model from the catalog
  --api-base-url <u>  Override the API base URL (staging)
  --dry-run           Show what would be written; change nothing
  --yes               Non-interactive: first model, no extra prompts
  --help              Show this help
  --version           Show the version
`;

const SUPPORTED_NOTES: Record<string, string | undefined> = {
  codex: "needs the Responses API; see gradiated.com/docs/codex",
  claude: "needs the Anthropic Messages API; see gradiated.com/docs/codex",
};

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
    "Which model should OpenCode use by default?",
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
        hint: "$5 of credit included",
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
      ...(SUPPORTED_NOTES[agent.name] !== undefined
        ? { note: SUPPORTED_NOTES[agent.name] }
        : {}),
    })),
  );

  if (!agents.some((agent) => agent.name === "opencode" && agent.found)) {
    ui.outro(
      "OpenCode is not installed. Install it with:\n  curl -fsSL https://opencode.ai/install | bash\nThen run this wizard again.",
    );
    return;
  }

  const apiKey = await resolveKey(options, targets);
  const models = await validateCatalogKey(targets.inferenceBaseUrl, apiKey);
  const model = await pickModel(models, {
    yes: options.yes,
    requested: options.model,
  });

  // Write the full catalog so /models offers every Gradiated model; the
  // default selection only sets the top-level "model" key.
  const configured = buildProviderBlock(options.inferenceBaseUrl, models);

  if (options.dryRun) {
    ui.note(
      JSON.stringify(configured, null, 2),
      "Would write this provider block",
    );
    ui.outro("Dry run complete. No files were changed.");
    return;
  }

  const located = locateConfig();
  const document = await readConfigDocument(located);
  const { document: merged, defaultModel } = mergeProvider(
    document,
    configured,
  );
  const configPath = await writeConfig(located, merged);
  ui.success(
    `Wrote the Gradiated provider to ${configPath}` +
      (defaultModel !== null ? ` (default model: ${defaultModel})` : ""),
  );

  await storeKey(apiKey);
  ui.success("Stored the key in ~/.gradiated/credentials.json (0600).");

  const authWritten = await mergeAuthCredential(apiKey);
  if (authWritten !== null) {
    ui.success(`Stored the credential for OpenCode in ${authWritten}.`);
  }

  ui.outro(
    `Done. Start coding:\n  opencode\n\nGradiated serves exact open-weight models with no markup. Docs: https://gradiated.com/docs`,
  );
};

const main = async (): Promise<void> => {
  const parsed = parseArguments(process.argv.slice(2));
  if (parsed.command === "help") {
    console.log(HELP);
    return;
  }
  if (parsed.command === "version") {
    console.log("0.1.0");
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
