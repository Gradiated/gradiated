import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect } from "vitest";
import { onWindows } from "../support/agent-files.js";
import { expectSuccess, test as it } from "../support/wizard.js";

describe("command line", () => {
  it.skipIf(onWindows)(
    "previews every agent with --dry-run and writes no files",
    async ({ home, wizard }) => {
      const result = await wizard.install({ dryRun: true });

      expectSuccess(result);
      expect(result.stdout).toContain("Would write this OpenCode provider");
      expect(result.stdout).toContain("[model_providers.gradiated]");
      expect(result.stdout).toContain('model_provider = "gradiated"');
      expect(result.stdout).toContain("Claude Code wrapper");
      expect(result.stdout).toContain(
        "Dry run complete. No files were changed.",
      );
      expect(await readdir(home)).toEqual([]);
    },
  );

  it("prints the package version", async ({ wizard }) => {
    const manifest: unknown = JSON.parse(
      await readFile(join(import.meta.dirname, "../../package.json"), "utf8"),
    );

    const result = await wizard.run(["--version"]);

    expectSuccess(result);
    expect(manifest).toHaveProperty("version", result.stdout.trim());
  });
});
