import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import {
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { createServer, type Server } from "node:http";
import { homedir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const FIXTURE_CATALOG = {
  data: [
    {
      schema_version: "2.4",
      id: "z-ai/glm-5.3-flash",
      name: "GLM-5.3 Flash",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 1_048_576, unit: "token" },
          },
        },
      ],
      output_modalities: [
        {
          type: "text",
          max_length: { value: 131_072, unit: "token" },
          streaming: true,
          supported_parameters: {},
        },
      ],
    },
    {
      schema_version: "2.4",
      id: "google/gemma-4-31b-it",
      name: "Gemma 4 31B",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 128_000, unit: "token" },
          },
        },
      ],
      output_modalities: [
        {
          type: "text",
          max_length: { value: 8_192, unit: "token" },
          streaming: true,
          supported_parameters: {},
        },
      ],
    },
  ],
};

const PORT = 8973;
const API_KEY = "grad_test_wizard_fixture_key_0000000000000000000";

let server: Server;

const startStub = async (): Promise<void> => {
  server = createServer((request, response) => {
    const url = new URL(request.url ?? "/", `http://127.0.0.1:${PORT}`);
    const auth = request.headers.authorization;
    if (auth !== `Bearer ${API_KEY}`) {
      response.writeHead(401, { "content-type": "application/problem+json" });
      response.end(
        JSON.stringify({
          type: "https://gradiated.com/problems/unauthenticated",
          title: "Authentication required",
          status: 401,
          detail: "The API key was rejected.",
          code: "unauthenticated",
          request_id: "stub",
        }),
      );
      return;
    }
    if (url.pathname === "/models") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(FIXTURE_CATALOG));
      return;
    }
    if (url.pathname === "/v1/responses") {
      const events = [
        {
          type: "response.created",
          response: {
            id: "resp_wizard",
            object: "response",
            status: "in_progress",
            model: "z-ai/glm-5.3-flash",
            output: [],
            usage: {
              input_tokens: 1,
              output_tokens: 0,
              total_tokens: 1,
              input_tokens_details: { cached_tokens: 0 },
              output_tokens_details: { reasoning_tokens: 0 },
            },
          },
        },
        {
          type: "response.output_item.added",
          output_index: 0,
          item: {
            type: "message",
            id: "msg_0",
            role: "assistant",
            status: "in_progress",
            content: [],
          },
        },
        {
          type: "response.content_part.added",
          output_index: 0,
          content_index: 0,
          part: { type: "output_text", text: "" },
        },
        {
          type: "response.output_text.delta",
          output_index: 0,
          content_index: 0,
          delta: "ready",
        },
        {
          type: "response.content_part.done",
          output_index: 0,
          content_index: 0,
          part: { type: "output_text", text: "ready" },
        },
        {
          type: "response.output_item.done",
          output_index: 0,
          item: {
            type: "message",
            role: "assistant",
            status: "completed",
            content: [{ type: "output_text", text: "ready" }],
          },
        },
        {
          type: "response.completed",
          response: {
            id: "resp_wizard",
            object: "response",
            status: "completed",
            incomplete_details: null,
            model: "z-ai/glm-5.3-flash",
            output: [
              {
                type: "message",
                role: "assistant",
                status: "completed",
                content: [{ type: "output_text", text: "ready" }],
              },
            ],
            usage: {
              input_tokens: 1,
              output_tokens: 1,
              total_tokens: 2,
              input_tokens_details: { cached_tokens: 0 },
              output_tokens_details: { reasoning_tokens: 0 },
            },
          },
        },
      ];
      response.writeHead(200, {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
      });
      response.end(
        events
          .map(
            (event) =>
              `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`,
          )
          .join(""),
      );
      return;
    }
    response.writeHead(404, { "content-type": "application/problem+json" });
    response.end(
      JSON.stringify({
        type: "https://gradiated.com/problems/not-found",
        title: "Not found",
        status: 404,
        detail: "Not found.",
        code: "not_found",
        request_id: "stub",
      }),
    );
  });
  await new Promise<void>((resolvePromise) => {
    server.listen(PORT, "127.0.0.1", resolvePromise);
  });
};

