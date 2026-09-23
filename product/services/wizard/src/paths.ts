import { homedir } from "node:os";
import { join } from "node:path";

export interface WizardPaths {
  home: string;
  credentials: string;
}

export const resolveWizardPaths = (): WizardPaths => {
  const home = homedir();

  return { home, credentials: join(home, ".gradiated", "credentials.json") };
};
