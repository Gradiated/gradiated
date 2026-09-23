import {
  chmod,
  lstat,
  readdir,
  readFile,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import { join } from "node:path";
import { describe, expect } from "vitest";
import { WizardError } from "../src/errors.js";
import {
  appendManagedBlock,
  prependManagedBlock,
  removeManagedBlock,
  writeIfChanged,
} from "../src/files.js";
import { onWindows } from "./support/agent-files.js";
import { listBackups } from "./support/files.js";
import { test as it } from "./support/home.js";

const MARKERS = { start: "# >>> test >>>", end: "# <<< test <<<" };
const BLOCK = `${MARKERS.start}\nmanaged = true\n${MARKERS.end}`;
const NEWER_BLOCK = `${MARKERS.start}\nmanaged = "newer"\n${MARKERS.end}`;

const TEXTS = [
  "",
  "\n",
  "a = 1\n",
  "a = 1\n\n",
  "\nleading = true\n",
  "[table]\nkey = 1\n\n[other]\nkey = 2\n",
];

const EDITS = [
  ["append", appendManagedBlock],
  ["prepend", prependManagedBlock],
] as const;

describe("managed blocks", () => {
  describe.each(EDITS)("%s", (_name, add) => {
    it.each(TEXTS)("restores %j byte-for-byte after removal", (text) => {
      expect(removeManagedBlock(add(text, BLOCK, MARKERS), MARKERS)).toBe(text);
    });

    it.each(TEXTS)("replaces rather than duplicates in %j", (text) => {
      const once = add(text, BLOCK, MARKERS);

      expect(add(once, BLOCK, MARKERS)).toBe(once);
      expect(add(once, NEWER_BLOCK, MARKERS)).toBe(
        add(text, NEWER_BLOCK, MARKERS),
      );
    });
  });

  it("appends after the existing text and prepends before it", () => {
    expect(appendManagedBlock("a = 1\n", BLOCK, MARKERS)).toBe(
      `a = 1\n\n${BLOCK}\n`,
    );
    expect(prependManagedBlock("a = 1\n", BLOCK, MARKERS)).toBe(
      `${BLOCK}\n\na = 1\n`,
    );
  });

  it("leaves text without a block unchanged", () => {
    expect(removeManagedBlock("a = 1", MARKERS)).toBe("a = 1");
  });

  it("refuses to guess where a block without an end marker stops", () => {
    const broken = `a = 1\n\n${MARKERS.start}\nmanaged = true\nuser = 1\n`;

    expect(() => removeManagedBlock(broken, MARKERS)).toThrow(WizardError);
    expect(() => appendManagedBlock(broken, BLOCK, MARKERS)).toThrow(
      MARKERS.end,
    );
  });
});

describe("writeIfChanged", () => {
  it("creates missing parent directories", async ({ home }) => {
    const path = join(home, "nested", "dir", "file.txt");

    expect(await writeIfChanged(path, "content\n", { backup: true })).toBe(
      true,
    );
    expect(await readFile(path, "utf8")).toBe("content\n");
    expect(await listBackups(join(home, "nested", "dir"))).toEqual([]);
  });

  it("backs up only when the content changes", async ({ home }) => {
    const path = join(home, "config.txt");
    await writeFile(path, "original\n");

    expect(await writeIfChanged(path, "original\n", { backup: true })).toBe(
      false,
    );
    expect(await listBackups(home)).toEqual([]);

    expect(await writeIfChanged(path, "updated\n", { backup: true })).toBe(
      true,
    );
    const [backup] = await listBackups(home);
    expect(backup).toMatch(/^config\.txt\.bak\.\d{8}T\d{9}Z$/);
    expect(await readFile(join(home, backup!), "utf8")).toBe("original\n");
  });

  it("leaves only the target file behind", async ({ home }) => {
    const path = join(home, "config.txt");
    await writeFile(path, "original\n");

    await writeIfChanged(path, "updated\n");

    expect(await readdir(home)).toEqual(["config.txt"]);
  });

  describe.skipIf(onWindows)("permissions and links", () => {
    it("keeps the mode of a file it replaces", async ({ home }) => {
      const path = join(home, ".zshrc");
      await writeFile(path, "export EDITOR=vim\n");
      await chmod(path, 0o640);

      await writeIfChanged(path, "export EDITOR=nano\n");

      expect((await stat(path)).mode & 0o777).toBe(0o640);
    });

    it("applies the requested mode to an existing file", async ({ home }) => {
      const path = join(home, "secret.json");
      await writeFile(path, "{}\n");
      await chmod(path, 0o644);

      await writeIfChanged(path, '{"key":1}\n', { mode: 0o600 });

      expect((await stat(path)).mode & 0o777).toBe(0o600);
    });

    it("writes through a symlink and keeps the link", async ({ home }) => {
      const target = join(home, "dotfiles-zshrc");
      const link = join(home, ".zshrc");
      await writeFile(target, "export EDITOR=vim\n");
      await symlink(target, link);

      await writeIfChanged(link, "export EDITOR=nano\n");

      expect((await lstat(link)).isSymbolicLink()).toBe(true);
      expect(await readFile(target, "utf8")).toBe("export EDITOR=nano\n");
    });
  });
});
