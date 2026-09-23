export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type JsonObject = { [key: string]: JsonValue };

export const isJsonObject = (value: unknown): value is JsonObject =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const object = (value: JsonValue | undefined): JsonObject => {
  if (!isJsonObject(value)) {
    throw new Error(`expected a JSON object: ${JSON.stringify(value)}`);
  }

  return value;
};

export const text = (value: JsonValue | undefined): string => {
  if (typeof value !== "string") {
    throw new Error(`expected a JSON string: ${JSON.stringify(value)}`);
  }

  return value;
};

/** The JSON a typed value serializes to, as plain data a test can mutate. */
export const toJsonObject = (value: object): JsonObject =>
  object(JSON.parse(JSON.stringify(value)));
