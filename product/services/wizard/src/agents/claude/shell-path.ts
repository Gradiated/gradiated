import { join } from "node:path";
import {
  appendManagedBlock,
  hasManagedBlock,
  readTextIfExists,
  removeManagedBlock,
  writeIfChanged,
  type BlockMarkers,
} from "../../files.js";
import type { WizardPaths } from "../../paths.js";
import type { NextStep } from "../agent.js";

const MARKERS: BlockMarkers = {
  start: "# >>> gradiated >>>",
  end: "# <<< gradiated <<<",
};

const POSIX_DIRECTORY = "$HOME/.gradiated/bin";
const POSIX_PATH_LINE = `export PATH="${POSIX_DIRECTORY}:$PATH"`;
const WINDOWS_SUBDIRECTORY = ".gradiated\\bin";
const WINDOWS_DIRECTORY = `%USERPROFILE%\\${WINDOWS_SUBDIRECTORY}`;

const POSIX_BLOCK = [MARKERS.start, POSIX_PATH_LINE, MARKERS.end].join("\n");

const FISH_BLOCK = [
  MARKERS.start,
  `fish_add_path -g "${POSIX_DIRECTORY}"`,
  MARKERS.end,
].join("\n");

export type ShellName =
  "zsh" | "bash" | "fish" | "powershell" | "cmd" | "unknown";

export interface ShellProfile {
  shell: "zsh" | "bash" | "fish";
  path: string;
  block: string;
}

export const currentShell = (): ShellName => {
  if (process.platform === "win32") {
    // PSModulePath is only set in PowerShell sessions.
    return process.env.PSModulePath !== undefined ? "powershell" : "cmd";
  }

  const name = (process.env.SHELL ?? "").split("/").pop() ?? "";
  if (name === "zsh" || name === "bash" || name === "fish") return name;

  return "unknown";
};

// Bash login shells read .bash_profile and ignore .bashrc, so it comes first
// and is the one to source when both were updated.
const profiles = (paths: WizardPaths): ShellProfile[] => [
  { shell: "zsh", path: join(paths.home, ".zshrc"), block: POSIX_BLOCK },
  {
    shell: "bash",
    path: join(paths.home, ".bash_profile"),
    block: POSIX_BLOCK,
  },
  { shell: "bash", path: join(paths.home, ".bashrc"), block: POSIX_BLOCK },
  {
    shell: "fish",
    path: join(paths.home, ".config", "fish", "config.fish"),
    block: FISH_BLOCK,
  },
];

export const addWrapperToPath = async (
  paths: WizardPaths,
): Promise<ShellProfile[]> => {
  const updated: ShellProfile[] = [];

  for (const profile of profiles(paths)) {
    const existing = await readTextIfExists(profile.path);
    // A fish user without a config file still needs a block that the
    // printed `source` command can load.
    const createsFishConfig =
      existing === null &&
      profile.shell === "fish" &&
      currentShell() === "fish";
    if (existing === null && !createsFishConfig) continue;

    const text = appendManagedBlock(existing ?? "", profile.block, MARKERS);
    if (await writeIfChanged(profile.path, text)) updated.push(profile);
  }

  return updated;
};

export const removeWrapperFromPath = async (
  paths: WizardPaths,
): Promise<ShellProfile[]> => {
  const updated: ShellProfile[] = [];

  for (const profile of profiles(paths)) {
    const existing = await readTextIfExists(profile.path);
    if (existing === null || !hasManagedBlock(existing, MARKERS)) continue;

    await writeIfChanged(profile.path, removeManagedBlock(existing, MARKERS));
    updated.push(profile);
  }

  return updated;
};

export const hasWrapperOnPath = async (
  paths: WizardPaths,
): Promise<boolean> => {
  for (const profile of profiles(paths)) {
    const existing = await readTextIfExists(profile.path);
    if (existing !== null && hasManagedBlock(existing, MARKERS)) return true;
  }

  return false;
};

export const applyNowCommand = (
  updatedProfiles: readonly ShellProfile[],
  shell: ShellName,
): string | null => {
  if (shell === "powershell") {
    return `$env:Path = "$env:USERPROFILE\\${WINDOWS_SUBDIRECTORY};" + $env:Path`;
  }
  if (shell === "cmd") return `set "PATH=${WINDOWS_DIRECTORY};%PATH%"`;

  const profile = updatedProfiles.find((updated) => updated.shell === shell);

  return profile === undefined ? null : `source ${profile.path}`;
};

export const pathNextStep = (
  updatedProfiles: readonly ShellProfile[],
  onPath: boolean,
): NextStep => {
  const command = applyNowCommand(updatedProfiles, currentShell());

  if (command !== null) {
    // Windows PATH is not persisted, so the session command needs a manual
    // persistent entry beside it.
    return {
      action: `run \`${command}\` in this terminal, then \`claude-gradiated\``,
      notes:
        process.platform === "win32"
          ? [`for new terminals, add ${WINDOWS_DIRECTORY} to your PATH`]
          : [],
    };
  }

  if (updatedProfiles.length > 0) {
    return {
      action:
        "open a new terminal so the updated PATH applies, then run `claude-gradiated`",
      notes: [],
    };
  }

  return {
    action: onPath
      ? "run `claude-gradiated`"
      : `add \`${POSIX_PATH_LINE}\` to your shell profile, then run \`claude-gradiated\``,
    notes: [],
  };
};
