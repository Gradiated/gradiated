import { readFileSync } from "node:fs";

import { SystemOneRequestSchema } from "@gradiated/contracts";
import { z } from "@hono/zod-openapi";
import { describe, expect, it } from "vitest";

import { createOpenApiDocument } from "../src/openapi.js";
import { createTestApp } from "./support.js";

const ParityFixturesSchema = z.array(
  z.object({ name: z.string(), request: z.unknown() }),
);

describe("SystemOne documentation and Rust parity fixtures", () => {
  it("registers a bearer-secured OpenAPI operation without a TypeScript handler", async () => {
    const document = createOpenApiDocument();
    const operation = document.paths?.["/v1/systemone"]?.post;
    expect(operation?.security).toEqual([
      { InferenceBearer: [] },
      { InferenceApiKey: [] },
    ]);
    expect(document.components?.securitySchemes?.InferenceBearer).toMatchObject(
      { type: "http", scheme: "bearer" },
    );
    expect(operation?.requestBody).toMatchObject({
      required: true,
      content: {
        "application/json": {
          schema: { $ref: "#/components/schemas/SystemOneRequest" },
        },
      },
    });
    expect(operation?.responses?.[200]).toMatchObject({
      content: {
        "application/json": {
          schema: { $ref: "#/components/schemas/SystemOneResponse" },
        },
      },
    });
    expect(
      (await createTestApp().request("/v1/systemone", { method: "POST" }))
        .status,
    ).toBe(404);
  });

  for (const [kind, accepted] of [
    ["accepted", true],
    ["rejected", false],
  ] as const) {
    const fixtures = ParityFixturesSchema.parse(
      JSON.parse(
        readFileSync(
          new URL(
            `../../gateway/test/fixtures/systemone-request.${kind}.json`,
            import.meta.url,
          ),
          "utf8",
        ),
      ),
    );
    it.each(fixtures)(`${kind} parity fixture: $name`, ({ request: value }) => {
      expect(SystemOneRequestSchema.safeParse(value).success).toBe(accepted);
    });
  }
});
