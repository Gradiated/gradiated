import type { AgentIntegration, UninstallOutcome } from "../agents/agent.js";
import { agentLabel, selectIntegrations } from "../agents/index.js";
import type { AgentName } from "../agents/names.js";
import type { UninstallOptions } from "../arguments.js";
import { readStoredKey, removeStoredKey } from "../credentials.js";
import type { WizardPaths } from "../paths.js";
import * as ui from "../ui.js";

interface UninstallTarget {
  label: string;
  hint: string;
  isConfigured: () => Promise<boolean>;
  remove: () => Promise<UninstallOutcome>;
}

const storedKey = (paths: WizardPaths): UninstallTarget => ({
  label: "Stored API key",
  hint: paths.credentials,
  isConfigured: async () => (await readStoredKey(paths)) !== null,
  remove: async () => ({
    removed: (await removeStoredKey(paths))
      ? [`Stored key (${paths.credentials})`]
      : [],
    backedUp: false,
  }),
});

const agentTarget = (
  integration: AgentIntegration,
  paths: WizardPaths,
): UninstallTarget => ({
  label: integration.label,
  hint: integration.uninstallHint,
  isConfigured: () => integration.isConfigured(paths),
  remove: () => integration.uninstall(paths),
});

const candidateTargets = (
  agent: AgentName | undefined,
  paths: WizardPaths,
): UninstallTarget[] => {
  const agents = selectIntegrations(agent).map((integration) =>
    agentTarget(integration, paths),
  );

  return agent === undefined ? [...agents, storedKey(paths)] : agents;
};

const configuredTargets = async (
  targets: readonly UninstallTarget[],
): Promise<UninstallTarget[]> => {
  const configured: UninstallTarget[] = [];

  for (const target of targets) {
    if (await target.isConfigured()) configured.push(target);
  }

  return configured;
};

const chooseTargets = async (
  targets: UninstallTarget[],
): Promise<UninstallTarget[]> => {
  const selection = await ui.selectMany(
    "Which agents should Gradiated be removed from?",
    targets.map((target) => ({
      value: target,
      label: target.label,
      hint: target.hint,
    })),
  );
  if (selection.length === 0) return [];

  const proceed = await ui.confirm(
    "Remove the selected configuration? Backups (.bak) are kept.",
  );

  return proceed ? selection : [];
};

export const runUninstall = async (
  options: UninstallOptions,
  paths: WizardPaths,
): Promise<void> => {
  ui.intro("Gradiated uninstall");

  const configured = await configuredTargets(
    candidateTargets(options.agent, paths),
  );
  if (configured.length === 0) {
    ui.outro(
      options.agent === undefined
        ? "No Gradiated configuration was found. Nothing to remove."
        : `Gradiated is not configured for ${agentLabel(options.agent)}. Nothing to remove.`,
    );
    return;
  }

  if (options.dryRun) {
    ui.note(
      configured.map((target) => target.label).join("\n"),
      "Would remove",
    );
    ui.outro("Dry run complete. No files were changed.");
    return;
  }

  const selection = options.interactive
    ? await chooseTargets(configured)
    : configured;
  if (selection.length === 0) {
    ui.outro("Nothing removed. No files were changed.");
    return;
  }

  const removed: string[] = [];
  let backedUp = false;

  for (const target of selection) {
    const outcome = await ui.step(
      `Removing ${target.label}`,
      () => target.remove(),
      {
        done: (result) =>
          result.removed.length > 0
            ? `Removed ${target.label}`
            : "Nothing found",
        failed: () => `Could not remove ${target.label}`,
      },
    );
    removed.push(...outcome.removed);
    backedUp ||= outcome.backedUp;
  }

  if (removed.length === 0) {
    ui.outro("Nothing to remove for the selected agents.");
    return;
  }

  const backupNote = backedUp
    ? "Backups (.bak.<timestamp>) were kept next to each modified config file. "
    : "";
  ui.outro(
    `Removed Gradiated configuration from:\n${ui.bulletList(removed)}\n\n` +
      `${backupNote}Your other providers and settings are untouched.`,
  );
};
