import {
  ModelPropertiesInputSchema,
  OpenRouterModelIdSchema,
} from "@gradiated/contracts";
import {
  catalogModel,
  modelSupportedUses,
} from "@gradiated/contracts/model-catalog";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { requireOwnedModelNames } from "../src/catalog/apply.js";
import {
  catalogModels,
  legacyModels,
  trainingOnlyModels,
} from "../src/catalog/models/index.js";
import type { CatalogModelInput } from "../src/catalog/service.js";
import { createKev9bModelConfiguration } from "../src/catalog/models/kev-9b.js";

const prices = (model: { properties: unknown }) => {
  const properties = ModelPropertiesInputSchema.parse(model.properties);

  return {
    input: properties.input_modalities.flatMap((modality) => modality.pricing),
    output: properties.output_modalities.flatMap(
      (modality) => modality.pricing,
    ),
  };
};

describe("model configurations", () => {
  it.each([...catalogModels, ...legacyModels])(
    "$id is a valid catalog model",
    (model) => {
      const properties = ModelPropertiesInputSchema.parse(model.properties);

      expect(model.id).toBe(model.id.toLowerCase());
      for (const output of properties.output_modalities) {
        expect(output.default_length?.value ?? 0).toBeLessThanOrEqual(
          output.max_length.value,
        );
      }
      const { input, output } = prices(model);
      for (const { cost } of [...input, ...output]) {
        expect(Number.isSafeInteger(cost) && cost >= 0).toBe(true);
      }
    },
  );

  it.each([...catalogModels, ...legacyModels])(
    "$id keeps an owner's model under its slug and out of the public catalog",
    (model: CatalogModelInput) => {
      expect(() => requireOwnedModelNames(model)).not.toThrow();
      if (model.owner) expect(catalogModel(model.id)).toBeUndefined();
    },
  );

  it("names an owned model under its owner's slug", () => {
    const owned = (id: string, aliases: string[] = []) => ({
      id,
      aliases,
      owner: { organizationSlug: "posthog" },
      type: "decision",
    });

    expect(() =>
      requireOwnedModelNames(
        owned("posthog/jeeves", ["posthog/jevk5"]) as CatalogModelInput,
      ),
    ).not.toThrow();
    for (const definition of [
      owned("jeeves"),
      owned("posthogx/jeeves"),
      owned("posthog/"),
      owned("posthog/jeeves", ["jeeves"]),
      // A further segment could be a private version name.
      owned("posthog/support/v1"),
      owned("posthog/jeeves", ["posthog/support/v1"]),
      // The gateway lowercases requests, so this could never be called.
      owned("posthog/Jeeves"),
    ])
      expect(() =>
        requireOwnedModelNames(definition as CatalogModelInput),
      ).toThrow("must be named");
  });

  const pinnedPrices: Record<string, { input: number[]; output: number[] }> = {
    "deepseek/deepseek-v4.1-flash-1017": {
      input: [300, 7],
      output: [1_200, 1_200],
    },
    "deepseek/deepseek-v4.1-flash": { input: [300, 7], output: [1_200, 1_200] },
    "z-ai/glm-5.3-flash": { input: [150, 30], output: [500, 500] },
    "dealignai/glm-5.3-flash-uncensored": {
      input: [150, 15],
      output: [450, 450],
    },
    "dealignai/glm-5.3-flash-uncensored-nvfp4": {
      input: [150, 15],
      output: [450, 450],
    },
    "jaredpalmer/kev-9b": { input: [30, 6], output: [0] },
    "gradiated/linden-1": { input: [20, 20], output: [0] },
    "perplexity-ai/pplx-decider-v1.2": { input: [20, 20], output: [0] },
    "moonshotai/kimi-k3.1-pro": {
      input: [1_600, 160],
      output: [8_000, 8_000],
    },
    "kimi-k3.1-pro-cyber": {
      input: [1_000, 100],
      output: [5_000, 5_000],
    },
    "yetalabs/kimi-k3.1-pro-abliterated": {
      input: [1_000, 100],
      output: [5_000, 5_000],
    },
    "z-ai/glm-5.3": { input: [1_400, 260], output: [4_400, 4_400] },
    "posthog/jeeves": { input: [20, 20], output: [0] },
    "posthog/jevk5": { input: [20, 20], output: [0] },
  };

  it.each([...catalogModels, ...legacyModels])(
    "pins the nano-USD prices of $id",
    (model) => {
      const pinned = prices(model);

      expect({
        input: pinned.input.map(({ cost }) => cost),
        output: pinned.output.map(({ cost }) => cost),
      }).toEqual(pinnedPrices[model.id]);
    },
  );

  it("maps only verified exact models to OpenRouter", () => {
    const mappings = Object.fromEntries(
      [...catalogModels, ...legacyModels].map((model) => [
        model.id,
        "openrouterModelId" in model ? model.openrouterModelId : undefined,
      ]),
    );

    expect(mappings).toEqual({
      "deepseek/deepseek-v4.1-flash-1017": "deepseek/deepseek-v4.1-flash-1017",
      "deepseek/deepseek-v4.1-flash": "deepseek/deepseek-v4.1-flash",
      "z-ai/glm-5.3-flash": "z-ai/glm-5.3-flash",
      "dealignai/glm-5.3-flash-uncensored": null,
      "dealignai/glm-5.3-flash-uncensored-nvfp4": null,
      "jaredpalmer/kev-9b": undefined,
      "gradiated/linden-1": null,
      "perplexity-ai/pplx-decider-v1.2": null,
      "moonshotai/kimi-k3.1-pro": "moonshotai/kimi-k3.1-pro",
      "kimi-k3.1-pro-cyber": null,
      "yetalabs/kimi-k3.1-pro-abliterated": null,
      "z-ai/glm-5.3": "z-ai/glm-5.3",
      "posthog/jeeves": null,
      "posthog/jevk5": null,
    });
    for (const mapping of Object.values(mappings)) {
      if (typeof mapping === "string") OpenRouterModelIdSchema.parse(mapping);
    }
  });

  it("rejects an OpenRouter variant or moving alias as a mapping", () => {
    for (const mapping of [
      "z-ai/glm-5.3-flash:free",
      "~z-ai/glm-latest",
      "Z-AI/GLM-5.3-Flash",
      "glm-5.3-flash",
    ]) {
      expect(OpenRouterModelIdSchema.safeParse(mapping).success).toBe(false);
    }
  });

  it("retains Kev 9B history while retiring it from published catalogs", () => {
    expect(createKev9bModelConfiguration().status).toBe("retired");
    expect(createKev9bModelConfiguration().type).toBe("decision");
    const [output] =
      createKev9bModelConfiguration().properties.output_modalities;

    expect(output).toMatchObject({
      streaming: false,
      supported_parameters: {},
      max_length: { value: 1 },
      pricing: [{ type: "completion", cost: 0 }],
    });
  });

  it("classifies the generation models as chat", () => {
    expect(catalogModels.map((model) => model.type)).toEqual([
      "decision",
      "decision",
      "chat",
      "chat",
      "chat",
      "decision",
      "chat",
      "chat",
      "chat",
      "decision",
      "decision",
    ]);
  });

  it("advertises the GLM effort parameter so the gateway forwards it to the runtime", () => {
    const glm = catalogModels.find(
      (model) => model.id === "z-ai/glm-5.3-flash",
    );
    const properties = ModelPropertiesInputSchema.parse(glm?.properties);

    expect(glm?.status).toBe("available");

    expect(
      properties.output_modalities[0]?.supported_parameters.reasoning_effort,
    ).toEqual({
      type: "enum",
      values: ["low", "high", "max"],
    });
  });
});

