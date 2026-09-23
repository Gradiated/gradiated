import { join } from "node:path";
import type { CatalogModel } from "../catalog.js";
import {
  formatJson,
  readJsonObject,
  readTextIfExists,
  writeIfChanged,
} from "../files.js";
import { isRecord } from "../guards.js";
import { parseJsonc } from "../jsonc.js";
import type { WizardPaths } from "../paths.js";
import type { AgentIntegration } from "./agent.js";

const CONFIG_FILENAMES = [
  "opencode.json",
  "opencode.jsonc",
  "opencode.json5",
] as const;

const PROVIDER_ID = "gradiated";
const MODEL_PREFIX = `${PROVIDER_ID}/`;

export interface OpenCodeProvider {
  npm: "@ai-sdk/openai-compatible";
  name: "Gradiated";
  options: { baseURL: string };
  models: Record<
    string,
    { name: string; limit?: { context: number; output: number } }
  >;
}

interface OpenCodeConfig {
  path: string;
  document: Record<string, unknown>;
}

export const authPath = (paths: WizardPaths): string =>
  join(paths.home, ".local", "share", "opencode", "auth.json");

const readConfig = async (paths: WizardPaths): Promise<OpenCodeConfig> => {
  const directory = join(paths.home, ".config", "opencode");

  for (const filename of CONFIG_FILENAMES) {
    const path = join(directory, filename);
    const text = await readTextIfExists(path);
    if (text !== null) return { path, document: parseJsonc(path, text) };
  }

  return { path: join(directory, CONFIG_FILENAMES[0]), document: {} };
};

const providersOf = (document: Record<string, unknown>) =>
  isRecord(document.provider) ? document.provider : {};

export const buildProvider = (
  apiBaseUrl: string,
  models: readonly CatalogModel[],
): OpenCodeProvider => ({
  npm: "@ai-sdk/openai-compatible",
  name: "Gradiated",
  options: { baseURL: apiBaseUrl },
  models: Object.fromEntries(
    models.map((model) => [
      model.id,
      model.limit === null
        ? { name: model.name }
        : { name: model.name, limit: model.limit },
    ]),
  ),
});

const isGradiatedModel = (model: unknown): boolean =>
  typeof model === "string" && model.startsWith(MODEL_PREFIX);

const defaultModel = (
  document: Record<string, unknown>,
  modelId: string,
): string =>
  typeof document.model === "string" &&
  document.model.length > 0 &&
  !isGradiatedModel(document.model)
    ? document.model
    : `${MODEL_PREFIX}${modelId}`;

export const mergeProvider = (
  document: Record<string, unknown>,
  provider: OpenCodeProvider,
  modelId: string,
): Record<string, unknown> => ({
  // OpenCode validates against this schema; new files must carry it.
  $schema: "https://opencode.ai/config.json",
  ...document,
  model: defaultModel(document, modelId),
  provider: { ...providersOf(document), [PROVIDER_ID]: provider },
});

export const removeProvider = (
  document: Record<string, unknown>,
): Record<string, unknown> => {
  const providers = { ...providersOf(document) };
  delete providers[PROVIDER_ID];

  const result: Record<string, unknown> = { ...document, provider: providers };
  if (isGradiatedModel(result.model)) delete result.model;

  return result;
};

export const writeProvider = async (
  paths: WizardPaths,
  provider: OpenCodeProvider,
  modelId: string,
): Promise<{ path: string; changed: boolean; defaultModel: string }> => {
  const config = await readConfig(paths);
  const merged = mergeProvider(config.document, provider, modelId);
  const changed = await writeIfChanged(config.path, formatJson(merged), {
    backup: true,
  });

  return {
    path: config.path,
    changed,
    defaultModel: defaultModel(config.document, modelId),
  };
};

export const mergeAuthCredential = async (
  paths: WizardPaths,
  apiKey: string,
): Promise<boolean> => {
  const path = authPath(paths);
  const document = (await readJsonObject(path)) ?? {};
  const existing = isRecord(document.gradiated) ? document.gradiated : {};

  return writeIfChanged(
    path,
    formatJson({
      ...document,
      gradiated: { ...existing, type: "api", key: apiKey },
    }),
    { mode: 0o600 },
  );
};

const hasProvider = async (paths: WizardPaths): Promise<boolean> => {
  const { document } = await readConfig(paths);

  return providersOf(document)[PROVIDER_ID] !== undefined;
};

const hasAuthCredential = async (paths: WizardPaths): Promise<boolean> =>
  (await readJsonObject(authPath(paths)))?.gradiated !== undefined;

export const isConfigured = async (paths: WizardPaths): Promise<boolean> =>
  (await hasProvider(paths)) || (await hasAuthCredential(paths));

export const uninstallConfig = async (
  paths: WizardPaths,
): Promise<string | null> => {
  const config = await readConfig(paths);
  if (providersOf(config.document)[PROVIDER_ID] === undefined) return null;

  const document = removeProvider(config.document);
  await writeIfChanged(config.path, formatJson(document), { backup: true });

  return config.path;
};

export const uninstallAuthCredential = async (
  paths: WizardPaths,
): Promise<string | null> => {
  const path = authPath(paths);
  const document = await readJsonObject(path);
  if (document?.gradiated === undefined) return null;

  delete document.gradiated;
  await writeIfChanged(path, formatJson(document), { mode: 0o600 });

  return path;
};

export const openCode: AgentIntegration = {
  name: "opencode",
  label: "OpenCode",
  uninstallHint: "provider block and credential in auth.json",
  runsWithoutClient: false,
  isConfigured,
  preview: (setup) => [
    {
      title: "Would write this OpenCode provider",
      body: JSON.stringify(
        buildProvider(setup.apiBaseUrl, setup.models),
        null,
        2,
      ),
    },
  ],
  install: async (setup, paths) => {
    const provider = buildProvider(setup.apiBaseUrl, setup.models);
    const config = await writeProvider(paths, provider, setup.model.id);
    const authChanged = await mergeAuthCredential(paths, setup.apiKey);
    const modelNames = setup.models.map((model) => model.name).join(", ");

    return {
      changes: [
        ...(config.changed
          ? [
              `OpenCode provider in ${config.path} (default model: ${config.defaultModel})`,
            ]
          : []),
        ...(authChanged ? [`OpenCode credential in ${authPath(paths)}`] : []),
      ],
      nextStep: {
        action: "run `opencode`",
        notes: [`/models switches between ${modelNames}`],
      },
    };
  },
  uninstall: async (paths) => {
    const config = await uninstallConfig(paths);
    const auth = await uninstallAuthCredential(paths);

    return {
      removed: [
        ...(config === null ? [] : [`OpenCode config (${config})`]),
        ...(auth === null ? [] : [`OpenCode credential (${auth})`]),
      ],
      backedUp: config !== null,
    };
  },
};
