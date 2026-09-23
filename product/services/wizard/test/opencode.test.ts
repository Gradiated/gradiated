import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect } from "vitest";
import {
  authPath,
  buildProvider,
  isConfigured,
  mergeAuthCredential,
  mergeProvider,
  removeProvider,
  uninstallAuthCredential,
  uninstallConfig,
  writeProvider,
} from "../src/agents/opencode.js";
import { WizardError } from "../src/errors.js";
import type { WizardPaths } from "../src/paths.js";
import {
  API_BASE_URL,
  DEFAULT_MODEL,
  GEMMA,
  GLM,
  SECOND_MODEL,
} from "./support/catalog.js";
import { readJson, seed } from "./support/files.js";
import { test as it } from "./support/home.js";

const PROVIDER = buildProvider(API_BASE_URL, [GLM, { ...GEMMA, limit: null }]);

const configPath = (paths: WizardPaths, filename = "opencode.json"): string =>
  join(paths.home, ".config", "opencode", filename);

describe("OpenCode provider", () => {
  it("lists every catalog model and a limit only when both counts are known", () => {
    expect(PROVIDER.models).toEqual({
      [DEFAULT_MODEL]: { name: GLM.name, limit: GLM.limit },
      [SECOND_MODEL]: { name: GEMMA.name },
    });
  });

  it("keeps other providers", () => {
    const local = { npm: "@ai-sdk/openai-compatible", name: "Local" };

    const merged = mergeProvider(
      { provider: { local } },
      PROVIDER,
      SECOND_MODEL,
    );

    expect(merged.provider).toEqual({ local, gradiated: PROVIDER });
  });

  it.each([
    [undefined, `gradiated/${SECOND_MODEL}`],
    ["", `gradiated/${SECOND_MODEL}`],
    [`gradiated/${DEFAULT_MODEL}`, `gradiated/${SECOND_MODEL}`],
    ["anthropic/claude-sonnet-4-5", "anthropic/claude-sonnet-4-5"],
  ])("turns the default model %j into %j", (model, expected) => {
    const document = model === undefined ? {} : { model };

    expect(mergeProvider(document, PROVIDER, SECOND_MODEL).model).toBe(
      expected,
    );
  });

  it("removes only the Gradiated provider and a Gradiated default", () => {
    const local = { name: "Local" };
    const installed = mergeProvider(
      { theme: "dark", provider: { local } },
      PROVIDER,
      DEFAULT_MODEL,
    );

    expect(removeProvider(installed)).toEqual({
      $schema: "https://opencode.ai/config.json",
      theme: "dark",
      provider: { local },
    });
    expect(
      removeProvider({ model: "local/model", provider: { gradiated: {} } }),
    ).toEqual({ model: "local/model", provider: {} });
  });
});

describe("OpenCode install and uninstall", () => {
  it("reads opencode.jsonc with comments and keeps string contents", async ({
    paths,
  }) => {
    const path = configPath(paths, "opencode.jsonc");
    await seed(
      path,
      `{
  // Watch sources.
  "watcher": { "ignore": ["src/**/*.ts", "dist//x"] },
  "model": "anthropic/claude-sonnet-4-5", /* keep */
}
`,
    );

    const written = await writeProvider(paths, PROVIDER, DEFAULT_MODEL);

    expect(written).toEqual({
      path,
      changed: true,
      defaultModel: "anthropic/claude-sonnet-4-5",
    });
    expect(await readJson(path)).toMatchObject({
      watcher: { ignore: ["src/**/*.ts", "dist//x"] },
      model: "anthropic/claude-sonnet-4-5",
      provider: { gradiated: PROVIDER },
    });
  });

  it("rejects a malformed config and names it", async ({ paths }) => {
    const path = configPath(paths);
    await seed(path, '{ "provider": ');

    await expect(writeProvider(paths, PROVIDER, DEFAULT_MODEL)).rejects.toThrow(
      new WizardError(`${path} is not valid JSONC. Fix or move it.`),
    );
    expect(await readFile(path, "utf8")).toBe('{ "provider": ');
  });

  it("rejects a malformed auth.json and names it", async ({ paths }) => {
    await seed(authPath(paths), "not json");

    await expect(mergeAuthCredential(paths, "grad_fixture")).rejects.toThrow(
      authPath(paths),
    );
    await expect(uninstallAuthCredential(paths)).rejects.toThrow(
      authPath(paths),
    );
  });

  it("stores the credential beside other providers and reports changes", async ({
    paths,
  }) => {
    await seed(authPath(paths), '{"local":{"type":"api","key":"local"}}\n');

    expect(await mergeAuthCredential(paths, "grad_first")).toBe(true);
    expect(await mergeAuthCredential(paths, "grad_first")).toBe(false);
    expect(await mergeAuthCredential(paths, "grad_second")).toBe(true);
    expect(await readJson(authPath(paths))).toEqual({
      local: { type: "api", key: "local" },
      gradiated: { type: "api", key: "grad_second" },
    });

    expect(await uninstallAuthCredential(paths)).toBe(authPath(paths));
    expect(await readJson(authPath(paths))).toEqual({
      local: { type: "api", key: "local" },
    });
  });

  it("uninstalls the provider it installed", async ({ paths }) => {
    await writeProvider(paths, PROVIDER, DEFAULT_MODEL);
    expect(await isConfigured(paths)).toBe(true);

    expect(await uninstallConfig(paths)).toBe(configPath(paths));
    expect(await isConfigured(paths)).toBe(false);
    expect(await uninstallConfig(paths)).toBeNull();
    expect(await readJson(configPath(paths))).toEqual({
      $schema: "https://opencode.ai/config.json",
      provider: {},
    });
  });
});
