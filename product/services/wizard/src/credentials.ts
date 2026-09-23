import { rm } from "node:fs/promises";
import { formatJson, readJsonObject, writeIfChanged } from "./files.js";
import type { WizardPaths } from "./paths.js";

export const readStoredKey = async (
  paths: WizardPaths,
): Promise<string | null> => {
  const credentials = await readJsonObject(paths.credentials);
  const apiKey = credentials?.api_key;

  return typeof apiKey === "string" && apiKey.length > 0 ? apiKey : null;
};

export const storeKey = (
  paths: WizardPaths,
  apiKey: string,
): Promise<boolean> =>
  writeIfChanged(paths.credentials, formatJson({ api_key: apiKey }), {
    mode: 0o600,
  });

export const removeStoredKey = async (paths: WizardPaths): Promise<boolean> => {
  if ((await readStoredKey(paths)) === null) return false;

  await rm(paths.credentials, { force: true });

  return true;
};
