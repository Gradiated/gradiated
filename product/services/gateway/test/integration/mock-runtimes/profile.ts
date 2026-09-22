export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };

export interface RuntimeProfile {
  readonly PATH: string;
  readonly validate: (body: JsonObject, model: string) => void;
  readonly response: (body: JsonObject, cached?: number) => JsonObject;
  readonly events: (
    body: JsonObject,
    cached?: number,
  ) => (JsonObject | string)[];
}