it("offers Kimi with exact OpenRouter capacity and its reasoning contract", () => {
  const model = catalogModels.find(
    (item) => item.id === "moonshotai/kimi-k3.1-pro",
  );

  expect(model?.status).toBe("available");
  expect(
    model && "openrouterModelId" in model ? model.openrouterModelId : undefined,
  ).toBe("moonshotai/kimi-k3.1-pro");
  expect(model && "tokenizer" in model ? model.tokenizer : undefined).toEqual({
    path: "moonshotai/Kimi-K3.1-Pro",
    revision: "d9e99b0792a5e93b78ea9bea62a68167e36ddd9e",
  });
  expect(model?.properties).toMatchObject({
    hugging_face_id: "moonshotai/Kimi-K3.1-Pro",
    quantization: "mxfp4",
    input_modalities: [{ type: "text" }],
    reasoning: {
      supported_efforts: ["low", "high", "max"],
      default_effort: "max",
    },
    output_modalities: [
      {
        supported_parameters: {
          reasoning_effort: { type: "enum", values: ["low", "high", "max"] },
        },
      },
    ],
  });
});

it("offers YetaLabs' Kimi K3.1 Pro Cyber without OpenRouter fallback and aliases NanoGPT's ID", () => {
  const model = catalogModels.find((item) => item.id === "kimi-k3.1-pro-cyber");
  const retired = legacyModels.find(
    (item) => item.id === "yetalabs/kimi-k3.1-pro-abliterated",
  );

  expect(model?.status).toBe("available");
  expect(model?.name).toBe("Kimi K3.1 Pro Cyber");
  expect(model && "aliases" in model ? model.aliases : undefined).toEqual([
    "yetalabs/kimi-k3.1-pro-abliterated",
  ]);
  expect(retired?.status).toBe("retired");
  expect(
    model && "openrouterModelId" in model ? model.openrouterModelId : undefined,
  ).toBeNull();
  expect(model && "tokenizer" in model ? model.tokenizer : undefined).toEqual({
    path: "yetalabs/Kimi-K3.1-Pro-abliterated",
    revision: "0911ef0765f49d26dfa25bb0d071f29463f8000b",
  });
  expect(model?.properties).toMatchObject({
    hugging_face_id: "yetalabs/Kimi-K3.1-Pro-abliterated",
    quantization: "mxfp4",
    tokenizer: "Kimi K3.1",
    input_modalities: [{ type: "text" }],
    reasoning: {
      supported_efforts: ["low", "high", "max"],
      default_effort: "max",
    },
  });
});

