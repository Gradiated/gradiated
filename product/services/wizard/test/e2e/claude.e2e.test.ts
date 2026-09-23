import { existsSync } from "node:fs";
import { readFile, rm, stat, symlink, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect } from "vitest";
import {
  CLAUDE_BIN,
  CLAUDE_COMMAND,
  CLAUDE_SCRIPT,
  onWindows,
} from "../support/agent-files.js";
import { API_KEY, DEFAULT_MODEL, SECOND_MODEL } from "../support/catalog.js";
import {
  expectSuccess,
  hasCommand,
  runClaudeWrapper,
  test as it,
  writeCommand,
} from "../support/wizard.js";

const INSTALL = { agent: "claude", model: DEFAULT_MODEL } as const;

const ECHO_GATEWAY_ENV =
  'echo "BASE_URL=$ANTHROPIC_BASE_URL"\n' +
  'echo "AUTH_TOKEN=$ANTHROPIC_AUTH_TOKEN"\n' +
  'echo "MODEL=$ANTHROPIC_MODEL"\n';

describe("Claude Code wrapper", () => {
  it("installs and uninstalls the wrapper without touching ~/.claude", async ({
    home,
    api,
    wizard,
  }) => {
    await writeFile(join(home, ".zshrc"), "export EDITOR=vim\n");

    const install = await wizard.install(INSTALL);
    expectSuccess(install);
    expect(install.stdout).toContain("claude-gradiated");
    expect(install.stdout).toMatch(/source |new terminal/);

    const wrapper = await readFile(join(home, CLAUDE_SCRIPT), "utf8");
    expect(wrapper).toContain(`const BASE_URL = "${api.baseUrl}"`);
    expect(wrapper).toContain(`"${DEFAULT_MODEL}"`);
    expect(wrapper).not.toContain(API_KEY);
    expect(wrapper).toContain("credentials.json");

    const command = join(home, CLAUDE_COMMAND);
    if (onWindows) {
      expect(await readFile(command, "utf8")).toContain("claude-gradiated.js");
    } else {
      expect((await stat(command)).mode & 0o111).toBe(0o111);
      expect(wrapper).toContain("#!/usr/bin/env node");
    }

    const zshrc = await readFile(join(home, ".zshrc"), "utf8");
    expect(zshrc).toContain("export EDITOR=vim");
    expect(zshrc).toContain("# >>> gradiated >>>");
    expect(zshrc).toContain(CLAUDE_BIN);
    expect(existsSync(join(home, ".claude"))).toBe(false);

    const uninstall = await wizard.uninstall();
    expectSuccess(uninstall);
    expect(uninstall.stdout).toContain("claude-gradiated wrapper");

    expect(existsSync(join(home, CLAUDE_BIN))).toBe(false);
    const cleaned = await readFile(join(home, ".zshrc"), "utf8");
    expect(cleaned).toContain("export EDITOR=vim");
    expect(cleaned).not.toContain("# >>> gradiated >>>");
    expect(existsSync(join(home, ".claude"))).toBe(false);
  });
});

// PATH lookup of an extensionless script is POSIX-only; the install test
// covers the Windows .cmd shim.
describe.skipIf(onWindows)("claude-gradiated command", () => {
  it("runs claude with the Gradiated gateway env", async ({
    paths,
    bin,
    api,
    wizard,
  }) => {
    await writeCommand(bin, "claude", ECHO_GATEWAY_ENV);
    expectSuccess(await wizard.install(INSTALL));

    const result = await runClaudeWrapper(paths, { pathPrepend: [bin] });

    expect(result.status, result.stderr).toBe(0);
    expect(result.stdout).toContain(`BASE_URL=${api.baseUrl}`);
    expect(result.stdout).toContain(`AUTH_TOKEN=${API_KEY}`);
    expect(result.stdout).toContain(`MODEL=${DEFAULT_MODEL}`);
  });

  it("keeps a model set with ANTHROPIC_MODEL for one run", async ({
    paths,
    bin,
    wizard,
  }) => {
    await writeCommand(bin, "claude", ECHO_GATEWAY_ENV);
    expectSuccess(await wizard.install(INSTALL));

    const result = await runClaudeWrapper(paths, {
      env: { ANTHROPIC_MODEL: SECOND_MODEL },
      pathPrepend: [bin],
    });

    expect(result.status, result.stderr).toBe(0);
    expect(result.stdout).toContain(`MODEL=${SECOND_MODEL}`);
    expect(result.stdout).toContain(`AUTH_TOKEN=${API_KEY}`);
  });

  it("stops when the credentials file is missing", async ({
    paths,
    wizard,
  }) => {
    expectSuccess(await wizard.install(INSTALL));
    await rm(paths.credentials);

    const result = await runClaudeWrapper(paths);

    expect(result.status).toBe(1);
    expect(result.stderr).toContain(
      `No Gradiated key found at ${paths.credentials}.`,
    );
  });

  it.for(["{}", "{not json", '{"api_key":""}'])(
    "stops when the credentials file holds %s",
    async (content, { paths, wizard }) => {
      expectSuccess(await wizard.install(INSTALL));
      await writeFile(paths.credentials, content);

      const result = await runClaudeWrapper(paths);

      expect(result.status).toBe(1);
      expect(result.stderr).toContain(
        "The Gradiated credential file has no API key.",
      );
    },
  );

  it("stops with an install hint when claude is not on PATH", async ({
    paths,
    bin,
    wizard,
  }) => {
    expectSuccess(await wizard.install(INSTALL));
    await symlink(process.execPath, join(bin, "node"));

    const result = await runClaudeWrapper(paths, { env: { PATH: bin } });

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("'claude' was not found on PATH.");
    expect(result.stderr).toContain("Install Claude Code first");
  });

  it.skipIf(!hasCommand("claude"))(
    "passes arguments through the wrapper to the real Claude Code",
    async ({ paths, wizard }) => {
      expectSuccess(await wizard.install(INSTALL));

      const result = await runClaudeWrapper(paths);

      expect(result.status, result.stderr).toBe(0);
      expect(result.stdout).toMatch(/\d+\.\d+/);
    },
    60_000,
  );
});
