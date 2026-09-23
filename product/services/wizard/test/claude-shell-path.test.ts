import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { afterEach, describe, expect, vi } from "vitest";
import {
  addWrapperToPath,
  applyNowCommand,
  currentShell,
  hasWrapperOnPath,
  pathNextStep,
  removeWrapperFromPath,
  type ShellProfile,
} from "../src/agents/claude/shell-path.js";
import { WizardError } from "../src/errors.js";
import { onWindows } from "./support/agent-files.js";
import { test as it } from "./support/home.js";

const ZSHRC: ShellProfile = { shell: "zsh", path: "/home/u/.zshrc", block: "" };
const BASHRC: ShellProfile = {
  shell: "bash",
  path: "/home/u/.bashrc",
  block: "",
};
const FISH_CONFIG: ShellProfile = {
  shell: "fish",
  path: "/home/u/.config/fish/config.fish",
  block: "",
};

const updatedPaths = (profiles: readonly ShellProfile[]): string[] =>
  profiles.map((profile) => profile.path);

afterEach(() => {
  vi.unstubAllEnvs();
});

describe.skipIf(onWindows)("currentShell", () => {
  it.each([
    ["/bin/zsh", "zsh"],
    ["/usr/bin/fish", "fish"],
    ["/bin/bash", "bash"],
    ["/bin/tcsh", "unknown"],
    ["", "unknown"],
  ])("maps SHELL=%j to %s", (shell, expected) => {
    vi.stubEnv("SHELL", shell);

    expect(currentShell()).toBe(expected);
  });
});

describe("applyNowCommand", () => {
  it.each([
    [ZSHRC, "zsh"],
    [BASHRC, "bash"],
    [FISH_CONFIG, "fish"],
  ] as const)("sources the updated $1 profile", (profile, shell) => {
    expect(applyNowCommand([ZSHRC, BASHRC, FISH_CONFIG], shell)).toBe(
      `source ${profile.path}`,
    );
    expect(applyNowCommand([], shell)).toBeNull();
  });

  it("returns Windows session PATH commands that need no profile", () => {
    expect(applyNowCommand([], "powershell")).toBe(
      '$env:Path = "$env:USERPROFILE\\.gradiated\\bin;" + $env:Path',
    );
    expect(applyNowCommand([], "cmd")).toBe(
      'set "PATH=%USERPROFILE%\\.gradiated\\bin;%PATH%"',
    );
  });

  it("returns null for unknown shells so the fallback message is used", () => {
    expect(applyNowCommand([ZSHRC], "unknown")).toBeNull();
  });
});

describe.skipIf(onWindows)("pathNextStep", () => {
  it("prints the source command for the updated profile", () => {
    vi.stubEnv("SHELL", "/bin/zsh");

    expect(pathNextStep([ZSHRC], true)).toEqual({
      action:
        "run `source /home/u/.zshrc` in this terminal, then `claude-gradiated`",
      notes: [],
    });
  });

  it("asks for a new terminal when the shell has no known profile", () => {
    vi.stubEnv("SHELL", "/bin/tcsh");

    expect(pathNextStep([BASHRC], true).action).toContain(
      "open a new terminal",
    );
  });

  it("gives the PATH line to add when no profile has the block", () => {
    vi.stubEnv("SHELL", "/bin/zsh");

    expect(pathNextStep([], true)).toEqual({
      action: "run `claude-gradiated`",
      notes: [],
    });
    expect(pathNextStep([], false).action).toContain(
      'export PATH="$HOME/.gradiated/bin:$PATH"',
    );
  });
});

describe.skipIf(onWindows)("shell profile PATH block", () => {
  it.for(["", "export EDITOR=vim\n", "export EDITOR=vim\n\n", "# only\n"])(
    "restores %j byte-for-byte after add and remove",
    async (content, { paths }) => {
      vi.stubEnv("SHELL", "/bin/zsh");
      const zshrc = join(paths.home, ".zshrc");
      await writeFile(zshrc, content);

      expect(updatedPaths(await addWrapperToPath(paths))).toEqual([zshrc]);
      expect(await hasWrapperOnPath(paths)).toBe(true);
      expect(updatedPaths(await removeWrapperFromPath(paths))).toEqual([zshrc]);

      expect(await readFile(zshrc, "utf8")).toBe(content);
      expect(await hasWrapperOnPath(paths)).toBe(false);
    },
  );

  it("does not add a second block", async ({ paths }) => {
    vi.stubEnv("SHELL", "/bin/bash");
    const bashrc = join(paths.home, ".bashrc");
    await writeFile(bashrc, "alias ll='ls -l'\n");

    await addWrapperToPath(paths);
    const once = await readFile(bashrc, "utf8");

    expect(await addWrapperToPath(paths)).toEqual([]);
    expect(await readFile(bashrc, "utf8")).toBe(once);
  });

  it("sources .bash_profile, which bash login shells read instead of .bashrc", async ({
    paths,
  }) => {
    vi.stubEnv("SHELL", "/bin/bash");
    const bashProfile = join(paths.home, ".bash_profile");
    await writeFile(join(paths.home, ".bashrc"), "");
    await writeFile(bashProfile, "");

    const updated = await addWrapperToPath(paths);

    expect(updated).toHaveLength(2);
    expect(pathNextStep(updated, true).action).toContain(
      `source ${bashProfile}`,
    );
  });

  it("creates config.fish for a fish user without one", async ({ paths }) => {
    vi.stubEnv("SHELL", "/usr/bin/fish");
    const fish = join(paths.home, ".config", "fish", "config.fish");

    expect(updatedPaths(await addWrapperToPath(paths))).toEqual([fish]);
    expect(await readFile(fish, "utf8")).toContain("fish_add_path");
  });

  it("creates no profile for other shells", async ({ paths }) => {
    vi.stubEnv("SHELL", "/bin/zsh");

    expect(await addWrapperToPath(paths)).toEqual([]);
    expect(existsSync(join(paths.home, ".zshrc"))).toBe(false);
    expect(existsSync(join(paths.home, ".config"))).toBe(false);
  });

  it("refuses to edit a block without an end marker", async ({ paths }) => {
    const zshrc = join(paths.home, ".zshrc");
    const broken = "# >>> gradiated >>>\nexport KEEP=1\n";
    await mkdir(paths.home, { recursive: true });
    await writeFile(zshrc, broken);

    await expect(removeWrapperFromPath(paths)).rejects.toThrow(WizardError);
    expect(await readFile(zshrc, "utf8")).toBe(broken);
  });
});
