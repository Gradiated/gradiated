import type { CatalogModel } from "../../src/catalog.js";

export const API_KEY = "grad_test_wizard_fixture_key_0000000000000000000";
export const ROTATED_KEY = "grad_test_wizard_rotated_key_000000000000000000";
export const REJECTED_KEY = "grad_wrong_key";

export const API_BASE_URL = "https://api.gradiated.com";

export const DEFAULT_MODEL = "z-ai/glm-5.3-flash";
export const SECOND_MODEL = "google/gemma-4-31b-it";

type LimitedModel = CatalogModel & {
  limit: NonNullable<CatalogModel["limit"]>;
};

export const GLM: LimitedModel = {
  id: DEFAULT_MODEL,
  name: "GLM-5.3 Flash",
  limit: { context: 1_048_576, output: 131_072 },
};

export const GEMMA: LimitedModel = {
  id: SECOND_MODEL,
  name: "Gemma 4 31B",
  limit: { context: 128_000, output: 8_192 },
};

export const CATALOG_MODELS = [GLM, GEMMA] as const;

export const MODEL_IDS = CATALOG_MODELS.map((model) => model.id);

const wireModel = ({ id, name, limit }: LimitedModel) => ({
  schema_version: "2.4",
  id,
  name,
  input_modalities: [
    {
      type: "text",
      supported_inputs: {
        max_context_length: { value: limit.context, unit: "token" },
      },
    },
  ],
  output_modalities: [
    {
      type: "text",
      max_length: { value: limit.output, unit: "token" },
      streaming: true,
      supported_parameters: {},
    },
  ],
});

export const FIXTURE_CATALOG = { data: CATALOG_MODELS.map(wireModel) };
