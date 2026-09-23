import { describe, expect, it } from "vitest";

import { GenerationSettledSchema } from "../src/index.js";

const generationSettled = (
  properties: Record<string, unknown>,
): Record<string, unknown> => ({
  generation_id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774",
  properties: {
    external_id: null,
    organization_id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c775",
    workspace_id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c776",
    api_key_id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c777",
    model_id: "gradiated/small",
    served_release_digest: `sha256:${"a".repeat(64)}`,
    status: "succeeded",
    streamed: false,
    pricing: { schema_version: 1, components: [] },
    usage: {
      charge: 0,
      input_tokens: 1,
      cached_input_tokens: 0,
      cache_write_tokens: 0,
      output_tokens: 1,
      reasoning_tokens: 0,
    },
    outcome: {
      finish_reason: "stop",
      error_code: null,
      usable_output_delivered: true,
      cancellation_owner: null,
    },
    timing: {
      received_at: "2026-01-01T00:00:00.000Z",
      started_at: "2026-01-01T00:00:00.100Z",
      first_token_at: "2026-01-01T00:00:00.200Z",
      completed_at: "2026-01-01T00:00:01.000Z",
    },
    ...properties,
  },
});

describe("GenerationSettledSchema", () => {
  it.each([
    ["version 1 without a service tier", { event_schema_version: 1 }],
    [
      "version 2 with a service tier",
      { event_schema_version: 2, service_tier: "flex" },
    ],
  ])("accepts %s", (_, properties) => {
    expect(
      GenerationSettledSchema.safeParse(generationSettled(properties)).success,
    ).toBe(true);
  });

  it("rejects version 1 with a service tier", () => {
    const result = GenerationSettledSchema.safeParse(
      generationSettled({ event_schema_version: 1, service_tier: "default" }),
    );

    expect(result.error?.issues).toMatchObject([
      {
        code: "unrecognized_keys",
        keys: ["service_tier"],
        path: ["properties"],
      },
    ]);
  });

  it("rejects version 2 without a service tier", () => {
    const result = GenerationSettledSchema.safeParse(
      generationSettled({ event_schema_version: 2 }),
    );

    expect(result.error?.issues).toMatchObject([
      { path: ["properties", "service_tier"] },
    ]);
  });
});
