import { execFile } from "node:child_process";
import { chmod, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

const PATH_BLOCK_START = "# >>> gradiated >>>";
const PATH_BLOCK_END = "# <<< gradiated <<<";

const WRAPPER_NAME = "claude-gradiated.js";

export const wrapperPath = (): string =>
  join(homedir(), ".gradiated", "bin", WRAPPER_NAME);

/** The command users invoke: extensionless on POSIX, .cmd on Windows. */
export const wrapperCommandPath = (): string =>
  join(
    homedir(),
    ".gradiated",
    "bin",
    process.platform === "win32" ? "claude-gradiated.cmd" : "claude-gradiated",
  );

export const detect = async (): Promise<string | null> => {
  try {
    const output = await new Promise<string>(
      (resolvePromise, rejectPromise) => {
        execFile(
          "claude",
          ["--version"],
          { encoding: "utf8", timeout: 5_000 },
          (error: Error | null, stdout: string) =>
            error ? rejectPromise(error) : resolvePromise(stdout),
        );
      },
    );
    return output.trim().split("\r\n")[0]?.split("\n")[0] ?? null;
  } catch {
    return null;
  }
};

const wrapperScript = (baseUrl: string, modelId: string): string =>
  `#!/usr/bin/env node
// claude-gradiated: run Claude Code with Gradiated as the inference provider.
// Installed by @gradiated/wizard. The API key is read at runtime from
// ~/.gradiated/credentials.json; this file never contains the key itself.
"use strict";
const { spawn } = require("node:child_process");
const { existsSync, readFileSync } = require("node:fs");
const path = require("node:path");

const CREDENTIALS_PATH =
  process.env.GRADIATED_CREDENTIALS_PATH ||
  path.join(require("node:os").homedir(), ".gradiated", "credentials.json");
const BASE_URL = ${JSON.stringify(baseUrl.replace(/\/+$/, ""))};
const DEFAULT_MODEL = ${JSON.stringify(modelId)};

if (!existsSync(CREDENTIALS_PATH)) {
  console.error(
    "No Gradiated key found at " + CREDENTIALS_PATH + ".",
  );
  console.error("Run: npx -y @gradiated/wizard");
  process.exit(1);
}

let apiKey = "";
try {
  apiKey = String(
    JSON.parse(readFileSync(CREDENTIALS_PATH, "utf8")).api_key || "",
  );
} catch {
  apiKey = "";
}
if (apiKey.length === 0) {
  console.error("The Gradiated credential file has no API key.");
  console.error("Run: npx -y @gradiated/wizard");
  process.exit(1);
}

// Respect explicit per-run overrides; set defaults only when absent.
process.env.ANTHROPIC_BASE_URL ??= BASE_URL;
process.env.ANTHROPIC_AUTH_TOKEN ??= apiKey;
if (process.env.ANTHROPIC_MODEL === undefined) {
  process.env.ANTHROPIC_MODEL = DEFAULT_MODEL;
}

const child = spawn("claude", process.argv.slice(2), {
  stdio: "inherit",
  env: process.env,
});
child.on("error", (error) => {
  if (error.code === "ENOENT") {
    console.error("'claude' was not found on PATH.");
    console.error("Install Claude Code first: https://claude.com/claude-code");
    process.exit(1);
  }
  throw error;
});
child.on("exit", (code, signal) => {
  if (signal !== undefined && signal !== null) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
`;

export const isWrapperInstalled = (): boolean =>
  existsSync(wrapperPath()) || existsSync(wrapperCommandPath());

export interface WrapperInstall {
  path: string;
  commandPath: string;
  /** False when both files already had exactly this content. */
  changed: boolean;
}

export const writeWrapper = async (
  baseUrl: string,
  modelId: string,
): Promise<WrapperInstall> => {
  const path = wrapperPath();
  const commandPath = wrapperCommandPath();
  const script = wrapperScript(baseUrl, modelId);
  const commandContent =
    process.platform === "win32"
      ? `@echo off\r\nnode "%~dp0${WRAPPER_NAME}" %*\r\n`
      : script;
  const unchanged =
    existsSync(path) &&
    existsSync(commandPath) &&
    (await readFile(path, "utf8")) === script &&
    (await readFile(commandPath, "utf8")) === commandContent;
  if (unchanged) {
    return { path, commandPath, changed: false };
  }
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, script, { mode: 0o755 });
  await chmod(path, 0o755);
  // The command on PATH must be extensionless on POSIX: `claude-gradiated`
  // resolves to that file, and a .js suffix would leave the command missing.
  // Windows gets a .cmd shim because cmd.exe will not execute extensionless
  // shebang scripts from PATH.
  await writeFile(commandPath, commandContent, { mode: 0o755 });
  await chmod(commandPath, 0o755);
  return { path, commandPath, changed: true };
};

export const uninstallWrapper = async (): Promise<string | null> => {
  if (!existsSync(wrapperPath()) && !existsSync(wrapperCommandPath())) {
    return null;
  }
  await rm(dirname(wrapperPath()), { recursive: true, force: true });
  return wrapperCommandPath();
};

const profilePaths = (): string[] =>
  [join(homedir(), ".zshrc"), join(homedir(), ".bashrc")].filter((path) =>
    existsSync(path),
  );

export const addWrapperToPath = async (): Promise<string[]> => {
  const updated: string[] = [];
  for (const profile of profilePaths()) {
    const raw = await readFile(profile, "utf8");
    if (raw.includes(PATH_BLOCK_START)) continue;
    const block = [
      "",
      PATH_BLOCK_START,
      'export PATH="$HOME/.gradiated/bin:$PATH"',
      PATH_BLOCK_END,
      "",
    ].join("\n");
    await writeFile(profile, `${raw.replace(/\n*$/, "\n")}${block}`);
    updated.push(profile);
  }
  return updated;
};

export const removeWrapperFromPath = async (): Promise<string[]> => {
  const updated: string[] = [];
  for (const profile of profilePaths()) {
    const raw = await readFile(profile, "utf8");
    const start = raw.indexOf(PATH_BLOCK_START);
    if (start === -1) continue;
    const end = raw.indexOf(PATH_BLOCK_END, start);
    if (end === -1) continue;
    const cleaned =
      raw.slice(0, start).replace(/\n+$/, "\n") +
      raw.slice(end + PATH_BLOCK_END.length).replace(/^\n+/, "\n");
    await writeFile(profile, cleaned);
    updated.push(profile);
  }
  return updated;
};

export const hasWrapperOnPath = async (): Promise<boolean> => {
  for (const profile of profilePaths()) {
    const raw = await readFile(profile, "utf8").catch(() => "");
    if (raw.includes(PATH_BLOCK_START)) return true;
  }
  return false;
};
