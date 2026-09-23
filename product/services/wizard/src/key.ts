import { signIn } from "./account.js";
import type { Credential } from "./arguments.js";
import { fetchCatalog, type Catalog } from "./catalog.js";
import { readStoredKey } from "./credentials.js";
import { requestFailure, WizardError } from "./errors.js";
import { HttpStatusError } from "./http.js";
import type { WizardPaths } from "./paths.js";
import * as ui from "./ui.js";

const CONSOLE_URL = "https://console.gradiated.com";

interface KeyChoice {
  label: string;
  hint?: string;
  value: () => Promise<string>;
}

interface KeyContext {
  apiBaseUrl: string;
  interactive: boolean;
}

interface KeyResolution extends KeyContext {
  offerAccount: boolean;
  paths: WizardPaths;
}

export const resolveKey = async (
  credential: Credential,
  { apiBaseUrl, interactive, offerAccount, paths }: KeyResolution,
): Promise<string> => {
  if (credential.kind === "key") return credential.key;
  if (credential.kind === "account") return signIn(apiBaseUrl, credential.mode);

  const { environmentKey } = credential;
  const stored = await readStoredKey(paths);

  if (!interactive) {
    if (environmentKey !== null) return environmentKey;
    if (stored !== null) return stored;

    throw new WizardError(
      `No Gradiated key found. Pass --key, set GRADIATED_API_KEY, or run the wizard interactively. Create a key at ${CONSOLE_URL}.`,
    );
  }

  const choices: KeyChoice[] = [];
  if (environmentKey !== null) {
    choices.push({
      label: "Use the detected API key",
      hint: "GRADIATED_API_KEY environment variable",
      value: async () => environmentKey,
    });
  }
  if (stored !== null) {
    choices.push({
      label: "Use the saved API key",
      hint: "Saved by the Gradiated wizard",
      value: async () => stored,
    });
  }
  if (offerAccount) {
    choices.push(
      {
        label: "Create a free account",
        hint: "free credit included",
        value: () => signIn(apiBaseUrl, "signup"),
      },
      {
        label: "Log in to an existing account",
        value: () => signIn(apiBaseUrl, "login"),
      },
    );
  }
  choices.push({
    label: "Paste an existing API key",
    value: () =>
      ui.askPassword(`Paste your API key (create one at ${CONSOLE_URL}):`),
  });

  const resolve = await ui.selectOption(
    "How would you like to connect to Gradiated?",
    choices,
  );

  return resolve();
};

const isRejectedKey = (error: unknown): boolean =>
  error instanceof HttpStatusError && error.status === 401;

export const validateKey = async (
  candidateKey: string,
  { apiBaseUrl, interactive }: KeyContext,
): Promise<{ apiKey: string; models: Catalog }> => {
  let apiKey = candidateKey;

  while (true) {
    try {
      const models = await ui.step(
        "Validating the API key and fetching the model catalog",
        () => fetchCatalog(apiBaseUrl, apiKey),
        {
          done: (catalog) =>
            `${catalog.length} model${catalog.length === 1 ? "" : "s"} available`,
          failed: (error) =>
            isRejectedKey(error)
              ? "API key invalid."
              : "Could not fetch the model catalog",
        },
      );
      return { apiKey, models };
    } catch (error) {
      if (!isRejectedKey(error)) {
        throw requestFailure("Could not fetch the model catalog", error);
      }

      if (!interactive) {
        throw new WizardError(
          "API key invalid. Supply a different key or run the wizard interactively to try again.",
          { cause: error },
        );
      }
    }

    apiKey = await ui.askPassword(
      "Paste a different API key (Ctrl+C to cancel):",
    );
  }
};