const stopStub = async (): Promise<void> => {
  await new Promise<void>((resolvePromise, rejectPromise) => {
    server.close((error) => (error ? rejectPromise(error) : resolvePromise()));
  });
};

const runWizard = async (
  arguments_: readonly string[],
  home: string,
): Promise<{ status: number | null; stdout: string; stderr: string }> =>
  new Promise((resolvePromise) => {
    const child = spawn(
      process.execPath,
      [join(import.meta.dirname, "../dist/bin.js"), ...arguments_],
      {
        env: {
          ...process.env,
          HOME: home,
          USERPROFILE: home,
          GRADIATED_CREDENTIALS_PATH: join(
            home,
            ".gradiated",
            "credentials.json",
          ),
          GRADIATED_API_KEY: "",
        },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("close", (status) => {
      resolvePromise({ status, stdout, stderr });
    });
  });

const runWizardUninstall = (
  arguments_: readonly string[],
  home: string,
): Promise<{ status: number | null; stdout: string; stderr: string }> =>
  runWizard(["uninstall", ...arguments_], home);

/** True when the command exists on PATH (does not require exit code 0). */
const hasCommand = (command: string): boolean =>
  spawnSync(command, ["--version"], {
    stdio: "ignore",
    shell: process.platform === "win32",
  }).error === undefined;

/** Run an installed CLI with a temporary HOME and optional XDG overrides. */
const runClient = async (
  command: string,
  arguments_: readonly string[],
  home: string,
  extraEnv: Record<string, string> = {},
): Promise<{ status: number | null; stdout: string; stderr: string }> =>
  new Promise((resolvePromise) => {
    const child = spawn(command, [...arguments_], {
      cwd: home,
      env: {
        ...process.env,
        HOME: home,
        USERPROFILE: home,
        NO_COLOR: "1",
        ...extraEnv,
      },
      shell: process.platform === "win32",
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("close", (status) => {
      resolvePromise({ status, stdout, stderr });
    });
  });

/**
 * Run the installed claude-gradiated command with <home>/.gradiated/bin (and
 * an optional directory, e.g. holding a fake `claude`) first on PATH.
 */
const runClaudeWrapper = async (
  home: string,
  pathPrepend: readonly string[] = [],
  arguments_: readonly string[] = [],
): Promise<{ status: number | null; stdout: string; stderr: string }> =>
  new Promise((resolvePromise) => {
    const separator = process.platform === "win32" ? ";" : ":";
    const child = spawn("claude-gradiated", [...arguments_], {
      env: {
        ...process.env,
        HOME: home,
        USERPROFILE: home,
        GRADIATED_CREDENTIALS_PATH: join(
          home,
          ".gradiated",
          "credentials.json",
        ),
        GRADIATED_API_KEY: "",
        PATH: [
          join(home, ".gradiated", "bin"),
          ...pathPrepend,
          process.env.PATH ?? "",
        ].join(separator),
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("close", (status) => {
      resolvePromise({ status, stdout, stderr });
    });
  });

const listBackups = async (directory: string): Promise<number> => {
  try {
    const entries = await readdir(directory);
    return entries.filter((entry) => entry.includes(".bak.")).length;
  } catch {
    return 0;
  }
};

const runCodex = async (
  home: string,
): Promise<{ status: number | null; stdout: string; stderr: string }> =>
  new Promise((resolvePromise) => {
    const child = spawn(
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
      {
        cwd: home,
        env: {
          ...process.env,
          HOME: home,
          USERPROFILE: home,
          CODEX_HOME: join(home, ".codex"),
          GRADIATED_CREDENTIALS_PATH: join(
            home,
            ".gradiated",
            "credentials.json",
          ),
          GRADIATED_API_KEY: "",
          NO_COLOR: "1",
        },
        shell: process.platform === "win32",
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("close", (status) => {
      resolvePromise({ status, stdout, stderr });
    });
  });

describe("wizard install end to end", () => {
  beforeAll(startStub);
  afterAll(async () => {
    await stopStub();
  });

  it("writes the opencode provider block, credential file and auth.json", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const result = await runWizard(
        [
          "--yes",
          "--agent",
          "opencode",
          "--key",
          API_KEY,
          "--model",
          "Z-AI/GLM-5.3-FLASH",
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );

      expect(result.stderr).toBe("");
      expect(result.status).toBe(0);

      const config = JSON.parse(
        await readFile(join(home, ".config/opencode/opencode.json"), "utf8"),
      ) as {
        $schema: string;
        model: string;
        provider: Record<string, unknown>;
      };
      expect(config.$schema).toBe("https://opencode.ai/config.json");
      expect(config.model).toBe("gradiated/z-ai/glm-5.3-flash");
      const provider = config.provider.gradiated as {
        npm: string;
        name: string;
        options: { baseURL: string; apiKey: string };
        models: Record<string, unknown>;
      };
      expect(provider.npm).toBe("@ai-sdk/openai-compatible");
      expect(provider.name).toBe("Gradiated");
      expect(provider.options.baseURL).toBe(`http://127.0.0.1:${PORT}`);
      expect(provider.options.apiKey).toBe("{env:GRADIATED_API_KEY}");
      expect(provider.models["z-ai/glm-5.3-flash"]).toEqual({
        name: "GLM-5.3 Flash",
        limit: { context: 1_048_576, output: 131_072 },
      });
      expect(provider.models["google/gemma-4-31b-it"]).toEqual({
        name: "Gemma 4 31B",
        limit: { context: 128_000, output: 8_192 },
      });

      const credentials = JSON.parse(
        await readFile(join(home, ".gradiated/credentials.json"), "utf8"),
      ) as { api_key: string };
      expect(credentials.api_key).toBe(API_KEY);

      const auth = JSON.parse(
        await readFile(join(home, ".local/share/opencode/auth.json"), "utf8"),
      ) as { gradiated: { type: string; key: string } };
      expect(auth.gradiated.type).toBe("api");
      expect(auth.gradiated.key).toBe(API_KEY);
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);

  it("writes a Codex profile that the real client can use", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const result = await runWizard(
        [
          "--yes",
          "--agent",
          "codex",
          "--key",
          API_KEY,
          "--model",
          "z-ai/glm-5.3-flash",
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );

      expect(result.stderr).toBe("");
      expect(result.status).toBe(0);

      const config = await readFile(join(home, ".codex/config.toml"), "utf8");
      expect(config).toContain("[model_providers.gradiated]");
      expect(config).toContain(`base_url = "http://127.0.0.1:${PORT}/v1"`);
      expect(config).toContain('wire_api = "responses"');
      expect(config).toContain('auth = { command = "node"');
      expect(config).not.toContain(API_KEY);

      const profile = await readFile(
        join(home, ".codex/gradiated.config.toml"),
        "utf8",
      );
      expect(profile).toContain('model_provider = "gradiated"');
      expect(profile).toContain('model = "z-ai/glm-5.3-flash"');

      // Running the real client is checked wherever `codex` is installed
      // (CI installs the latest version). The Windows cmd.exe -> codex.cmd ->
      // node shim chain re-splits argv, which corrupts the invocation
      // independently of what the wizard wrote; the content assertions above
      // are the platform-relevant part on Windows.
      if (process.platform !== "win32" && hasCommand("codex")) {
        const codex = await runCodex(home);
        expect(codex.status, codex.stderr).toBe(0);
        expect(codex.stdout).toContain("ready");
      }
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);

  it("fails with the gateway message when the key is rejected", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const result = await runWizard(
        [
          "--yes",
          "--agent",
          "opencode",
          "--key",
          "grad_wrong_key",
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );

      expect(result.status).toBe(1);
      expect(result.stdout).toContain("The API key was rejected");
      await expect(
        readFile(join(home, ".config/opencode/opencode.json"), "utf8"),
      ).rejects.toThrow();
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);

  it("respects an existing default model", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const { mkdir, writeFile } = await import("node:fs/promises");
      const configDir = join(home, ".config/opencode");
      await mkdir(configDir, { recursive: true });
      await writeFile(
        join(configDir, "opencode.json"),
        JSON.stringify({
          $schema: "https://opencode.ai/config.json",
          model: "anthropic/claude-sonnet-4-5",
          // trailing comma and comment on purpose
        }) + "\n",
      );

      const result = await runWizard(
        [
          "--yes",
          "--agent",
          "opencode",
          "--key",
          API_KEY,
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );

      expect(result.status).toBe(0);
      const config = JSON.parse(
        await readFile(join(configDir, "opencode.json"), "utf8"),
      ) as { model: string; provider: Record<string, unknown> };
      expect(config.model).toBe("anthropic/claude-sonnet-4-5");
      expect(Object.keys(config.provider)).toContain("gradiated");
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);

  it("uninstalls the opencode provider and keeps unrelated config", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const install = await runWizard(
        [
          "--yes",
          "--agent",
          "opencode",
          "--key",
          API_KEY,
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );
      expect(install.status).toBe(0);

      const configPath = join(home, ".config/opencode/opencode.json");
      const before = JSON.parse(await readFile(configPath, "utf8")) as {
        model: string;
        provider: Record<string, unknown>;
      };
      expect(Object.keys(before.provider)).toContain("gradiated");

      const uninstall = await runWizardUninstall(
        ["--yes", "--agent", "opencode"],
        home,
      );
      expect(uninstall.stderr).toBe("");
      expect(uninstall.status).toBe(0);
      expect(uninstall.stdout).toContain("Removed Gradiated configuration");

      const config = JSON.parse(await readFile(configPath, "utf8")) as {
        provider: Record<string, unknown>;
        model?: string;
      };
      expect(Object.keys(config.provider)).not.toContain("gradiated");
      expect(config.model).toBeUndefined();

      const auth = JSON.parse(
        await readFile(join(home, ".local/share/opencode/auth.json"), "utf8"),
      ) as Record<string, unknown>;
      expect(auth.gradiated).toBeUndefined();

      // The stored key is a separate uninstall target; removing the agent
      // must leave the credential file untouched.
      const credentials = JSON.parse(
        await readFile(join(home, ".gradiated/credentials.json"), "utf8"),
      ) as Record<string, unknown>;
      expect(credentials.api_key).toBe(API_KEY);
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);

  it("installs and uninstalls the claude wrapper without touching ~/.claude", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      // No shell profiles initially; create one so PATH handling is exercised.
      const { writeFile: writeFileRaw } = await import("node:fs/promises");
      await writeFileRaw(join(home, ".zshrc"), "export EDITOR=vim\n");

      const install = await runWizard(
        [
          "--yes",
          "--agent",
          "claude",
          "--key",
          API_KEY,
          "--model",
          "z-ai/glm-5.3-flash",
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );
      expect(install.stderr).toBe("");
      expect(install.status).toBe(0);
      expect(install.stdout).toContain("claude-gradiated");

      // The wrapper launcher is claude-gradiated.js on every platform, and
      // POSIX also gets the extensionless claude-gradiated command that PATH
      // lookup resolves.
      const wrapper = await readFile(
        join(home, ".gradiated/bin/claude-gradiated.js"),
        "utf8",
      );
      // The wrapper stores exactly the base URL the wizard was invoked with.
      expect(wrapper).toContain(`const BASE_URL = "http://127.0.0.1:${PORT}"`);
      expect(wrapper).toContain('"z-ai/glm-5.3-flash"');
      // The wrapper must read the key at runtime, never embed it.
      expect(wrapper).not.toContain(API_KEY);
      expect(wrapper).toContain("credentials.json");

      const commandPath = join(home, ".gradiated/bin/claude-gradiated");
      if (process.platform === "win32") {
        const shim = await readFile(
          join(home, ".gradiated/bin/claude-gradiated.cmd"),
          "utf8",
        );
        expect(shim).toContain("claude-gradiated.js");
      } else {
        expect(existsSync(commandPath)).toBe(true);
        const mode = (await stat(commandPath)).mode;
        expect(mode & 0o111).toBe(0o111);
        expect(await readFile(commandPath, "utf8")).toContain(
          "#!/usr/bin/env node",
        );
      }

      const zshrc = await readFile(join(home, ".zshrc"), "utf8");
      expect(zshrc).toContain("export EDITOR=vim");
      expect(zshrc).toContain("# >>> gradiated >>>");
      expect(zshrc).toContain(".gradiated/bin");

      // ~/.claude must remain untouched by the wizard.
      expect(existsSync(join(home, ".claude"))).toBe(false);

      const uninstall = await runWizardUninstall(["--yes"], home);
      expect(uninstall.stderr).toBe("");
      expect(uninstall.status).toBe(0);
      expect(uninstall.stdout).toContain("claude-gradiated wrapper");

      expect(existsSync(join(home, ".gradiated/bin"))).toBe(false);
      const cleaned = await readFile(join(home, ".zshrc"), "utf8");
      expect(cleaned).toContain("export EDITOR=vim");
      expect(cleaned).not.toContain("# >>> gradiated >>>");
      expect(existsSync(join(home, ".claude"))).toBe(false);
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);

  it("runs claude through the wrapper with the Gradiated gateway env", async () => {
    // PATH lookup for an extensionless script is a POSIX concern; Windows
    // coverage is the .cmd shim content assertions in the test above.
    if (process.platform === "win32") {
      console.warn("wrapper PATH lookup is POSIX-only; skipping on Windows");
      return;
    }
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      // A fake `claude` earlier on PATH records the environment the wrapper
      // hands to Claude Code, so the wiring is verifiable without network.
      const fakeBin = join(home, "fakebin");
      await mkdir(fakeBin, { recursive: true });
      await writeFile(
        join(fakeBin, "claude"),
        "#!/bin/sh\n" +
          'echo "BASE_URL=$ANTHROPIC_BASE_URL"\n' +
          'echo "AUTH_TOKEN=$ANTHROPIC_AUTH_TOKEN"\n' +
          'echo "MODEL=$ANTHROPIC_MODEL"\n',
        { mode: 0o755 },
      );

      const install = await runWizard(
        [
          "--yes",
          "--agent",
          "claude",
          "--key",
          API_KEY,
          "--model",
          "z-ai/glm-5.3-flash",
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );
      expect(install.stderr).toBe("");
      expect(install.status).toBe(0);

      const result = await runClaudeWrapper(home, [fakeBin], ["--version"]);
      expect(result.status, result.stderr).toBe(0);
      expect(result.stdout).toContain(`BASE_URL=http://127.0.0.1:${PORT}`);
      expect(result.stdout).toContain(`AUTH_TOKEN=${API_KEY}`);
      expect(result.stdout).toContain("MODEL=z-ai/glm-5.3-flash");
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);

  it("passes arguments through the wrapper to the real Claude Code", async () => {
    if (process.platform === "win32") {
      console.warn("wrapper PATH lookup is POSIX-only; skipping on Windows");
      return;
    }
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const install = await runWizard(
        [
          "--yes",
          "--agent",
          "claude",
          "--key",
          API_KEY,
          "--model",
          "z-ai/glm-5.3-flash",
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );
      expect(install.status).toBe(0);

      // CI installs the latest Claude Code; skip silently where it is not
      // present (the env-wiring test above covers the wrapper itself).
      if (!hasCommand("claude")) {
        console.warn("claude is not installed; skipping the real client check");
        return;
      }
      const result = await runClaudeWrapper(home, [], ["--version"]);
      expect(result.status, result.stderr).toBe(0);
      expect(result.stdout).toMatch(/\d+\.\d+/);
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 60_000);

  it("registers the provider and credential with the real opencode client", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const install = await runWizard(
        [
          "--yes",
          "--agent",
          "opencode",
          "--key",
          API_KEY,
          "--model",
          "z-ai/glm-5.3-flash",
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );
      expect(install.stderr).toBe("");
      expect(install.status).toBe(0);

      // CI installs the latest opencode. A full completion round-trip is
      // environment dependent (the bundled provider plugin is sandboxed on
      // some hosts), so assert on the deterministic client surfaces: config
      // parsing, model registration and stored credentials.
      if (!hasCommand("opencode")) {
        console.warn(
          "opencode is not installed; skipping the real client check",
        );
        return;
      }
      const xdgEnv = {
        XDG_CONFIG_HOME: join(home, ".config"),
        XDG_DATA_HOME: join(home, ".local", "share"),
      };
      const models = await runClient("opencode", ["models"], home, xdgEnv);
      expect(models.status, models.stderr).toBe(0);
      expect(models.stdout).toContain("gradiated/z-ai/glm-5.3-flash");
      expect(models.stdout).toContain("gradiated/google/gemma-4-31b-it");

      const auth = await runClient("opencode", ["auth", "list"], home, xdgEnv);
      expect(auth.status, auth.stderr).toBe(0);
      expect(auth.stdout).toContain("gradiated");
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 60_000);

  it("re-running install and uninstall for codex is idempotent", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const arguments_ = [
        "--yes",
        "--agent",
        "codex",
        "--key",
        API_KEY,
        "--model",
        "z-ai/glm-5.3-flash",
        "--api-base-url",
        `http://127.0.0.1:${PORT}`,
      ];
      // Pre-existing user configuration: the first install must back it up
      // and preserve it, and nothing may change after that.
      await mkdir(join(home, ".codex"), { recursive: true });
      await writeFile(join(home, ".codex/config.toml"), 'model = "gpt-5"\n');
      const first = await runWizard(arguments_, home);
      expect(first.stderr).toBe("");
      expect(first.status).toBe(0);
      expect(
        await readFile(join(home, ".codex/config.toml"), "utf8"),
      ).toContain('model = "gpt-5"');

      const configPath = join(home, ".codex/config.toml");
      const profilePath = join(home, ".codex/gradiated.config.toml");
      const configAfterFirst = await readFile(configPath, "utf8");
      const profileAfterFirst = await readFile(profilePath, "utf8");
      expect(await listBackups(join(home, ".codex"))).toBe(1);

      const second = await runWizard(arguments_, home);
      expect(second.stderr).toBe("");
      expect(second.status).toBe(0);
      expect(second.stdout).toContain(
        "Codex already has the current Gradiated provider",
      );
      expect(await readFile(configPath, "utf8")).toBe(configAfterFirst);
      expect(await readFile(profilePath, "utf8")).toBe(profileAfterFirst);
      // The unchanged second run must not create another backup.
      expect(await listBackups(join(home, ".codex"))).toBe(1);

      const uninstallFirst = await runWizardUninstall(
        ["--yes", "--agent", "codex"],
        home,
      );
      expect(uninstallFirst.stderr).toBe("");
      expect(uninstallFirst.status).toBe(0);

      const uninstallSecond = await runWizardUninstall(
        ["--yes", "--agent", "codex"],
        home,
      );
      expect(uninstallSecond.stderr).toBe("");
      expect(uninstallSecond.status).toBe(0);
      expect(uninstallSecond.stdout).toContain("not configured for codex");
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);

  it("re-running install and uninstall for opencode is idempotent", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const arguments_ = [
        "--yes",
        "--agent",
        "opencode",
        "--key",
        API_KEY,
        "--model",
        "z-ai/glm-5.3-flash",
        "--api-base-url",
        `http://127.0.0.1:${PORT}`,
      ];
      const first = await runWizard(arguments_, home);
      expect(first.status).toBe(0);

      const configPath = join(home, ".config/opencode/opencode.json");
      const authPath = join(home, ".local/share/opencode/auth.json");
      const configAfterFirst = await readFile(configPath, "utf8");
      const authAfterFirst = await readFile(authPath, "utf8");

      const second = await runWizard(arguments_, home);
      expect(second.status).toBe(0);
      expect(second.stdout).toContain(
        "OpenCode already has the current Gradiated provider",
      );
      expect(await readFile(configPath, "utf8")).toBe(configAfterFirst);
      expect(await readFile(authPath, "utf8")).toBe(authAfterFirst);
      expect(await listBackups(join(home, ".config/opencode"))).toBe(0);

      const uninstallFirst = await runWizardUninstall(
        ["--yes", "--agent", "opencode"],
        home,
      );
      expect(uninstallFirst.status).toBe(0);

      const uninstallSecond = await runWizardUninstall(
        ["--yes", "--agent", "opencode"],
        home,
      );
      expect(uninstallSecond.status).toBe(0);
      expect(uninstallSecond.stdout).toContain("not configured for opencode");
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);

  it("focuses the run on the requested agent when --agent is passed", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const result = await runWizard(
        [
          "--yes",
          "--agent",
          "codex",
          "--key",
          API_KEY,
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );
      expect(result.stderr).toBe("");
      expect(result.status).toBe(0);

      // Other agents must not appear in the output or on disk. (Detection
      // itself scaffolds opencode/codex state dirs via their --version
      // calls, so assert on the configuration files the wizard writes.)
      expect(result.stdout).not.toMatch(/opencode/i);
      expect(result.stdout).not.toMatch(/claude/i);
      expect(existsSync(join(home, ".config/opencode/opencode.json"))).toBe(
        false,
      );
      expect(existsSync(join(home, ".local/share/opencode/auth.json"))).toBe(
        false,
      );
      expect(existsSync(join(home, ".gradiated/bin"))).toBe(false);
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);

  it("uninstall with --agent and --dry-run stay scoped and change nothing", async () => {
    const home = await mkdtemp(join(homedir(), "gradiated-wizard-test-"));
    try {
      const install = await runWizard(
        [
          "--yes",
          "--agent",
          "claude",
          "--key",
          API_KEY,
          "--model",
          "z-ai/glm-5.3-flash",
          "--api-base-url",
          `http://127.0.0.1:${PORT}`,
        ],
        home,
      );
      expect(install.status).toBe(0);

      // A scoped uninstall of an unconfigured agent removes nothing.
      const scoped = await runWizardUninstall(
        ["--yes", "--agent", "opencode"],
        home,
      );
      expect(scoped.status).toBe(0);
      expect(scoped.stdout).toContain("not configured for opencode");
      const commandFile =
        process.platform === "win32"
          ? "claude-gradiated.cmd"
          : "claude-gradiated";
      expect(existsSync(join(home, ".gradiated/bin", commandFile))).toBe(true);

      // Dry run reports the plan and leaves every file in place.
      const dry = await runWizardUninstall(["--dry-run"], home);
      expect(dry.status).toBe(0);
      expect(dry.stdout).toContain("Would remove");
      expect(dry.stdout).toContain("Dry run complete. No files were changed.");
      expect(existsSync(join(home, ".gradiated/bin", commandFile))).toBe(true);
      expect(
        JSON.parse(
          await readFile(join(home, ".gradiated/credentials.json"), "utf8"),
        ),
      ).toEqual({ api_key: API_KEY });
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  }, 30_000);
});
