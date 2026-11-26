import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

import { MODEL_CATALOG } from "../../packages/contracts/src/model-catalog";
import { GPT_MODEL, OPUS_MODEL, SONNET_MODEL } from "../src/docs/models";

const require = createRequire(import.meta.url);
const cjsModels = require("../scripts/docs-models.cjs") as {
  OPUS_MODEL: string;
  SONNET_MODEL: string;
  GPT_MODEL: string;
  substituteDocModels: (value: string) => string;
};

describe("docs model catalog constants", () => {
  const catalogIds = new Set<string>(MODEL_CATALOG.map((m) => m.id));

  it("pulls OPUS_MODEL, SONNET_MODEL, and GPT_MODEL from MODEL_CATALOG", () => {
    expect(catalogIds.has(OPUS_MODEL)).toBe(true);
    expect(catalogIds.has(SONNET_MODEL)).toBe(true);
    expect(catalogIds.has(GPT_MODEL)).toBe(true);
    expect(OPUS_MODEL).toMatch(/^anthropic\/claude-opus-/);
    expect(SONNET_MODEL).toMatch(/^anthropic\/claude-sonnet-/);
    expect(GPT_MODEL).toMatch(/^openai\/gpt-/);
  });

  it("stays in sync with scripts/docs-models.cjs", () => {
    expect(cjsModels.OPUS_MODEL).toBe(OPUS_MODEL);
    expect(cjsModels.SONNET_MODEL).toBe(SONNET_MODEL);
    expect(cjsModels.GPT_MODEL).toBe(GPT_MODEL);
    expect(cjsModels.substituteDocModels("{{OPUS_MODEL}} / {{SONNET_MODEL}}")).toBe(
      `${OPUS_MODEL} / ${SONNET_MODEL}`,
    );
  });
});
