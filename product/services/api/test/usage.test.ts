import { describe, expect, it } from "vitest";

import type { UsageService } from "@gradiated/control";

import { createApp } from "../src/app.js";
import { authenticated, organizationId, user, workspaceId } from "./support.js";

const from = "2026-08-01T00:00:00.000Z";
const to = "2026-08-21T00:00:00.000Z";
const apiKeyId = "0198c982-7da8-7e8d-92bc-609f57cb62ca";

const usageService = (): UsageService => ({
  getSummary: async (input) => {
    expect(input).toMatchObject({
      userId: user.id,
      organizationId,
      workspaceId,
    });
    expect(input.range.from.toISOString()).toBe(from);
    expect(input.range.to.toISOString()).toBe(to);
    return {
      charge: "428600000000",
      inputTokens: "7860000",
      outputTokens: "1560000",
      generationCount: "18294",
      succeededCount: "18166",
      daily: [
        {
          date: "2026-08-20",
          charge: "19600000000",
          input_tokens: "502000",
          output_tokens: "116000",
          generation_count: "1228",
        },
      ],
      models: [
        {
          model_id: "moonshotai/kimi-k3",
          charge: "428600000000",
          input_tokens: "7860000",
          output_tokens: "1560000",
          generation_count: "18294",
        },
      ],
    };
  },
  listGenerations: async (input) => {
    expect(input).toMatchObject({
      userId: user.id,
      organizationId,
      workspaceId,
      apiKeyId,
      limit: 25,
      search: "kimi",
      sort: "highest_cost",
      status: "succeeded",
    });
    return {
      data: [
        {
          id: "0198c982-7da8-7e8d-92bc-609f57cb62cb",
          external_id: null,
          model_id: "moonshotai/kimi-k3",
          status: "succeeded",
          streamed: true,
          charge: "87400000",
          input_tokens: 4_821,
          cached_input_tokens: 0,
          cache_write_tokens: 0,
          output_tokens: 612,
          reasoning_tokens: 0,
          finish_reason: "stop",
          error_code: null,
          usable_output_delivered: true,
          cancellation_owner: null,
          received_at: "2026-08-20T12:34:16.000Z",
          started_at: "2026-08-20T12:34:16.100Z",
          first_token_at: "2026-08-20T12:34:16.740Z",
          completed_at: "2026-08-20T12:34:18.384Z",
        },
      ],
      nextCursor: "next-page",
    };
  },
});

describe("usage routes", () => {
  it("returns workspace usage from the usage service", async () => {
    const app = createApp({
      auth: authenticated,
      services: { usage: usageService() },
    });
    const response = await app.request(
      `/api/v1/organizations/${organizationId}/workspaces/${workspaceId}/usage?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      charge: "428600000000",
      generation_count: "18294",
      daily: [{ date: "2026-08-20" }],
    });
  });

  it("returns filtered generation logs", async () => {
    const app = createApp({
      auth: authenticated,
      services: { usage: usageService() },
    });
    const response = await app.request(
      `/api/v1/organizations/${organizationId}/workspaces/${workspaceId}/generations?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&api_key_id=${apiKeyId}&search=kimi&sort=highest_cost&status=succeeded`,
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      data: [
        {
          model_id: "moonshotai/kimi-k3",
          input_tokens: 4_821,
          status: "succeeded",
        },
      ],
      next_cursor: "next-page",
    });
  });

  it("rejects an invalid date range", async () => {
    const app = createApp({
      auth: authenticated,
      services: { usage: usageService() },
    });
    const response = await app.request(
      `/api/v1/organizations/${organizationId}/workspaces/${workspaceId}/usage?from=${encodeURIComponent(to)}&to=${encodeURIComponent(from)}`,
    );

    expect(response.status).toBe(422);
  });
});