it("serves DeepSeek V4.1 Flash 1017 on our capacity from its native weights", () => {
  const model = catalogModels.find(
    (item) => item.id === "deepseek/deepseek-v4.1-flash-1017",
  );

  expect(model?.status).toBe("available");
  expect(model?.name).toBe("DeepSeek V4.1 Flash 1017");
  expect(model?.properties).toMatchObject({
    hugging_face_id: "deepseek-ai/DeepSeek-V4.1-Flash-1017",
    quantization: "mxfp4",
    tokenizer: "DeepSeek V4.1",
    input_modalities: [
      { supported_inputs: { max_context_length: { value: 1_048_576 } } },
    ],
  });
});

it("retires original DeepSeek Flash and keeps 1017 as an explicit selection", () => {
  const originalId = "deepseek/deepseek-v4.1-flash";
  const retired = legacyModels.find((model) => model.id === originalId);
  const replacement = catalogModels.find(
    (model) => model.id === "deepseek/deepseek-v4.1-flash-1017",
  );

  expect(catalogModels.some((model) => model.id === originalId)).toBe(false);
  expect(retired?.status).toBe("retired");
  expect(replacement?.status).toBe("available");
});

it("identifies Dealign weights separately from the stock training base", () => {
  const model = catalogModels.find(
    (item) => item.id === "dealignai/glm-5.3-flash-uncensored",
  );

  expect(model?.status).toBe("available");
  expect(model?.properties).toMatchObject({
    hugging_face_id: "dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4",
    quantization: "nvfp4",
  });
});

