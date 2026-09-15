import { fetchCatalog, type CatalogModel } from "./catalog.js";
import { HttpError } from "./http.js";
import { CONSOLE_URL } from "./arguments.js";
import { resolveAccount } from "./account.js";
import { readStoredKey } from "./credentials.js";
import * as ui from "./ui.js";

type KeyChoice = "environment" | "stored" | "signup" | "login" | "paste";

export const resolveKey = async (
  options: { yes: boolean; key: string | undefined; mode: string },
  targets: { apiBaseUrl: string; inferenceBaseUrl: string },
): Promise<string> => {
  // Explicit instructions take precedence over discovered credentials.
  if (options.key !== undefined) return options.key;
  if (options.mode === "login" || options.mode === "signup") {
    return (await resolveAccount(targets, options.mode)).apiKey;
  }

  const environmentKey = process.env.GRADIATED_API_KEY || null;
  const stored = await readStoredKey();
  if (options.yes) {
    if (environmentKey !== null) return environmentKey;
    if (stored !== null) return stored;
    ui.fail(
      `No Gradiated key found. Create one at ${CONSOLE_URL} or run without --yes.`,
    );
  }

  const choices: { value: KeyChoice; label: string; hint?: string }[] = [];
  if (environmentKey !== null) {
    choices.push({
      value: "environment",
      label: "Use the detected API key",
      hint: "GRADIATED_API_KEY environment variable",
    });
  }
  if (stored !== null) {
    choices.push({
      value: "stored",
      label: "Use the saved API key",
      hint: "Saved by the Gradiated wizard",
    });
  }
  choices.push(
    {
      value: "signup",
      label: "Create a free account",
      hint: "free credit included",
    },
    { value: "login", label: "Log in to an existing account" },
    { value: "paste", label: "Paste an existing API key" },
  );
  const choice = await ui.selectOption<KeyChoice>(
    "How would you like to connect to Gradiated?",
    choices,
  );
  if (choice === "environment" && environmentKey !== null)
    return environmentKey;
  if (choice === "stored" && stored !== null) return stored;
  if (choice === "paste")
    return ui.askPassword(`Paste your API key (create one at ${CONSOLE_URL}):`);
  if (choice === "signup" || choice === "login") {
    return (await resolveAccount(targets, choice)).apiKey;
  }
  throw new Error(
    "The selected API key is no longer available. Run the wizard again.",
  );
};

/** Validate before storing anything; interactive users can replace a rejected key. */
export const validateKey = async (
  candidateKey: string,
  inferenceBaseUrl: string,
  interactive: boolean,
): Promise<{ apiKey: string; models: CatalogModel[] }> => {
  let apiKey = candidateKey;
  while (true) {
    const progress = ui.spinner();
    progress.start("Validating the API key and fetching the model catalog");
    try {
      const models = await fetchCatalog(inferenceBaseUrl, apiKey);
      progress.stop(
        `${models.length} model${models.length === 1 ? "" : "s"} available`,
      );
      return { apiKey, models };
    } catch (error) {
      if (error instanceof HttpError && error.status === 401) {
        progress.stop("API key invalid.", 1);
        if (!interactive) {
          throw new Error(
            "API key invalid. Supply a different key or run the wizard interactively to try again.",
          );
        }
      } else {
        progress.stop("Could not fetch the model catalog", 1);
        if (error instanceof HttpError) {
          throw new Error(
            `Could not fetch the model catalog (${error.status || "network"}): ${error.message}`,
          );
        }
        throw error;
      }
    }
    apiKey = await ui.askPassword(
      "Paste a different API key (Ctrl+C to cancel):",
    );
  }
};
