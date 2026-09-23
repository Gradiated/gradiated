import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect } from "vitest";
import {
  CODEX_CONFIG,
  CODEX_PROFILE,
  onWindows,
} from "../support/agent-files.js";
import { API_KEY, DEFAULT_MODEL } from "../support/catalog.js";
import { listBackups, seed } from "../support/files.js";
import {
  expectSuccess,
  hasCommand,
  runClient,
  test as it,
} from "../support/wizard.js";

const INSTALL = { agent: "codex", model: DEFAULT_MODEL } as const;

describe("Codex install", () => {
  it("writes a provider and profile without embedding the key", async ({
    home,
    api,
    wizard,
  }) => {
    expectSuccess(await wizard.install(INSTALL));

    const config = await readFile(join(home, CODEX_CONFIG), "utf8");
    expect(config).toContain("[model_providers.gradiated]");
    expect(config).toContain(`base_url = "${api.baseUrl}/v1"`);
    expect(config).toContain('wire_api = "responses"');
    expect(config).toContain('auth = { command = "node"');
    expect(config).not.toContain(API_KEY);

    const profile = await readFile(join(home, CODEX_PROFILE), "utf8");
    expect(profile).toContain('model_provider = "gradiated"');
    expect(profile).toContain(`model = "${DEFAULT_MODEL}"`);
  });

  // On Windows the cmd.exe -> codex.cmd -> node shim chain re-splits argv,
  // which corrupts the invocation independently of what the wizard wrote.
  it.skipIf(onWindows || !hasCommand("codex"))(
    "writes a profile that the real client can use",
    async ({ home, paths, wizard }) => {
      expectSuccess(await wizard.install(INSTALL));

      const codex = await runClient(
        paths,
        "codex",
        [
          "exec",
          "--profile",
          "gradiated",
          "--strict-config",
          "--skip-git-repo-check",
          "--ephemeral",
          "--sandbox",
          "read-only",
          "--json",
          "ready",
        ],
        { CODEX_HOME: join(home, ".codex") },
      );

      expect(codex.status, codex.stderr).toBe(0);
      expect(codex.stdout).toContain("ready");
    },
  );

  it("re-runs install and uninstall idempotently and backs up user config once", async ({
    home,
    wizard,
  }) => {
    await seed(join(home, CODEX_CONFIG), 'model = "gpt-5"\n');

    expectSuccess(await wizard.install(INSTALL));
    const configAfterFirst = await readFile(join(home, CODEX_CONFIG), "utf8");
    const profileAfterFirst = await readFile(join(home, CODEX_PROFILE), "utf8");
    expect(configAfterFirst).toContain('model = "gpt-5"');
    expect(await listBackups(join(home, ".codex"))).toHaveLength(1);

    const second = await wizard.install(INSTALL);
    expectSuccess(second);
    expect(second.stdout).toContain(
      "Codex already has the current Gradiated provider",
    );
    expect(await readFile(join(home, CODEX_CONFIG), "utf8")).toBe(
      configAfterFirst,
    );
    expect(await readFile(join(home, CODEX_PROFILE), "utf8")).toBe(
      profileAfterFirst,
    );
    expect(await listBackups(join(home, ".codex"))).toHaveLength(1);

    expectSuccess(await wizard.uninstall({ agent: "codex" }));

    const repeated = await wizard.uninstall({ agent: "codex" });
    expectSuccess(repeated);
    expect(repeated.stdout).toContain("not configured for Codex");
  });

  it("keeps the run focused on the agent passed with --agent", async ({
    home,
    wizard,
  }) => {
    const result = await wizard.install({ agent: "codex" });

    expectSuccess(result);
    expect(result.stdout).not.toMatch(/opencode/i);
    expect(result.stdout).not.toMatch(/claude/i);
    expect((await readdir(home)).sort()).toEqual([".codex", ".gradiated"]);
    expect(await readdir(join(home, ".gradiated"))).toEqual([
      "credentials.json",
    ]);
  });
});
