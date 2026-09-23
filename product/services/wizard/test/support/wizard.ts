import { spawnSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { expect } from "vitest";
import { AGENT_NAMES, type AgentName } from "../../src/agents/names.js";
import type { WizardPaths } from "../../src/paths.js";
import { CLAUDE_BIN, onWindows } from "./agent-files.js";
import { API_KEY, ROTATED_KEY } from "./catalog.js";
import { startGradiatedApi } from "./gradiated-api.js";
import { test as homeTest } from "./home.js";
import { runProcess, type ProcessResult } from "./process.js";

const WIZARD_BIN = join(import.meta.dirname, "../../dist/bin.js");

type Environment = Readonly<Record<string, string>>;

export interface RunOptions {
  env?: Environment;
  cwd?: string;
}

export interface InstallRun extends RunOptions {
  agent?: AgentName;
  model?: string;
  key?: string;
  baseUrl?: string;
  dryRun?: boolean;
}

export interface UninstallRun extends RunOptions {
  agent?: AgentName;
  dryRun?: boolean;
}

export interface Wizard {
  run: (
    args: readonly string[],
    options?: RunOptions,
  ) => Promise<ProcessResult>;
  install: (options?: InstallRun) => Promise<ProcessResult>;
  uninstall: (options?: UninstallRun) => Promise<ProcessResult>;
}

const homeEnvironment = (paths: WizardPaths): Environment => ({
  HOME: paths.home,
  USERPROFILE: paths.home,
  GRADIATED_API_KEY: "",
});

const agentArgs = (agent: AgentName | undefined): string[] =>
  agent === undefined ? [] : ["--agent", agent];

const dryRunArgs = (dryRun: boolean | undefined): string[] =>
  dryRun === true ? ["--dry-run"] : [];

interface WizardContext {
  paths: WizardPaths;
  apiBaseUrl: string;
  agentPath: string;
}

const createWizard = ({
  paths,
  apiBaseUrl,
  agentPath,
}: WizardContext): Wizard => {
  const run = (args: readonly string[], options: RunOptions = {}) =>
    runProcess(process.execPath, [WIZARD_BIN, ...args], {
      cwd: options.cwd ?? paths.home,
      env: { ...homeEnvironment(paths), PATH: agentPath, ...options.env },
    });

  return {
    run,
    install: (options = {}) =>
      run(
        [
          "--yes",
          ...agentArgs(options.agent),
          "--key",
          options.key ?? API_KEY,
          ...(options.model === undefined ? [] : ["--model", options.model]),
          ...dryRunArgs(options.dryRun),
          "--api-base-url",
          options.baseUrl ?? apiBaseUrl,
        ],
        options,
      ),
    uninstall: (options = {}) =>
      run(
        [
          "uninstall",
          "--yes",
          ...agentArgs(options.agent),
          ...dryRunArgs(options.dryRun),
        ],
        options,
      ),
  };
};

export const writeCommand = (
  directory: string,
  name: string,
  script: string,
): Promise<void> =>
  writeFile(join(directory, name), `#!/bin/sh\n${script}`, { mode: 0o755 });

const writeFakeAgents = async (directory: string): Promise<void> => {
  for (const agent of AGENT_NAMES) {
    if (onWindows) {
      await writeFile(join(directory, `${agent}.cmd`), "@echo 1.0.0\r\n");
    } else {
      await writeCommand(directory, agent, 'echo "1.0.0"\n');
    }
  }
};

export const test = homeTest
  .extend("api", { scope: "file" }, async ({}, { onCleanup }) => {
    const api = await startGradiatedApi({
      acceptedKeys: [API_KEY, ROTATED_KEY],
    });
    onCleanup(() => api.close());

    return api;
  })
  .extend("unavailableApi", { scope: "file" }, async ({}, { onCleanup }) => {
    const api = await startGradiatedApi({
      acceptedKeys: [API_KEY],
      catalogStatus: 503,
    });
    onCleanup(() => api.close());

    return api;
  })
  .extend("agentPath", async ({ home }) => {
    const directory = join(dirname(home), "agents");
    await mkdir(directory);
    await writeFakeAgents(directory);

    return directory;
  })
  .extend("wizard", async ({ paths, api, agentPath }) =>
    createWizard({ paths, apiBaseUrl: api.baseUrl, agentPath }),
  );

export const expectSuccess = (result: ProcessResult): void => {
  expect({ status: result.status, stderr: result.stderr }).toEqual({
    status: 0,
    stderr: "",
  });
};

export const expectFailure = (result: ProcessResult, message: string): void => {
  expect(result.status).toBe(1);
  expect(result.stdout).toContain(message);
};

export const runClient = (
  paths: WizardPaths,
  command: string,
  args: readonly string[],
  env: Environment = {},
): Promise<ProcessResult> =>
  runProcess(command, args, {
    cwd: paths.home,
    env: { ...homeEnvironment(paths), NO_COLOR: "1", ...env },
    shell: onWindows,
  });

export interface ClaudeWrapperRun {
  args?: readonly string[];
  env?: Environment;
  pathPrepend?: readonly string[];
}

export const runClaudeWrapper = (
  paths: WizardPaths,
  { args = ["--version"], env = {}, pathPrepend = [] }: ClaudeWrapperRun = {},
): Promise<ProcessResult> =>
  runProcess("claude-gradiated", args, {
    env: { ...homeEnvironment(paths), ...env },
    pathPrepend: [join(paths.home, CLAUDE_BIN), ...pathPrepend],
  });

export const hasCommand = (command: string): boolean =>
  spawnSync(command, ["--version"], { stdio: "ignore", shell: onWindows })
    .error === undefined;
