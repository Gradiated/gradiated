import { ModelPropertiesInputSchema } from "@gradiated/contracts";
import { describe, expect, it } from "vitest";
import { createDeepseekV41FlashSeedModel } from "../scripts/seed-models.js";

describe("DeepSeek local catalog fixture", () => {
  it("validates the catalog properties and nano-USD prices", () => {
    const model = createDeepseekV41FlashSeedModel();
    expect(model.id).toBe("deepseek/deepseek-v4.1-flash");
    const properties = ModelPropertiesInputSchema.parse(model.properties);
    expect(properties.hugging_face_id).toBe("deepseek-ai/DeepSeek-V4.1-Flash");
    expect(
      properties.input_modalities[0]!.pricing.map((entry) => entry.cost),
    ).toEqual([300, 6]);
    expect(
      properties.output_modalities[0]!.pricing.map((entry) => entry.cost),
    ).toEqual([1200, 1200]);
  });
});
