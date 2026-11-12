import { expect, it } from "vitest";
import {
  DEFAULT_COMPARISON_MODEL,
  DEFAULT_EVALUATION_JUDGE,
  DEFAULT_TRAINING_BASE,
  catalogModel,
  TRAINING_BASE_MODELS,
} from "../src/model-catalog.js";
import { trainingRecipeForModel } from "../src/training-recipe.js";

it("pins every selectable training model and preserves rank two", () => {
  for (const model of TRAINING_BASE_MODELS) {
    expect(trainingRecipeForModel(model.id)).toMatchObject({
      revision: expect.stringMatching(/^[0-9a-f]{40}$/),
      rank: 2,
    });
  }
  expect(
    trainingRecipeForModel("deepseek/deepseek-v4.1-flash-1017"),
  ).toBeNull();
  expect(trainingRecipeForModel("deepseek/deepseek-v4.1-flash")).toBeNull();
  expect(trainingRecipeForModel("jaredpalmer/kev-9b")).toBeNull();
});

it("keeps retired GLM recipe metadata without enabling new training", () => {
  expect(trainingRecipeForModel(DEFAULT_TRAINING_BASE)).toBeNull();
  expect(catalogModel(DEFAULT_TRAINING_BASE)).toMatchObject({
    training: {
      model: "zai-org/GLM-5.3-Flash-BF16",
      model_task: "image_text_to_text",
      gpu_count: 4,
      attention: "eager",
      gradient_checkpointing: true,
    },
  });
  expect(DEFAULT_COMPARISON_MODEL).toBe("openai/gpt-6.1-sol");
  expect(DEFAULT_EVALUATION_JUDGE).toBe("openai/gpt-6.1-sol");
});
