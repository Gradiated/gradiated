import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { RequestTelemetrySchema } from "../src/request-telemetry.js";

const fixture = JSON.parse(
  readFileSync(
    new URL("./fixtures/request-telemetry.json", import.meta.url),
    "utf8",
  ),
);

describe("closed request metadata contract shared with Rust", () => {
  it("accepts the Rust extraction fixture without dropping any fields", () => {
    expect(RequestTelemetrySchema.parse(fixture)).toEqual(fixture);
  });

  it.each([
    { ...fixture, prompt: "private" },
    { ...fixture, task_type: "private-task" },
    { ...fixture, client: "private-user-agent" },
    { ...fixture, sampling: { ...fixture.sampling, seed: 123 } },
    {
      ...fixture,
      tool_schema: { ...fixture.tool_schema, properties: ["private-key"] },
    },
    { ...fixture, text_shape: { ...fixture.text_shape, scanned_bytes: 65537 } },
    { ...fixture, token_buckets: { input: "private" } },
  ])(
    "rejects open-ended, content-bearing, or out-of-bounds metadata",
    (value) => {
      expect(RequestTelemetrySchema.safeParse(value).success).toBe(false);
    },
  );
});
