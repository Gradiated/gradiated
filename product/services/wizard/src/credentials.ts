import { chmod, mkdir, readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

const CREDENTIALS_PATH = join(homedir(), ".gradiated", "credentials.json");

export interface StoredCredentials {
  api_key: string;
}

export function credentialsPath(): string {
  return process.env.GRADIATED_CREDENTIALS_PATH ?? CREDENTIALS_PATH;
}

export async function readStoredKey(): Promise<string | null> {
  try {
    const raw = await readFile(credentialsPath(), "utf8");
    const parsed = JSON.parse(raw) as Partial<StoredCredentials>;
    return typeof parsed.api_key === "string" && parsed.api_key.length > 0
      ? parsed.api_key
      : null;
  } catch {
    return null;
  }
}

export async function storeKey(apiKey: string): Promise<string> {
  const path = credentialsPath();
  await mkdir(path.slice(0, path.lastIndexOf("/")), { recursive: true });
  const credentials: StoredCredentials = { api_key: apiKey };
  await writeFile(path, `${JSON.stringify(credentials, null, 2)}\n`, {
    mode: 0o600,
  });
  await chmod(path, 0o600);
  return path;
}
