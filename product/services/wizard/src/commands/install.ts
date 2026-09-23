import type {
  AgentIntegration,
  AgentSetup,
  NextStep,
} from "../agents/agent.js";
import { isOnPath } from "../agents/detect.js";
import { selectIntegrations } from "../agents/index.js";
import type { AgentName } from "../agents/names.js";
import type { InstallOptions } from "../arguments.js";
import type { Catalog, CatalogModel } from "../catalog.js";
import { storeKey } from "../credentials.js";
import { WizardError } from "../errors.js";
import { resolveKey, validateKey } from "../key.js";
import type { WizardPaths } from "../paths.js";
import * as ui from "../ui.js";

const pickModel = async (
  models: Catalog,
  requested: string | undefined,
  interactive: boolean,
): Promise<CatalogModel> => {
  if (requested !== undefined) {
    const match = models.find(
      (model) => model.id.toLowerCase() === requested.toLowerCase(),
    );
    if (match === undefined) {
      throw new WizardError(
        `Model "${requested}" is not in the catalog. Available: ${models.map((model) => model.id).join(", ")}`,
      );
    }

    return match;
  }

  if (!interactive || models.length === 1) return models[0];

  return ui.selectOption(
    "Which model should Gradiated use by default?",
    models.map((model) => ({
      value: model,
      label: model.name,
      hint: model.id,
    })),
  );
};

const selectAgents = (agent: AgentName | undefined): AgentIntegration[] => {
  const candidates = selectIntegrations(agent).map((integration) => ({
    integration,
    found: isOnPath(integration.name),
  }));
  ui.agentTable(
    candidates.map(({ integration, found }) => ({
      name: integration.name,
      found,
    })),
  );

  const requested = agent !== undefined;
  const selected = candidates.filter(
    ({ integration, found }) =>
      found || (requested && integration.runsWithoutClient),
  );

  for (const { integration, found } of selected) {
    if (!found) {
      ui.warn(
        `'${integration.name}' was not found on PATH. Configuring ${integration.label} anyway; install it before use.`,
      );
    }
  }

  if (requested && selected.length === 0) {
    throw new WizardError(
      `${agent} is not installed or is not on PATH. Install it, then run this wizard again.`,
    );
  }

  return selected.map(({ integration }) => integration);
};

const configure = async (
  integration: AgentIntegration,
  setup: AgentSetup,
  paths: WizardPaths,
) =>
  ui.step(
    `Configuring ${integration.label}`,
    () => integration.install(setup, paths),
    {
      done: (outcome) =>
        outcome.changes.length > 0
          ? `Configured ${integration.label}`
          : `${integration.label} already has the current Gradiated provider`,
      failed: () => `Could not configure ${integration.label}`,
    },
  );

const formatNextStep = (label: string, step: NextStep): string =>
  [
    `  ${label}: ${step.action}`,
    ...step.notes.map((note) => `    ${note}`),
  ].join("\n");

const listLabels = (integrations: readonly AgentIntegration[]): string =>
  new Intl.ListFormat("en", { type: "conjunction" }).format(
    integrations.map((integration) => integration.label),
  );

export const runInstall = async (
  options: InstallOptions,
  paths: WizardPaths,
): Promise<void> => {
  ui.intro("Gradiated setup");

  const integrations = selectAgents(options.agent);
  if (integrations.length === 0) {
    ui.outro(
      "No supported coding agent was found. Install OpenCode, Codex, or Claude Code, then run this wizard again.",
    );
    return;
  }

  const context = {
    apiBaseUrl: options.apiBaseUrl,
    interactive: options.interactive,
  };
  const candidateKey = await resolveKey(options.credential, {
    ...context,
    offerAccount: !options.dryRun,
    paths,
  });
  const { apiKey, models } = await validateKey(candidateKey, context);
  const model = await pickModel(models, options.model, options.interactive);
  const setup: AgentSetup = {
    apiBaseUrl: options.apiBaseUrl,
    apiKey,
    models,
    model,
  };

  if (options.dryRun) {
    for (const integration of integrations) {
      for (const preview of integration.preview(setup, paths)) {
        ui.note(preview.body, preview.title);
      }
    }
    ui.outro("Dry run complete. No files were changed.");
    return;
  }

  const changes: string[] = [];
  const nextSteps: string[] = [];

  const keyChanged = await ui.step(
    "Storing the API key",
    () => storeKey(paths, apiKey),
    {
      done: () => `Stored the key in ${paths.credentials} (0600)`,
      failed: () => "Could not store the API key",
    },
  );
  if (keyChanged) changes.push(`API key in ${paths.credentials}`);

  for (const integration of integrations) {
    const outcome = await configure(integration, setup, paths);
    changes.push(...outcome.changes);
    nextSteps.push(formatNextStep(integration.label, outcome.nextStep));
  }

  const agentNames = listLabels(integrations);
  const nextStepsText = `Next steps:\n${nextSteps.join("\n\n")}`;

  ui.outro(
    changes.length === 0
      ? `Gradiated was already configured for ${agentNames}. No files were changed.\n\n${nextStepsText}\n\nDocs: https://gradiated.com/docs`
      : `Ready. Gradiated is configured for ${agentNames}.\n\nChanged:\n${ui.bulletList(changes)}\n\n${nextStepsText}\n\nAffordable inference for open-weight models — https://gradiated.com/docs`,
  );
};
