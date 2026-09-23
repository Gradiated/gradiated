import { describe, expect, it } from "vitest";

import {
  ControlServiceError,
  type GenerationLogRecord,
  type UsageService,
  type UsageSummaryRecord,
} from "@gradiated/control";

import {
  anonymous,
  authenticated,
  controlServiceProblems,
  expectProblem,
  failWith,
  unauthenticatedProblem,
  createTestApp,
  organizationId,
  user,
  validationProblem,
  workspaceId,
} from "./support.js";

const from = "2026-08-01T00:00:00.000Z";
const to = "2026-08-21T00:00:00.000Z";
const apiKeyId = "0198c982-7da8-7e8d-92bc-609f57cb62ca";

const usageSummary: UsageSummaryRecord = {
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

const generationLog: GenerationLogRecord = {
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
};

const workspacePath = `/api/v1/organizations/${organizationId}/workspaces/${workspaceId}`;
const range = `from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;

const usageEndpoints = [
  { name: "summary", path: `${workspacePath}/usage?${range}` },
  { name: "generations", path: `${workspacePath}/generations?${range}` },
];

describe("usage routes", () => {
  it("returns workspace usage from the usage service", async () => {
    const received: Parameters<UsageService["getSummary"]>[0][] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        usage: {
          getSummary: async (input) => {
            received.push(input);

            return usageSummary;
          },
        },
      },
    });

    const response = await app.request(`${workspacePath}/usage?${range}`);

    expect(response.status).toBe(200);
    expect(received).toEqual([
      {
        userId: user.id,
        organizationId,
        workspaceId,
        range: { from: new Date(from), to: new Date(to) },
      },
    ]);
    await expect(response.json()).resolves.toMatchObject({
      charge: "428600000000",
      generation_count: "18294",
      daily: [{ date: "2026-08-20" }],
    });
  });

  it("returns filtered generation logs", async () => {
    const received: Parameters<UsageService["listGenerations"]>[0][] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        usage: {
          listGenerations: async (input) => {
            received.push(input);

            return { data: [generationLog], nextCursor: "next-page" };
          },
        },
      },
    });

    const response = await app.request(
      `${workspacePath}/generations?${range}&api_key_id=${apiKeyId}&search=kimi&sort=highest_cost&status=succeeded`,
    );

    expect(response.status).toBe(200);
    expect(received).toEqual([
      {
        userId: user.id,
        organizationId,
        workspaceId,
        range: { from: new Date(from), to: new Date(to) },
        apiKeyId,
        limit: 25,
        search: "kimi",
        sort: "highest_cost",
        status: "succeeded",
      },
    ]);
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
    const app = createTestApp({ auth: authenticated });

    const response = await app.request(
      `${workspacePath}/usage?from=${encodeURIComponent(to)}&to=${encodeURIComponent(from)}`,
    );

    await expectProblem(response, validationProblem);
  });

  it.each(
    usageEndpoints.flatMap((endpoint) =>
      controlServiceProblems.map((problem) => ({ ...endpoint, problem })),
    ),
  )(
    "maps $problem.code on $name to $problem.status",
    async ({ path, problem }) => {
      const error = new ControlServiceError(problem.code, "Rejected.");
      const app = createTestApp({
        auth: authenticated,
        services: {
          usage: {
            getSummary: failWith(error),
            listGenerations: failWith(error),
          },
        },
      });

      await expectProblem(await app.request(path), problem);
    },
  );

  it.each(usageEndpoints)("requires a session for $name", async ({ path }) => {
    const response = await createTestApp({ auth: anonymous }).request(path);

    await expectProblem(response, unauthenticatedProblem);
  });
});
