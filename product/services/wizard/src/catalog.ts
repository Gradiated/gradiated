import type { HttpResponse } from "./http.js";
import { HttpError, request } from "./http.js";

export interface CatalogModel {
  id: string;
  name: string;
  contextLength: number | null;
  outputLength: number | null;
}

interface RawCatalogModel {
  id?: unknown;
  name?: unknown;
  input_modalities?: unknown;
  output_modalities?: unknown;
}

function tokenMeasure(value: unknown): number | null {
  if (
    value !== null &&
    typeof value === "object" &&
    typeof (value as { value?: unknown }).value === "number"
  ) {
    return (value as { value: number }).value;
  }
  return null;
}

function parseModel(raw: RawCatalogModel): CatalogModel | null {
  if (typeof raw.id !== "string" || raw.id.length === 0) return null;
  const inputModalities = Array.isArray(raw.input_modalities)
    ? (raw.input_modalities as Record<string, unknown>[])
    : [];
  const outputModalities = Array.isArray(raw.output_modalities)
    ? (raw.output_modalities as Record<string, unknown>[])
    : [];
  const textInput = inputModalities.find((entry) => entry.type === "text");
  const textOutput = outputModalities.find((entry) => entry.type === "text");
  const contextLength = tokenMeasure(
    (textInput?.supported_inputs as Record<string, unknown> | undefined)
      ?.max_context_length,
  );
  const outputLength = tokenMeasure(
    (textOutput as Record<string, unknown> | undefined)?.max_length,
  );
  return {
    id: raw.id,
    name:
      typeof raw.name === "string" && raw.name.length > 0 ? raw.name : raw.id,
    contextLength,
    outputLength,
  };
}

export async function fetchCatalog(
  inferenceBaseUrl: string,
  apiKey: string,
): Promise<CatalogModel[]> {
  const response: HttpResponse = await request(`${inferenceBaseUrl}/models`, {
    headers: { authorization: `Bearer ${apiKey}` },
  });
  const data = (response.body as { data?: unknown })?.data;
  if (!Array.isArray(data)) {
    throw new HttpError(
      response.status,
      "invalid_catalog",
      "The model catalog response was not understood.",
    );
  }
  const models = data
    .map((entry) => parseModel(entry as RawCatalogModel))
    .filter((model): model is CatalogModel => model !== null);
  if (models.length === 0) {
    throw new HttpError(
      response.status,
      "empty_catalog",
      "The model catalog is empty.",
    );
  }
  return models;
}
