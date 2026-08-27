import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

const USER_CONFIG_DIR = join(homedir(), ".config", "opencode");
const AUTH_PATH = join(homedir(), ".local", "share", "opencode", "auth.json");

const CONFIG_FILENAMES = [
  "opencode.json",
  "opencode.jsonc",
  "opencode.json5",
] as const;

export interface LocatedConfig {
  path: string;
  raw: string;
  existed: boolean;
}

export const locateConfig = (): LocatedConfig => {
  for (const directory of [USER_CONFIG_DIR, process.cwd()]) {
    for (const filename of CONFIG_FILENAMES) {
      const path = join(directory, filename);
      if (existsSync(path)) {
        return { path, raw: "", existed: true };
      }
    }
  }
  return {
    path: join(USER_CONFIG_DIR, "opencode.json"),
    raw: "",
    existed: false,
  };
};

/** Strip line comments, block comments and trailing commas so JSON.parse succeeds. */
export const parseJsonc = (raw: string): Record<string, unknown> => {
  const withoutBlocks = raw.replace(/\/\*[\s\S]*?\*\//g, "");
  const withoutLines = withoutBlocks
    .split("\n")
    .map((line) => stripLineComment(line))
    .join("\n");
  const withoutTrailing = withoutLines.replace(/,(\s*[}\]])/g, "$1");
  if (withoutTrailing.trim().length === 0) return {};
  return JSON.parse(withoutTrailing) as Record<string, unknown>;
};

const stripLineComment = (line: string): string => {
  let inString = false;
  let escaped = false;
  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (character === "\\") {
      escaped = true;
      continue;
    }
    if (character === '"') {
      inString = !inString;
      continue;
    }
    if (!inString && character === "/" && line[index + 1] === "/") {
      return line.slice(0, index);
    }
  }
  return line;
};

export interface ProviderModelInput {
  id: string;
  name: string;
  contextLength: number | null;
  outputLength: number | null;
}

export const buildProviderBlock = (
  inferenceBaseUrl: string,
  models: readonly ProviderModelInput[],
): Record<string, unknown> => {
  const modelEntries: Record<string, unknown> = {};
  for (const model of models) {
    const entry: Record<string, unknown> = { name: model.name };
    if (model.contextLength !== null && model.outputLength !== null) {
      entry.limit = {
        context: model.contextLength,
        output: model.outputLength,
      };
    }
    modelEntries[model.id] = entry;
  }
  return {
    npm: "@ai-sdk/openai-compatible",
    name: "Gradiated",
    options: {
      baseURL: inferenceBaseUrl,
      apiKey: "{env:GRADIATED_API_KEY}",
    },
    models: modelEntries,
  };
};

export interface MergeResult {
  document: Record<string, unknown>;
  defaultModel: string | null;
}

export const mergeProvider = (
  document: Record<string, unknown>,
  providerBlock: Record<string, unknown>,
): MergeResult => {
  const providers = {
    ...((document.provider as Record<string, unknown> | undefined) ?? {}),
    gradiated: providerBlock,
  };
  const models = (providerBlock.models ?? {}) as Record<string, unknown>;
  const firstModelId = Object.keys(models)[0];

  const existingModel =
    typeof document.model === "string" && document.model.length > 0
      ? document.model
      : null;
  const merged: Record<string, unknown> = {
    // OpenCode validates against this schema; new files must carry it.
    $schema: "https://opencode.ai/config.json",
    ...document,
    ...(existingModel === null && firstModelId !== undefined
      ? { model: `gradiated/${firstModelId}` }
      : {}),
    provider: providers,
  };
  return {
    document: merged,
    defaultModel:
      existingModel ?? (typeof merged.model === "string" ? merged.model : null),
  };
};

export const readConfigDocument = async (
  located: LocatedConfig,
): Promise<Record<string, unknown>> => {
  if (!located.existed) return {};
  const raw = await readFile(located.path, "utf8");
  return parseJsonc(raw);
};

export const writeConfig = async (
  located: LocatedConfig,
  merged: Record<string, unknown>,
): Promise<string> => {
  if (located.existed) {
    const timestamp = new Date()
      .toISOString()
      .replace(/[-:]/g, "")
      .slice(0, 14);
    await copyFile(located.path, `${located.path}.bak.${timestamp}Z`);
  }
  await mkdir(dirname(located.path), { recursive: true });
  const serialized = `${JSON.stringify(merged, null, 2)}\n`;
  await writeFile(located.path, serialized, { mode: 0o600 });
  return located.path;
};

export const mergeAuthCredential = async (
  apiKey: string,
): Promise<string | null> => {
  try {
    let document: Record<string, unknown> = {};
    if (existsSync(AUTH_PATH)) {
      document = JSON.parse(await readFile(AUTH_PATH, "utf8")) as Record<
        string,
        unknown
      >;
    }
    const existing = (document.gradiated ?? {}) as Record<string, unknown>;
    document.gradiated = { ...existing, type: "api", key: apiKey };
    await mkdir(dirname(AUTH_PATH), { recursive: true });
    await writeFile(AUTH_PATH, `${JSON.stringify(document, null, 2)}\n`, {
      mode: 0o600,
    });
    return AUTH_PATH;
  } catch {
    return null;
  }
};

export const authPath = (): string => AUTH_PATH;

/** True when the OpenCode config carries a Gradiated provider block. */
export const isInstalled = async (): Promise<boolean> => {
  const located = locateConfig();
  if (!located.existed) return false;
  const document = await readConfigDocument(located);
  const providers = document.provider as Record<string, unknown> | undefined;
  return providers?.gradiated !== undefined;
};

/** Remove the Gradiated provider and any gradiated/* default model. */
export const uninstallConfig = async (): Promise<string | null> => {
  const located = locateConfig();
  if (!located.existed) return null;
  const document = await readConfigDocument(located);
  const providers = document.provider as Record<string, unknown> | undefined;
  if (providers?.gradiated === undefined) return null;
  const remaining = { ...providers };
  delete remaining.gradiated;
  const merged: Record<string, unknown> = { ...document, provider: remaining };
  if (
    typeof merged.model === "string" &&
    merged.model.startsWith("gradiated/")
  ) {
    delete merged.model;
  }
  await writeConfig(located, merged);
  return located.path;
};

/** Remove the gradiated credential from OpenCode's auth store. */
export const uninstallAuthCredential = async (): Promise<string | null> => {
  if (!existsSync(AUTH_PATH)) return null;
  try {
    const document = JSON.parse(await readFile(AUTH_PATH, "utf8")) as Record<
      string,
      unknown
    >;
    if (document.gradiated === undefined) return null;
    delete document.gradiated;
    await writeFile(AUTH_PATH, `${JSON.stringify(document, null, 2)}\n`, {
      mode: 0o600,
    });
    return AUTH_PATH;
  } catch {
    return null;
  }
};
