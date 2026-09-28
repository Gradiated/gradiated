import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { AddressInfo } from "node:net";
import { vi } from "vitest";

import { createHttp } from "../../src/http.js";

export const token = "test-only-credential-0123456789abcdef";
export const lokiStreams = {
  status: "success",
  data: {
    resultType: "streams",
    result: [{ stream: { workload: "worker" }, values: [["1", "line"]] }],
    stats: { summary: { execTime: 0.01 } },
  },
};

export const range = {
  start: "2026-09-26T21:00:00Z",
  end: "2026-09-26T21:30:00Z",
};

const open: ReturnType<typeof createHttp>[] = [];

export const closeServers = async () => {
  for (const app of open.splice(0)) {
    app.server.closeAllConnections();
    await new Promise<void>((resolve) => app.server.close(() => resolve()));
  }
};

export const setup = async () => {
  const backend = vi.fn(async (): Promise<unknown> => ({
    status: "success",
    data: [],
  }));
  const audit = vi.fn();
  const options = {
    host: "ops.gradiated.com",
    authenticate: async (supplied: string) =>
      supplied === token
        ? { subject: "test-coder", email: "tester@gradiated.com" }
        : undefined,
    backend,
    audit,
  };
  const app = createHttp(options);
  open.push(app);
  await new Promise<void>((resolve) =>
    app.server.listen(0, "127.0.0.1", resolve),
  );

  const url = new URL(
    `http://127.0.0.1:${(app.server.address() as AddressInfo).port}/mcp`,
  );
  options.host = url.host;
  const headers = {
    host: url.host,
    authorization: `Bearer ${token}`,
    "content-type": "application/json",
    accept: "application/json, text/event-stream",
  };

  return { app, url, backend, audit, headers };
};

export const callTool = async (
  name: string,
  args: Record<string, unknown>,
  response: unknown = { status: "success", data: [] },
) => {
  const { url, headers, backend } = await setup();
  backend.mockResolvedValue(response);
  const client = new Client({ name: "test", version: "1" });
  await client.connect(
    new StreamableHTTPClientTransport(url, { requestInit: { headers } }),
  );

  const result = await client.callTool({ name, arguments: args });
  await client.close();

  const content = result.content as { text: string }[];
  const body = result.isError
    ? undefined
    : (JSON.parse(content[0]?.text ?? "{}") as { result: unknown }).result;

  return { backend, isError: result.isError === true, body };
};
