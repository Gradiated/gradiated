import { describe, expect, it } from "vitest";

import {
  createGemma4ModelConfiguration,
  gemma4ArtifactModelPath,
} from "../src/operations/gemma4-model.js";

describe("Gemma 4 model configuration", () => {
  it("uses a canonical public ID and a release date", () => {
    const model = createGemma4ModelConfiguration();

    expect(model.id).toBe(model.id.toLowerCase());
    expect(model.properties.released_at).toBe("2026-08-22T14:09:29.651Z");
    expect(gemma4ArtifactModelPath).toBe("google/gemma-4-31B-it");
  });
});
