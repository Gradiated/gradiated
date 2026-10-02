import { expect, it, vi } from "vitest";
import { createEvaluationModelValidator } from "../src/catalog/evaluation-models.js";
import { createExternalModelCatalog } from "../src/catalog/external-models.js";

it("validates provider selections against the live catalog without loading it for hosted choices", async () => {
  const load = vi
    .fn<ReturnType<typeof createExternalModelCatalog>>()
    .mockResolvedValue({
      data: [{ id: "openai/gpt-4.1-mini", status: "available" }],
    } as Awaited<ReturnType<ReturnType<typeof createExternalModelCatalog>>>);
  const validate = createEvaluationModelValidator(load, {
    listModels: vi
      .fn()
      .mockResolvedValue([{ id: "Qwen/Qwen3-0.6B", status: "available" }]),
  });
  await validate("Qwen/Qwen3-0.6B");
  expect(load).not.toHaveBeenCalled();
  await validate("openai/gpt-4.1-mini");
  await expect(validate("openai/unavailable")).rejects.toMatchObject({
    code: "not_found",
  });
});

it.each(["unavailable", "retired", "missing"])(
  "rejects %s hosted models without loading external models",
  async (status) => {
    const load = vi.fn<ReturnType<typeof createExternalModelCatalog>>();
    const validate = createEvaluationModelValidator(load, {
      listModels: vi
        .fn()
        .mockResolvedValue(
          status === "missing" ? [] : [{ id: "z-ai/glm-5.3-flash", status }],
        ),
    });
    await expect(validate("z-ai/glm-5.3-flash")).rejects.toMatchObject({
      code: "not_found",
    });
    expect(load).not.toHaveBeenCalled();
  },
);
