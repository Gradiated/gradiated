import { existsSync } from "node:fs";
import { readdir, rm, rmdir } from "node:fs/promises";
import { join } from "node:path";
import { writeIfChanged } from "../../files.js";
import type { WizardPaths } from "../../paths.js";
import type { GatewayModel } from "../agent.js";

const SCRIPT_NAME = "claude-gradiated.js";

const WINDOWS_SHIM = `@echo off\r\nnode "%~dp0${SCRIPT_NAME}" %*\r\n`;

interface WrapperFile {
  path: string;
  content: (script: string) => string;
}

export const wrapperDirectory = (paths: WizardPaths): string =>
  join(paths.home, ".gradiated", "bin");

const scriptPath = (paths: WizardPaths): string =>
  join(wrapperDirectory(paths), SCRIPT_NAME);

export const wrapperCommand = (paths: WizardPaths): string =>
  join(
    wrapperDirectory(paths),
    process.platform === "win32" ? "claude-gradiated.cmd" : "claude-gradiated",
  );

// The command on PATH must be extensionless on POSIX, because a .js suffix
// would leave `claude-gradiated` unresolved. cmd.exe does not run
// extensionless shebang scripts, so on Windows a .cmd shim runs the script.
const wrapperFiles = (paths: WizardPaths): WrapperFile[] =>
  process.platform === "win32"
    ? [
        { path: scriptPath(paths), content: (script) => script },
        { path: wrapperCommand(paths), content: () => WINDOWS_SHIM },
      ]
    : [{ path: wrapperCommand(paths), content: (script) => script }];

// Earlier releases also wrote the .js script on POSIX, so removal covers it on
// every platform.
const ownedFiles = (paths: WizardPaths): string[] => [
  scriptPath(paths),
  wrapperCommand(paths),
];

const wrapperScript = (
  { apiBaseUrl, modelId }: GatewayModel,
  credentialsPath: string,
): string =>
  `#!/usr/bin/env node
// claude-gradiated: run Claude Code with Gradiated as the inference provider.
// Installed by @gradiated/wizard. The API key is read at runtime from the
// credentials file below; this file never contains the key itself.
"use strict";
const { spawn } = require("node:child_process");
const { existsSync, readFileSync } = require("node:fs");

const CREDENTIALS_PATH = ${JSON.stringify(credentialsPath)};
const BASE_URL = ${JSON.stringify(apiBaseUrl)};
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
process.env.ANTHROPIC_MODEL ??= DEFAULT_MODEL;

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

export const isWrapperInstalled = (paths: WizardPaths): boolean =>
  ownedFiles(paths).some((path) => existsSync(path));

export const installWrapper = async (
  paths: WizardPaths,
  model: GatewayModel,
): Promise<boolean> => {
  const script = wrapperScript(model, paths.credentials);
  let changed = false;

  for (const file of wrapperFiles(paths)) {
    const written = await writeIfChanged(file.path, file.content(script), {
      mode: 0o755,
    });
    changed ||= written;
  }

  return changed;
};

export const uninstallWrapper = async (
  paths: WizardPaths,
): Promise<boolean> => {
  if (!isWrapperInstalled(paths)) return false;

  for (const path of ownedFiles(paths)) await rm(path, { force: true });

  const directory = wrapperDirectory(paths);
  if ((await readdir(directory)).length === 0) await rmdir(directory);

  return true;
};
