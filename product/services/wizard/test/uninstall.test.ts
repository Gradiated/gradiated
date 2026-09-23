import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { beforeEach, describe, expect, vi } from "vitest";
import { addWrapperToPath } from "../src/agents/claude/shell-path.js";
import { authPath } from "../src/agents/opencode.js";
import type { UninstallOptions } from "../src/arguments.js";
import { runUninstall } from "../src/commands/uninstall.js";
import { readStoredKey, storeKey } from "../src/credentials.js";
import { WizardError } from "../src/errors.js";
import * as ui from "../src/ui.js";
import { API_KEY } from "./support/catalog.js";
import { readJson, seed } from "./support/files.js";
import { test as it } from "./support/home.js";
import { progress } from "./support/ui-stub.js";

vi.mock("../src/ui.js", () => import("./support/ui-stub.js"));

const INTERACTIVE: UninstallOptions = {
  agent: undefined,
  dryRun: false,
  interactive: true,
};

const EVERYTHING: UninstallOptions = { ...INTERACTIVE, interactive: false };

const removedEntries = (): string =>
  vi
    .mocked(ui.outro)
    .mock.calls.map(([message]) => message)
    .join("\n");

const selectEverything = (): void => {
  vi.mocked(ui.selectMany).mockImplementation(async (_message, options) =>
    options.map((option: { value: unknown }) => option.value),
  );
};

beforeEach(() => {
  vi.resetAllMocks();
});

describe("interactive uninstall", () => {
  it("offers only configured targets and removes nothing without a selection", async ({
    paths,
  }) => {
    await storeKey(paths, API_KEY);
    vi.mocked(ui.selectMany).mockResolvedValue([]);

    await runUninstall(INTERACTIVE, paths);

    expect(vi.mocked(ui.selectMany).mock.calls[0]?.[1]).toEqual([
      expect.objectContaining({
        label: "Stored API key",
        hint: paths.credentials,
      }),
    ]);
    expect(ui.confirm).not.toHaveBeenCalled();
    expect(ui.outro).toHaveBeenCalledWith(
      "Nothing removed. No files were changed.",
    );
    expect(await readStoredKey(paths)).toBe(API_KEY);
  });

  it("removes nothing when the confirmation is declined", async ({ paths }) => {
    await storeKey(paths, API_KEY);
    selectEverything();
    vi.mocked(ui.confirm).mockResolvedValue(false);

    await runUninstall(INTERACTIVE, paths);

    expect(ui.outro).toHaveBeenCalledWith(
      "Nothing removed. No files were changed.",
    );
    expect(await readStoredKey(paths)).toBe(API_KEY);
  });

  it("removes the confirmed selection", async ({ paths }) => {
    await storeKey(paths, API_KEY);
    selectEverything();
    vi.mocked(ui.confirm).mockResolvedValue(true);

    await runUninstall(INTERACTIVE, paths);

    expect(vi.mocked(ui.outro).mock.calls[0]?.[0]).toContain(
      `Stored key (${paths.credentials})`,
    );
    expect(await readStoredKey(paths)).toBeNull();
  });
});

describe("partial configuration", () => {
  it("removes an OpenCode credential left without its provider", async ({
    paths,
  }) => {
    await seed(
      authPath(paths),
      JSON.stringify({
        local: { type: "api", key: "local" },
        gradiated: { type: "api", key: API_KEY },
      }),
    );

    await runUninstall({ ...EVERYTHING, agent: "opencode" }, paths);

    expect(removedEntries()).toContain(
      `OpenCode credential (${authPath(paths)})`,
    );
    expect(await readJson(authPath(paths))).toEqual({
      local: { type: "api", key: "local" },
    });
  });

  it("removes a Claude Code PATH entry left without its wrapper", async ({
    paths,
  }) => {
    const zshrc = join(paths.home, ".zshrc");
    await seed(zshrc, "export EDITOR=vim\n");
    await addWrapperToPath(paths);

    await runUninstall({ ...EVERYTHING, agent: "claude" }, paths);

    expect(removedEntries()).toContain(`PATH entry (${zshrc})`);
    expect(await readFile(zshrc, "utf8")).toBe("export EDITOR=vim\n");
  });
});

describe("uninstall failures", () => {
  it("stops and names the target whose removal fails", async ({ paths }) => {
    await seed(
      join(paths.home, ".zshrc"),
      '# >>> gradiated >>>\nexport PATH="$HOME/.gradiated/bin:$PATH"\n',
    );

    await expect(
      runUninstall({ ...EVERYTHING, agent: "claude" }, paths),
    ).rejects.toThrow(WizardError);

    expect(progress.stop).toHaveBeenCalledWith(
      "Could not remove Claude Code",
      1,
    );
    expect(ui.outro).not.toHaveBeenCalled();
  });

  it("removes nothing when any agent configuration cannot be read", async ({
    paths,
  }) => {
    const config = join(paths.home, ".config", "opencode", "opencode.jsonc");
    await storeKey(paths, API_KEY);
    await seed(config, '{ "provider": ');

    await expect(runUninstall(EVERYTHING, paths)).rejects.toThrow(config);

    expect(progress.start).not.toHaveBeenCalled();
    expect(await readStoredKey(paths)).toBe(API_KEY);
  });
});
