import { WizardError } from "./errors.js";
import { isRecord } from "./guards.js";
import { request } from "./http.js";

export interface CatalogModel {
  id: string;
  name: string;
  limit: { context: number; output: number } | null;
}

export type Catalog = readonly [CatalogModel, ...CatalogModel[]];

const textModality = (modalities: unknown): Record<string, unknown> => {
  const text = Array.isArray(modalities)
    ? modalities.find((entry) => isRecord(entry) && entry.type === "text")
    : undefined;

  return isRecord(text) ? text : {};
};

const tokenCount = (measure: unknown): number | null =>
  isRecord(measure) && typeof measure.value === "number" ? measure.value : null;

const parseLimit = (raw: Record<string, unknown>): CatalogModel["limit"] => {
  const input = textModality(raw.input_modalities);
  const output = textModality(raw.output_modalities);
  const context = tokenCount(
    isRecord(input.supported_inputs)
      ? input.supported_inputs.max_context_length
      : undefined,
  );
  const maxOutput = tokenCount(output.max_length);

  return context === null || maxOutput === null
    ? null
    : { context, output: maxOutput };
};

const parseModel = (raw: unknown): CatalogModel | null => {
  if (!isRecord(raw) || typeof raw.id !== "string" || raw.id.length === 0) {
    return null;
  }

  return {
    id: raw.id,
    name:
      typeof raw.name === "string" && raw.name.length > 0 ? raw.name : raw.id,
    limit: parseLimit(raw),
  };
};

export const fetchCatalog = async (
  apiBaseUrl: string,
  apiKey: string,
): Promise<Catalog> => {
  const { body } = await request(`${apiBaseUrl}/models`, {
    headers: { authorization: `Bearer ${apiKey}` },
  });

  if (!isRecord(body) || !Array.isArray(body.data)) {
    throw new WizardError("The model catalog response was not understood.");
  }

  const [first, ...rest] = body.data
    .map(parseModel)
    .filter((model) => model !== null);
  if (first === undefined) {
    throw new WizardError("The model catalog is empty.");
  }

  return [first, ...rest];
};
