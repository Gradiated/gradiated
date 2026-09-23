import { readdir } from "node:fs/promises";
import { describe, expect } from "vitest";
import { API_KEY, MODEL_IDS } from "../support/catalog.js";
import { expectFailure, expectSuccess, test as it } from "../support/wizard.js";

describe("wizard failures", () => {
  it("rejects a model outside the catalog and writes no agent config", async ({
    home,
    wizard,
  }) => {
    const result = await wizard.install({
      agent: "claude",
      model: "unknown/model",
    });

    expectFailure(result, 'Model "unknown/model" is not in the catalog');
    expect(result.stdout).toContain(`Available: ${MODEL_IDS.join(", ")}`);
    expect(await readdir(home)).toEqual([]);
  });

  it("fails when the requested agent is not on PATH", async ({
    home,
    bin,
    wizard,
  }) => {
    const result = await wizard.install({
      agent: "opencode",
      env: { PATH: bin },
    });

    expectFailure(result, "opencode is not installed or is not on PATH");
    expect(await readdir(home)).toEqual([]);
  });

  it("ends cleanly when no supported agent is on PATH", async ({
    home,
    bin,
    wizard,
  }) => {
    const result = await wizard.install({ env: { PATH: bin } });

    expectSuccess(result);
    expect(result.stdout).toContain("No supported coding agent was found");
    expect(await readdir(home)).toEqual([]);
  });

  it("reports a catalog outage as a service failure, not a rejected key", async ({
    home,
    unavailableApi,
    wizard,
  }) => {
    const result = await wizard.install({
      agent: "claude",
      baseUrl: unavailableApi.baseUrl,
    });

    expectFailure(
      result,
      "Could not fetch the model catalog (503): The catalog is temporarily unavailable. (unavailable)",
    );
    expect(result.stdout).not.toContain("API key invalid");
    expect(await readdir(home)).toEqual([]);
  });

  it("rejects an unknown flag before writing anything", async ({
    home,
    wizard,
  }) => {
    const result = await wizard.run([
      "--yes",
      "--agnet",
      "claude",
      "--key",
      API_KEY,
    ]);

    expectFailure(result, "--agnet");
    expect(await readdir(home)).toEqual([]);
  });
});
