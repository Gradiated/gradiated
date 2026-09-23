import { existsSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { describe, expect } from "vitest";
import {
  CLAUDE_BIN,
  CLAUDE_COMMAND,
  CODEX_CONFIG,
  OPENCODE_AUTH,
  OPENCODE_CONFIG,
  onWindows,
} from "../support/agent-files.js";
import { API_KEY, DEFAULT_MODEL } from "../support/catalog.js";
import { readJson, seed } from "../support/files.js";
import { expectSuccess, test as it } from "../support/wizard.js";

const SEEDED_FILES = {
  ".zshrc": "export EDITOR=vim\n",
  [CODEX_CONFIG]:
    'model = "gpt-5"\n\n[profiles.fast]\nmodel = "gpt-5-mini"\n\n[mcp_servers.docs]\ncommand = "docs-mcp"\n',
  [OPENCODE_CONFIG]: `${JSON.stringify(
    {
      $schema: "https://opencode.ai/config.json",
      provider: { local: { npm: "@ai-sdk/openai-compatible", name: "Local" } },
    },
    null,
    2,
  )}\n`,
  [OPENCODE_AUTH]: `${JSON.stringify(
    { local: { type: "api", key: "local-key" } },
    null,
    2,
  )}\n`,
  [join(CLAUDE_BIN, "notes.txt")]: "unrelated\n",
};

const JSON_FILES = new Set([OPENCODE_CONFIG, OPENCODE_AUTH]);

const seedHome = async (home: string): Promise<void> => {
  for (const [path, content] of Object.entries(SEEDED_FILES)) {
    await seed(join(home, path), content);
  }
};

const listFiles = async (home: string): Promise<string[]> => {
  const entries = await readdir(home, { recursive: true, withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => relative(home, join(entry.parentPath, entry.name)))
    .sort();
};

describe("uninstall", () => {
  it("removes the OpenCode provider and keeps the stored key", async ({
    home,
    paths,
    wizard,
  }) => {
    expectSuccess(await wizard.install({ agent: "opencode" }));
    expect(await readJson(join(home, OPENCODE_CONFIG))).toHaveProperty([
      "provider",
      "gradiated",
    ]);

    const uninstall = await wizard.uninstall({ agent: "opencode" });
    expectSuccess(uninstall);
    expect(uninstall.stdout).toContain("Removed Gradiated configuration");

    const config = await readJson(join(home, OPENCODE_CONFIG));
    expect(config).toHaveProperty("provider");
    expect(config).not.toHaveProperty(["provider", "gradiated"]);
    expect(config).not.toHaveProperty("model");
    expect(await readJson(join(home, OPENCODE_AUTH))).not.toHaveProperty(
      "gradiated",
    );
    expect(await readJson(paths.credentials)).toMatchObject({
      api_key: API_KEY,
    });
  });

  it("stays scoped to --agent and changes nothing with --dry-run", async ({
    home,
    paths,
    wizard,
  }) => {
    expectSuccess(
      await wizard.install({ agent: "claude", model: DEFAULT_MODEL }),
    );
    const command = join(home, CLAUDE_COMMAND);

    const scoped = await wizard.uninstall({ agent: "opencode" });
    expectSuccess(scoped);
    expect(scoped.stdout).toContain("not configured for OpenCode");
    expect(existsSync(command)).toBe(true);

    const dry = await wizard.uninstall({ dryRun: true });
    expectSuccess(dry);
    expect(dry.stdout).toContain("Would remove");
    expect(dry.stdout).toContain("Dry run complete. No files were changed.");
    expect(existsSync(command)).toBe(true);
    expect(await readJson(paths.credentials)).toEqual({ api_key: API_KEY });
  });

  // The wizard re-serializes JSON, so JSON files are compared parsed.
  it.skipIf(onWindows)(
    "restores every user file after installing all agents",
    async ({ home, wizard }) => {
      await seedHome(home);

      const install = await wizard.install();
      expectSuccess(install);
      expect(install.stdout).toContain(
        "Gradiated is configured for OpenCode, Codex, and Claude Code",
      );

      expectSuccess(await wizard.uninstall());

      for (const [path, content] of Object.entries(SEEDED_FILES)) {
        const restored = await readFile(join(home, path), "utf8");
        if (JSON_FILES.has(path)) {
          expect(JSON.parse(restored), path).toEqual(JSON.parse(content));
        } else {
          expect(restored, path).toBe(content);
        }
      }

      const added = (await listFiles(home)).filter(
        (path) => !(path in SEEDED_FILES),
      );
      expect(added.filter((path) => !path.includes(".bak."))).toEqual([]);
    },
  );
});
