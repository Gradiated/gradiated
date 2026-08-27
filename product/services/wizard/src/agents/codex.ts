import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

const CONFIG_PATH = join(homedir(), ".codex", "config.toml");
const PROFILE_PATH = join(homedir(), ".codex", "gradiated.config.toml");
const BLOCK_START = "# --- Gradiated (added by @gradiated/wizard) ---";
const BLOCK_END = "# --- End Gradiated ---";

const CREDENTIAL_HELPER = [
  'const fs=require("node:fs")',
  'const os=require("node:os")',
  'const path=require("node:path")',
  'const file=process.env.GRADIATED_CREDENTIALS_PATH||path.join(os.homedir(),".gradiated","credentials.json")',
  'process.stdout.write(JSON.parse(fs.readFileSync(file,"utf8")).api_key)',
].join(";");

export const configPath = (): string => CONFIG_PATH;
export const profilePath = (): string => PROFILE_PATH;

/**
 * Add a custom Responses provider without changing the user's normal Codex
 * provider. The auth command reads the wizard's owner-only credential file.
 */
export const buildProviderBlock = (baseUrl: string): string =>
  [
    BLOCK_START,
    "[model_providers.gradiated]",
    'name = "Gradiated"',
    `base_url = ${JSON.stringify(`${baseUrl.replace(/\/$/, "")}/v1`)}`,
    'wire_api = "responses"',
    `auth = { command = "node", args = ["--eval", ${JSON.stringify(CREDENTIAL_HELPER)}] }`,
    BLOCK_END,
  ].join("\n");

export const buildProfileBlock = (modelId: string): string =>
  [
    BLOCK_START,
    'model_provider = "gradiated"',
    `model = ${JSON.stringify(modelId)}`,
    BLOCK_END,
  ].join("\n");

const withoutManagedBlock = (existing: string): string => {
  const start = existing.indexOf(BLOCK_START);
  if (start === -1) return existing.trim();
  const end = existing.indexOf(BLOCK_END, start);
  const after = end === -1 ? existing.length : end + BLOCK_END.length;
  return `${existing.slice(0, start)}${existing.slice(after)}`.trim();
};

/** Keep the provider block last so later root keys do not enter its table. */
export const mergeProviderConfig = (
  existing: string,
  block: string,
): string => {
  const preserved = withoutManagedBlock(existing);
  return `${preserved.length > 0 ? `${preserved}\n\n` : ""}${block}\n`;
};

/** Keep root-level profile keys before any user-defined TOML tables. */
export const mergeProfileConfig = (existing: string, block: string): string => {
  const preserved = withoutManagedBlock(existing);
  return `${block}${preserved.length > 0 ? `\n\n${preserved}` : ""}\n`;
};

const backupFile = async (path: string): Promise<string> => {
  const timestamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 14);
  const backup = `${path}.bak.${timestamp}Z`;
  await copyFile(path, backup);
  return backup;
};

export const writeConfig = async (
  baseUrl: string,
  modelId: string,
): Promise<{
  configPath: string;
  profilePath: string;
  backups: string[];
}> => {
  const configRaw = existsSync(CONFIG_PATH)
    ? await readFile(CONFIG_PATH, "utf8")
    : "";
  const profileRaw = existsSync(PROFILE_PATH)
    ? await readFile(PROFILE_PATH, "utf8")
    : "";

  if (profileRaw.length > 0 && !profileRaw.includes(BLOCK_START)) {
    throw new Error(
      `${PROFILE_PATH} already exists and is not managed by the wizard. Move it or use another profile name.`,
    );
  }

  const backups: string[] = [];
  if (existsSync(CONFIG_PATH)) backups.push(await backupFile(CONFIG_PATH));
  if (existsSync(PROFILE_PATH)) backups.push(await backupFile(PROFILE_PATH));

  await mkdir(dirname(CONFIG_PATH), { recursive: true });
  await writeFile(
    CONFIG_PATH,
    mergeProviderConfig(configRaw, buildProviderBlock(baseUrl)),
    { mode: 0o600 },
  );
  await writeFile(
    PROFILE_PATH,
    mergeProfileConfig(profileRaw, buildProfileBlock(modelId)),
    { mode: 0o600 },
  );
  return { configPath: CONFIG_PATH, profilePath: PROFILE_PATH, backups };
};