it("serves text-only linden-1 with no external provider or training capability", () => {
  const model = catalogModels.find((item) => item.id === "gradiated/linden-1");
  expect(model?.status).toBe("available");
  expect(
    model && "openrouterModelId" in model ? model.openrouterModelId : undefined,
  ).toBeNull();
  expect(model?.type).toBe("decision");
  expect(modelSupportedUses("gradiated/linden-1")).toEqual(["serving"]);
  expect(model?.properties).toMatchObject({
    hugging_face_id: "gradiated/linden-1",
    quantization: "bf16",
    tokenizer: "Gemma",
  });
});

it("retires Decider v1.2 but keeps its historical model ID", () => {
  const model = catalogModels.find(
    (item) => item.id === "perplexity-ai/pplx-decider-v1.2",
  );
  expect(model?.status).toBe("retired");
  expect(
    model && "openrouterModelId" in model ? model.openrouterModelId : undefined,
  ).toBeNull();
  expect(model?.type).toBe("decision");
  expect(modelSupportedUses("perplexity-ai/pplx-decider-v1.2")).toEqual([
    "serving",
  ]);
  expect(model?.properties.quantization).toBe("int4");
});

it("declares the type every pinned runtime's release protocol serves", () => {
  // A deployment whose protocol doesn't match its model's type is withdrawn,
  // so a mismatch here would take that runtime out of service.
  const runtimes = Object.values(
    JSON.parse(
      readFileSync(
        new URL("../../../inference/gpu/runtimes.json", import.meta.url),
        "utf8",
      ),
    ) as Record<string, { model_id: string; release: { protocol?: string } }>,
  );
  const definitions = new Map(
    [...catalogModels, ...legacyModels].map((model) => [model.id, model]),
  );
  let checked = 0;
  for (const runtime of runtimes) {
    const definition = definitions.get(runtime.model_id);
    if (!definition) continue;
    checked += 1;
    expect(
      runtime.release.protocol === "system_one" ? "decision" : "chat",
      runtime.model_id,
    ).toBe(definition.type);
  }
  expect(checked).toBeGreaterThan(0);
});

it("backfills each existing model with the type its definition declares", () => {
  // Migration 0036 types existing rows from this list alone; a definition that
  // disagreed would be retired as type_changed on the first catalog pass.
  const migration = readFileSync(
    new URL("../migrations/0036_organization_models.sql", import.meta.url),
    "utf8",
  );
  const list = /WHEN "id" IN \(([^)]*)\)/.exec(migration)?.[1] ?? "";
  const backfilled = [...list.matchAll(/'([^']+)'/g)].map((match) => match[1]);

  expect(backfilled.sort()).toEqual(
    // Owned models are new rows, written with their type.
    [...catalogModels, ...legacyModels, ...trainingOnlyModels()]
      .filter((model) => model.type === "decision" && !("owner" in model))
      .map((model) => model.id)
      .sort(),
  );
});

it.each([
  ["posthog/jeeves", "available"],
  ["posthog/jevk5", "available"],
] as const)("defines %s as PostHog's own decision model (%s)", (id, status) => {
  const model: CatalogModelInput | undefined = catalogModels.find(
    (item) => item.id === id,
  );

  expect(model).toMatchObject({
    owner: { organizationSlug: "posthog" },
    type: "decision",
    status,
    openrouterModelId: null,
    properties: {
      tokenizer: "Qwen",
      input_modalities: [
        { supported_inputs: { max_prompt_length: { value: 16_384 } } },
      ],
      output_modalities: [{ streaming: false, max_length: { value: 1 } }],
    },
  });
  expect(model?.id.startsWith("posthog/")).toBe(true);
  expect(model?.aliases ?? []).toEqual([]);
  expect(() => requireOwnedModelNames(model!)).not.toThrow();
  // Never compiled into the public catalog, so never published or listed.
  expect(catalogModel(id)).toBeUndefined();
});
