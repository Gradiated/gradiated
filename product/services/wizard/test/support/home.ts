import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test as base } from "vitest";
import type { WizardPaths } from "../../src/paths.js";

export const test = base.extend<{
  home: string;
  bin: string;
  paths: WizardPaths;
}>({
  home: async ({}, use) => {
    const root = await mkdtemp(join(tmpdir(), "gradiated-wizard-"));
    const home = join(root, "home");
    await mkdir(home);

    await use(home);

    await rm(root, { recursive: true, force: true });
  },
  bin: async ({ home }, use) => {
    const bin = join(dirname(home), "bin");
    await mkdir(bin);
    await use(bin);
  },
  paths: async ({ home }, use) => {
    await use({
      home,
      credentials: join(home, ".gradiated", "credentials.json"),
    });
  },
});
