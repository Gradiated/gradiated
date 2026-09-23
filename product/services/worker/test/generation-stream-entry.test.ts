import { describe, expect, it } from "vitest";
import { ZodError } from "zod";

import { parseGenerationStreamEntry } from "../src/generation-stream-entry.js";
import {
  generationSettled,
  mispricedFields,
  streamFields,
} from "./support/generation.js";

const event = generationSettled();
const entry = { id: "1786797061000-4", message: streamFields(event) };

describe("generation stream entries", () => {
  it("validates the complete stream event and derives its slot", () => {
    expect(parseGenerationStreamEntry(entry)).toEqual({
      event,
      slotId: "20260815T123000Z-300s-v1",
    });
  });

  it.each([
    ["an extra field", { ...entry.message, prompt: "secret" }],
    ["a missing field", { generation_id: event.generation_id }],
    ["an empty field", { ...entry.message, generation_id: "" }],
  ])("rejects an entry with %s", (_case, message) => {
    expect(() => parseGenerationStreamEntry({ ...entry, message })).toThrow(
      expect.objectContaining({ code: "EINVALID_STREAM_ENTRY" }),
    );
  });

  it("rejects properties that are not JSON", () => {
    const message = { ...entry.message, properties: "{not json" };

    expect(() => parseGenerationStreamEntry({ ...entry, message })).toThrow(
      expect.objectContaining({ code: "EINVALID_GENERATION_JSON" }),
    );
  });

  it.each([
    ["an invalid event", { ...entry.message, properties: JSON.stringify({}) }],
    ["a charge that differs from its components", mispricedFields(event)],
  ])(
    "rejects %s and keeps the validation error as the cause",
    (_case, message) => {
      expect(() => parseGenerationStreamEntry({ ...entry, message })).toThrow(
        expect.objectContaining({
          code: "EINVALID_GENERATION_EVENT",
          cause: expect.any(ZodError),
        }),
      );
    },
  );

  it("rejects an invalid stream ID", () => {
    expect(() => parseGenerationStreamEntry({ ...entry, id: "x" })).toThrow(
      expect.objectContaining({ code: "EINVALID_STREAM_ID" }),
    );
  });
});
