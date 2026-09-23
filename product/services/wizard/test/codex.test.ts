import { existsSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { describe, expect } from "vitest";
import {
  buildProfileBlock,
  buildProviderBlock,
  codexFiles,
  isConfigured,
  mergeProfileConfig,
  mergeProviderConfig,
  uninstallConfig,
  uninstallProfile,
  writeConfig,
} from "../src/agents/codex.js";
import { WizardError } from "../src/errors.js";
import type { WizardPaths } from "../src/paths.js";
import { API_BASE_URL, DEFAULT_MODEL } from "./support/catalog.js";
import { seed } from "./support/files.js";
import { test as it } from "./support/home.js";

const USER_CONFIG =
  'model = "gpt-5"\n\n[profiles.fast]\nmodel = "gpt-5-mini"\n\n[mcp_servers.docs]\ncommand = "docs-mcp"\n';

const FIXED_PATHS: WizardPaths = {
  home: "/home/fixture",
  credentials: "/home/fixture/keys/gradiated.json",
};

const install = (paths: WizardPaths) =>
  writeConfig(paths, { apiBaseUrl: API_BASE_URL, modelId: DEFAULT_MODEL });

describe("Codex configuration text", () => {
  it("builds a Responses provider without embedding the API key", () => {
    const block = buildProviderBlock(API_BASE_URL, FIXED_PATHS);

    expect(block).toContain("[model_providers.gradiated]");
    expect(block).toContain('base_url = "https://api.gradiated.com/v1"');
    expect(block).toContain('wire_api = "responses"');
    expect(block).toContain('auth = { command = "node"');
    expect(block).not.toContain("grad_");
  });

  it("reads the key from the credentials file the wizard wrote", () => {
    const block = buildProviderBlock(API_BASE_URL, FIXED_PATHS);

    expect(block).toContain(FIXED_PATHS.credentials);
  });

  it("replaces the managed provider block and keeps it after user tables", () => {
    const existing = mergeProviderConfig(
      'model = "openai-model"\n\n[features]\nweb_search = true\n',
      buildProviderBlock("https://old.example.com", FIXED_PATHS),
    );
    const merged = mergeProviderConfig(
      existing,
      buildProviderBlock(API_BASE_URL, FIXED_PATHS),
    );

    expect(merged).toContain('model = "openai-model"');
    expect(merged).not.toContain("old.example.com");
    expect(merged.indexOf("[features]")).toBeLessThan(
      merged.indexOf("[model_providers.gradiated]"),
    );
  });

  it("keeps profile root keys before user-defined tables", () => {
    const merged = mergeProfileConfig(
      "[features]\nweb_search = true\n",
      buildProfileBlock(DEFAULT_MODEL),
    );

    expect(merged.indexOf('model_provider = "gradiated"')).toBeLessThan(
      merged.indexOf("[features]"),
    );
  });
});

describe("Codex install and uninstall", () => {
  it("restores a config.toml with tables byte-for-byte", async ({ paths }) => {
    const files = codexFiles(paths);
    await seed(files.config, USER_CONFIG);

    expect(await install(paths)).toEqual({ config: true, profile: true });
    expect(await isConfigured(paths)).toBe(true);

    expect(await uninstallConfig(paths)).toBe(true);
    expect(await uninstallProfile(paths)).toBe(true);
    expect(await readFile(files.config, "utf8")).toBe(USER_CONFIG);
    expect(existsSync(files.profile)).toBe(false);
    expect(await isConfigured(paths)).toBe(false);
  });

  it("reports no change when the configuration is current", async ({
    paths,
  }) => {
    await install(paths);

    expect(await install(paths)).toEqual({ config: false, profile: false });
  });

  it("moves the provider block last after the user adds keys", async ({
    paths,
  }) => {
    const files = codexFiles(paths);
    await install(paths);
    const installed = await readFile(files.config, "utf8");
    await writeFile(files.config, `${installed}approval_policy = "never"\n`);

    await install(paths);

    const config = await readFile(files.config, "utf8");
    expect(config.indexOf('approval_policy = "never"')).toBeLessThan(
      config.indexOf("[model_providers.gradiated]"),
    );
    expect(config.match(/\[model_providers\.gradiated\]/g)).toHaveLength(1);
  });

  it("refuses to overwrite an unmanaged gradiated profile", async ({
    paths,
  }) => {
    const files = codexFiles(paths);
    await seed(files.profile, 'model = "mine"\n');

    await expect(install(paths)).rejects.toThrow(WizardError);
    await expect(install(paths)).rejects.toThrow(files.profile);
    expect(await readFile(files.profile, "utf8")).toBe('model = "mine"\n');
    expect(existsSync(files.config)).toBe(false);
    expect(await uninstallProfile(paths)).toBe(false);
  });
});
