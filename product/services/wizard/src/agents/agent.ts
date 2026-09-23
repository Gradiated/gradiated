import type { Catalog, CatalogModel } from "../catalog.js";
import type { WizardPaths } from "../paths.js";
import type { AgentName } from "./names.js";

export interface AgentSetup {
  apiBaseUrl: string;
  apiKey: string;
  models: Catalog;
  model: CatalogModel;
}

export interface GatewayModel {
  apiBaseUrl: string;
  modelId: string;
}

export interface Preview {
  title: string;
  body: string;
}

export interface NextStep {
  action: string;
  notes: readonly string[];
}

export interface InstallOutcome {
  changes: string[];
  nextStep: NextStep;
}

export interface UninstallOutcome {
  removed: string[];
  backedUp: boolean;
}

export interface AgentIntegration {
  name: AgentName;
  label: string;
  uninstallHint: string;
  runsWithoutClient: boolean;
  isConfigured: (paths: WizardPaths) => Promise<boolean>;
  preview: (setup: AgentSetup, paths: WizardPaths) => Preview[];
  install: (setup: AgentSetup, paths: WizardPaths) => Promise<InstallOutcome>;
  uninstall: (paths: WizardPaths) => Promise<UninstallOutcome>;
}
