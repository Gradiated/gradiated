import type { JsonObject } from "../json.js";

export type StreamEvents = (JsonObject | string)[];

export interface RuntimeProfile {
  readonly path: string;
  readonly validate: (body: JsonObject, model: string) => void;
  readonly response: (body: JsonObject, cached?: number) => JsonObject;
  readonly events: (body: JsonObject, cached?: number) => StreamEvents;
}
