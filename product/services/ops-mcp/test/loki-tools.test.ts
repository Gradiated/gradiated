import { afterEach, describe, expect, it } from "vitest";

import { callTool, closeServers, lokiStreams, range } from "./support/mcp.js";

afterEach(closeServers);

describe("loki tools", () => {
  it("samples detected fields for a query and range", async () => {
    const { backend } = await callTool("log_fields", {
      query: '{workload="gateway"}',
      ...range,
    });

    expect(backend).toHaveBeenCalledWith(
      "loki",
      "/loki/api/v1/detected_fields",
      {
        query: '{workload="gateway"}',
        start: "2026-09-26T21:00:00.000Z",
        end: "2026-09-26T21:30:00.000Z",
        line_limit: "1000",
      },
    );
  });

  it("returns log streams without Loki's query statistics", async () => {
    const { body } = await callTool(
      "query_logs",
      { query: '{workload="worker"}', ...range },
      lokiStreams,
    );

    expect(body).toEqual({
      status: "success",
      data: {
        resultType: "streams",
        result: lokiStreams.data.result,
      },
    });
  });
});
