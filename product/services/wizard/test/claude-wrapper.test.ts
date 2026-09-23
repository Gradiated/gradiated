import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect } from "vitest";
import {
  installWrapper,
  isWrapperInstalled,
  uninstallWrapper,
  wrapperCommand,
  wrapperDirectory,
} from "../src/agents/claude/wrapper.js";
import { CLAUDE_SCRIPT, onWindows } from "./support/agent-files.js";
import {
  API_BASE_URL,
  API_KEY,
  DEFAULT_MODEL,
  SECOND_MODEL,
} from "./support/catalog.js";
import { test as it } from "./support/home.js";

const DEFAULT_TARGET = { apiBaseUrl: API_BASE_URL, modelId: DEFAULT_MODEL };
const SECOND_TARGET = { apiBaseUrl: API_BASE_URL, modelId: SECOND_MODEL };

describe("Claude Code wrapper", () => {
  it("installs an executable script that reads the key at runtime", async ({
    paths,
  }) => {
    expect(await installWrapper(paths, DEFAULT_TARGET)).toBe(true);

    const script = await readFile(join(paths.home, CLAUDE_SCRIPT), "utf8");
    expect(script).toContain(`const BASE_URL = "${API_BASE_URL}"`);
    expect(script).toContain(`const DEFAULT_MODEL = "${DEFAULT_MODEL}"`);
    expect(script).toContain(
      `const CREDENTIALS_PATH = ${JSON.stringify(paths.credentials)}`,
    );
    expect(script).not.toContain(API_KEY);
    expect(isWrapperInstalled(paths)).toBe(true);
    if (!onWindows) {
      expect((await stat(wrapperCommand(paths))).mode & 0o777).toBe(0o755);
    }
  });

  it.skipIf(onWindows)(
    "writes only the extensionless command on POSIX",
    async ({ paths }) => {
      await installWrapper(paths, DEFAULT_TARGET);

      expect(await readdir(wrapperDirectory(paths))).toEqual([
        "claude-gradiated",
      ]);
    },
  );

  it("rewrites the wrapper only when the base URL or model changes", async ({
    paths,
  }) => {
    await installWrapper(paths, DEFAULT_TARGET);

    expect(await installWrapper(paths, DEFAULT_TARGET)).toBe(false);
    expect(await installWrapper(paths, SECOND_TARGET)).toBe(true);
    expect(
      await installWrapper(paths, {
        apiBaseUrl: "https://staging.example.com",
        modelId: SECOND_MODEL,
      }),
    ).toBe(true);
  });

  it("removes its own files and the directory once it is empty", async ({
    paths,
  }) => {
    await installWrapper(paths, DEFAULT_TARGET);

    expect(await uninstallWrapper(paths)).toBe(true);
    expect(existsSync(wrapperDirectory(paths))).toBe(false);
    expect(await uninstallWrapper(paths)).toBe(false);
  });

  it("removes the script that earlier releases also wrote", async ({
    paths,
  }) => {
    const script = join(wrapperDirectory(paths), "claude-gradiated.js");
    await installWrapper(paths, DEFAULT_TARGET);
    await writeFile(script, "#!/usr/bin/env node\n");

    expect(await uninstallWrapper(paths)).toBe(true);
    expect(existsSync(wrapperDirectory(paths))).toBe(false);
  });

  it("keeps unrelated files in ~/.gradiated/bin", async ({ paths }) => {
    const notes = join(wrapperDirectory(paths), "notes.txt");
    await mkdir(wrapperDirectory(paths), { recursive: true });
    await writeFile(notes, "mine\n");
    await installWrapper(paths, DEFAULT_TARGET);

    expect(await uninstallWrapper(paths)).toBe(true);
    expect(await readFile(notes, "utf8")).toBe("mine\n");
    expect(isWrapperInstalled(paths)).toBe(false);
  });
});
