import { rm } from "node:fs/promises";
import { join } from "node:path";
import { WizardError } from "../errors.js";
import {
  appendManagedBlock,
  backupFile,
  hasManagedBlock,
  prependManagedBlock,
  readTextIfExists,
  removeManagedBlock,
  writeIfChanged,
  type BlockMarkers,
} from "../files.js";
import type { WizardPaths } from "../paths.js";
import type { AgentIntegration, GatewayModel } from "./agent.js";

const MARKERS: BlockMarkers = {
  start: "# --- Gradiated (added by @gradiated/wizard) ---",
  end: "# --- End Gradiated ---",
};

const credentialHelper = (credentialsPath: string): string =>
  `process.stdout.write(JSON.parse(require("node:fs").readFileSync(${JSON.stringify(credentialsPath)},"utf8")).api_key)`;

export const codexFiles = (paths: WizardPaths) => ({
  config: join(paths.home, ".codex", "config.toml"),
  profile: join(paths.home, ".codex", "gradiated.config.toml"),
});

export const buildProviderBlock = (
  apiBaseUrl: string,
  paths: WizardPaths,
): string =>
  [
    MARKERS.start,
    "[model_providers.gradiated]",
    'name = "Gradiated"',
    `base_url = ${JSON.stringify(`${apiBaseUrl}/v1`)}`,
    'wire_api = "responses"',
    `auth = { command = "node", args = ["--eval", ${JSON.stringify(credentialHelper(paths.credentials))}] }`,
    MARKERS.end,
  ].join("\n");

export const buildProfileBlock = (modelId: string): string =>
  [
    MARKERS.start,
    'model_provider = "gradiated"',
    `model = ${JSON.stringify(modelId)}`,
    MARKERS.end,
  ].join("\n");

// TOML assigns every key after a table header to that table, so the provider
// table goes last in config.toml and the profile's root keys go first.
export const mergeProviderConfig = (existing: string, block: string): string =>
  appendManagedBlock(existing, block, MARKERS);

export const mergeProfileConfig = (existing: string, block: string): string =>
  prependManagedBlock(existing, block, MARKERS);

export const writeConfig = async (
  paths: WizardPaths,
  { apiBaseUrl, modelId }: GatewayModel,
): Promise<{ config: boolean; profile: boolean }> => {
  const files = codexFiles(paths);
  const config = (await readTextIfExists(files.config)) ?? "";
  const profile = (await readTextIfExists(files.profile)) ?? "";

  if (profile.length > 0 && !hasManagedBlock(profile, MARKERS)) {
    throw new WizardError(
      `${files.profile} already exists and is not managed by the wizard. Move it or use another profile name.`,
    );
  }

  const configChanged = await writeIfChanged(
    files.config,
    mergeProviderConfig(config, buildProviderBlock(apiBaseUrl, paths)),
    { backup: true },
  );
  const profileChanged = await writeIfChanged(
    files.profile,
    mergeProfileConfig(profile, buildProfileBlock(modelId)),
    { backup: true },
  );

  return { config: configChanged, profile: profileChanged };
};

export const isConfigured = async (paths: WizardPaths): Promise<boolean> => {
  const files = codexFiles(paths);
  const config = await readTextIfExists(files.config);
  const profile = await readTextIfExists(files.profile);

  return (
    (config !== null && hasManagedBlock(config, MARKERS)) ||
    (profile !== null && hasManagedBlock(profile, MARKERS))
  );
};

export const uninstallConfig = async (paths: WizardPaths): Promise<boolean> => {
  const { config } = codexFiles(paths);
  const text = await readTextIfExists(config);
  if (text === null || !hasManagedBlock(text, MARKERS)) return false;

  return writeIfChanged(config, removeManagedBlock(text, MARKERS), {
    backup: true,
  });
};

export const uninstallProfile = async (
  paths: WizardPaths,
): Promise<boolean> => {
  const { profile } = codexFiles(paths);
  const text = await readTextIfExists(profile);
  if (text === null || !hasManagedBlock(text, MARKERS)) return false;

  await backupFile(profile);
  await rm(profile);

  return true;
};

export const codex: AgentIntegration = {
  name: "codex",
  label: "Codex",
  uninstallHint: "provider block and gradiated profile",
  runsWithoutClient: false,
  isConfigured,
  preview: (setup, paths) => {
    const files = codexFiles(paths);

    return [
      {
        title: `Would merge into ${files.config}`,
        body: buildProviderBlock(setup.apiBaseUrl, paths),
      },
      {
        title: `Would write ${files.profile}`,
        body: buildProfileBlock(setup.model.id),
      },
    ];
  },
  install: async (setup, paths) => {
    const files = codexFiles(paths);
    const changed = await writeConfig(paths, {
      apiBaseUrl: setup.apiBaseUrl,
      modelId: setup.model.id,
    });

    return {
      changes: [
        ...(changed.config ? [`Codex provider in ${files.config}`] : []),
        ...(changed.profile ? [`Codex profile in ${files.profile}`] : []),
      ],
      nextStep: {
        action: "run `codex --profile gradiated`",
        notes: ["add `-m <model-id>` for another Gradiated model"],
      },
    };
  },
  uninstall: async (paths) => {
    const files = codexFiles(paths);
    const configRemoved = await uninstallConfig(paths);
    const profileRemoved = await uninstallProfile(paths);

    return {
      removed: [
        ...(configRemoved ? [`Codex provider (${files.config})`] : []),
        ...(profileRemoved ? [`Codex profile (${files.profile})`] : []),
      ],
      backedUp: configRemoved || profileRemoved,
    };
  },
};
