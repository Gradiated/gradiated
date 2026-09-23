import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect } from "vitest";
import { OPENCODE_AUTH, OPENCODE_CONFIG } from "../support/agent-files.js";
import {
  API_KEY,
  DEFAULT_MODEL,
  REJECTED_KEY,
  ROTATED_KEY,
  SECOND_MODEL,
} from "../support/catalog.js";
import { listBackups, readJson, seed } from "../support/files.js";
import {
  expectFailure,
  expectSuccess,
  hasCommand,
  runClient,
  test as it,
} from "../support/wizard.js";

describe("OpenCode install", () => {
  it("writes the provider block, credential file and auth.json", async ({
    home,
    paths,
    api,
    wizard,
  }) => {
    expectSuccess(
      await wizard.install({
        agent: "opencode",
        model: "Z-AI/GLM-5.3-FLASH",
        env: { GRADIATED_API_KEY: "grad_unselected_environment_fixture" },
      }),
    );

    const config = await readJson(join(home, OPENCODE_CONFIG));
    expect(config).toMatchObject({
      $schema: "https://opencode.ai/config.json",
      model: `gradiated/${DEFAULT_MODEL}`,
      provider: {
        gradiated: {
          npm: "@ai-sdk/openai-compatible",
          name: "Gradiated",
          options: { baseURL: api.baseUrl },
        },
      },
    });
    expect(config).not.toHaveProperty([
      "provider",
      "gradiated",
      "options",
      "apiKey",
    ]);
    expect(config).toHaveProperty(
      ["provider", "gradiated", "models", DEFAULT_MODEL],
      { name: "GLM-5.3 Flash", limit: { context: 1_048_576, output: 131_072 } },
    );
    expect(config).toHaveProperty(
      ["provider", "gradiated", "models", SECOND_MODEL],
      { name: "Gemma 4 31B", limit: { context: 128_000, output: 8_192 } },
    );

    expect(await readJson(paths.credentials)).toMatchObject({
      api_key: API_KEY,
    });
    expect(await readJson(join(home, OPENCODE_AUTH))).toMatchObject({
      gradiated: { type: "api", key: API_KEY },
    });
  });

  it("fails without prompting or writing config when --yes gets a rejected key", async ({
    home,
    paths,
    wizard,
  }) => {
    const result = await wizard.install({
      agent: "opencode",
      key: REJECTED_KEY,
    });

    expectFailure(result, "API key invalid.");
    expect(result.stdout).not.toContain("Paste a different API key");
    expect(existsSync(paths.credentials)).toBe(false);
    expect(existsSync(join(home, OPENCODE_CONFIG))).toBe(false);
  });

  it("keeps a JSONC config and its own default model", async ({
    home,
    wizard,
  }) => {
    await seed(
      join(home, OPENCODE_CONFIG),
      `{
  // Personal settings.
  "$schema": "https://opencode.ai/config.json",
  "model": "anthropic/claude-sonnet-4-5", /* keep this default */
  "watcher": { "ignore": ["src/**/*.ts"] },
}
`,
    );

    expectSuccess(await wizard.install({ agent: "opencode" }));

    const config = await readJson(join(home, OPENCODE_CONFIG));
    expect(config).toMatchObject({
      model: "anthropic/claude-sonnet-4-5",
      watcher: { ignore: ["src/**/*.ts"] },
    });
    expect(config).toHaveProperty(["provider", "gradiated"]);
  });

  it("uses the model passed with --model as the default", async ({
    home,
    wizard,
  }) => {
    expectSuccess(
      await wizard.install({ agent: "opencode", model: SECOND_MODEL }),
    );

    expect(await readJson(join(home, OPENCODE_CONFIG))).toMatchObject({
      model: `gradiated/${SECOND_MODEL}`,
    });
  });

  it("leaves a project opencode.json in the working directory alone", async ({
    home,
    wizard,
  }) => {
    const project = join(home, "project");
    const projectConfig = '{ "model": "local/model" }\n';
    await seed(join(project, "opencode.json"), projectConfig);

    expectSuccess(await wizard.install({ agent: "opencode", cwd: project }));

    expect(await readFile(join(project, "opencode.json"), "utf8")).toBe(
      projectConfig,
    );
    expect(await readJson(join(home, OPENCODE_CONFIG))).toHaveProperty([
      "provider",
      "gradiated",
    ]);
  });

  it("re-runs install and uninstall idempotently", async ({ home, wizard }) => {
    const install = { agent: "opencode", model: DEFAULT_MODEL } as const;

    expectSuccess(await wizard.install(install));
    const configAfterFirst = await readFile(
      join(home, OPENCODE_CONFIG),
      "utf8",
    );
    const authAfterFirst = await readFile(join(home, OPENCODE_AUTH), "utf8");

    const second = await wizard.install(install);
    expectSuccess(second);
    expect(second.stdout).toContain(
      "OpenCode already has the current Gradiated provider",
    );
    expect(await readFile(join(home, OPENCODE_CONFIG), "utf8")).toBe(
      configAfterFirst,
    );
    expect(await readFile(join(home, OPENCODE_AUTH), "utf8")).toBe(
      authAfterFirst,
    );
    expect(await listBackups(join(home, ".config/opencode"))).toEqual([]);

    expectSuccess(await wizard.uninstall({ agent: "opencode" }));

    const repeated = await wizard.uninstall({ agent: "opencode" });
    expectSuccess(repeated);
    expect(repeated.stdout).toContain("not configured for OpenCode");
  });

  it("reports a rotated key as a change", async ({ home, paths, wizard }) => {
    expectSuccess(await wizard.install({ agent: "opencode" }));

    const rotated = await wizard.install({
      agent: "opencode",
      key: ROTATED_KEY,
    });

    expectSuccess(rotated);
    expect(rotated.stdout).toContain(`API key in ${paths.credentials}`);
    expect(rotated.stdout).toContain(
      `OpenCode credential in ${join(home, OPENCODE_AUTH)}`,
    );
    expect(rotated.stdout).not.toContain("No files were changed");
    expect(await readJson(join(home, OPENCODE_AUTH))).toMatchObject({
      gradiated: { key: ROTATED_KEY },
    });
  });

  it.skipIf(!hasCommand("opencode"))(
    "registers the provider and credential with the real client",
    async ({ home, paths, wizard }) => {
      expectSuccess(
        await wizard.install({ agent: "opencode", model: DEFAULT_MODEL }),
      );

      // A completion round-trip depends on the host because some hosts
      // sandbox the bundled provider plugin, so this checks config parsing,
      // model registration and stored credentials only.
      const xdg = {
        XDG_CONFIG_HOME: join(home, ".config"),
        XDG_DATA_HOME: join(home, ".local", "share"),
      };

      const models = await runClient(paths, "opencode", ["models"], xdg);
      expect(models.status, models.stderr).toBe(0);
      expect(models.stdout).toContain(`gradiated/${DEFAULT_MODEL}`);
      expect(models.stdout).toContain(`gradiated/${SECOND_MODEL}`);

      const auth = await runClient(paths, "opencode", ["auth", "list"], xdg);
      expect(auth.status, auth.stderr).toBe(0);
      expect(auth.stdout).toContain("gradiated");
    },
    60_000,
  );
});
