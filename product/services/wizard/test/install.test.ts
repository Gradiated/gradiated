import { beforeEach, describe, expect, vi } from "vitest";
import { isOnPath } from "../src/agents/detect.js";
import type { InstallOptions } from "../src/arguments.js";
import type { Catalog } from "../src/catalog.js";
import { runInstall } from "../src/commands/install.js";
import { resolveKey, validateKey } from "../src/key.js";
import * as ui from "../src/ui.js";
import {
  API_KEY,
  DEFAULT_MODEL,
  GEMMA,
  GLM,
  SECOND_MODEL,
} from "./support/catalog.js";
import { test as it } from "./support/home.js";

vi.mock("../src/ui.js", () => import("./support/ui-stub.js"));
vi.mock("../src/agents/detect.js", () => ({ isOnPath: vi.fn() }));
vi.mock("../src/key.js", () => ({
  resolveKey: vi.fn(),
  validateKey: vi.fn(),
}));

const dryRun = (overrides: Partial<InstallOptions>): InstallOptions => ({
  credential: { kind: "key", key: API_KEY },
  agent: "codex",
  model: undefined,
  apiBaseUrl: "https://api.example.com",
  dryRun: true,
  interactive: true,
  ...overrides,
});

const serveCatalog = (models: Catalog): void => {
  vi.mocked(validateKey).mockResolvedValue({ apiKey: API_KEY, models });
};

const previews = (): string =>
  vi
    .mocked(ui.note)
    .mock.calls.map(([body]) => body)
    .join("\n");

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(isOnPath).mockReturnValue(true);
  vi.mocked(resolveKey).mockResolvedValue(API_KEY);
  serveCatalog([GLM, GEMMA]);
});

describe("install", () => {
  it("asks which model to use when the catalog has several", async ({
    paths,
  }) => {
    vi.mocked(ui.selectOption).mockResolvedValue(GEMMA);

    await runInstall(dryRun({}), paths);

    expect(vi.mocked(ui.selectOption).mock.calls[0]?.[1]).toEqual([
      { value: GLM, label: GLM.name, hint: DEFAULT_MODEL },
      { value: GEMMA, label: GEMMA.name, hint: SECOND_MODEL },
    ]);
    expect(previews()).toContain(`model = "${SECOND_MODEL}"`);
  });

  it("uses the only catalog model without asking", async ({ paths }) => {
    serveCatalog([GEMMA]);

    await runInstall(dryRun({}), paths);

    expect(ui.selectOption).not.toHaveBeenCalled();
    expect(previews()).toContain(`model = "${SECOND_MODEL}"`);
  });

  it("configures a requested Claude Code that is not on PATH, with a warning", async ({
    paths,
  }) => {
    vi.mocked(isOnPath).mockReturnValue(false);

    await runInstall(dryRun({ agent: "claude", interactive: false }), paths);

    expect(ui.warn).toHaveBeenCalledWith(
      "'claude' was not found on PATH. Configuring Claude Code anyway; install it before use.",
    );
    expect(vi.mocked(ui.note).mock.calls[0]?.[1]).toBe("Claude Code wrapper");
  });

  it("does not offer account creation in a dry run", async ({ paths }) => {
    await runInstall(dryRun({ interactive: false }), paths);

    expect(resolveKey).toHaveBeenCalledWith(
      { kind: "key", key: API_KEY },
      expect.objectContaining({ offerAccount: false }),
    );
    expect(ui.outro).toHaveBeenCalledWith(
      "Dry run complete. No files were changed.",
    );
  });
});
