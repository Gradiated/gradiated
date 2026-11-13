import { describe, expect, it } from "vitest";

import {
  credentialHeaders,
  functionTools,
  GRADIATED_MCP_SERVER_ID,
  GRADIATED_MCP_URL,
  installedServers,
  MCP_CATALOG,
  playgroundTools,
  type InstalledMcpServer,
  type McpTool,
} from "@/lib/mcp";

const server = (
  name: string,
  patch: Partial<InstalledMcpServer> = {},
): InstalledMcpServer => ({
  id: name,
  name,
  url: `https://${name}.example.com/mcp`,
  headers: {},
  enabled: true,
  ...patch,
});

const tool = (name: string, patch: Partial<McpTool> = {}): McpTool => ({
  name,
  title: null,
  description: null,
  input_schema: { type: "object" },
  read_only: true,
  ...patch,
});

describe("installedServers", () => {
  it("installs and enables the Gradiated server by default", () => {
    expect(installedServers(undefined)).toEqual([
      {
        id: GRADIATED_MCP_SERVER_ID,
        name: "Gradiated",
        url: GRADIATED_MCP_URL,
        headers: {},
        enabled: true,
      },
    ]);
  });

  it("keeps Gradiated first at this console's URL and remembers when it is off", () => {
    const servers = installedServers([
      server("docs"),
      {
        ...server("gradiated"),
        id: GRADIATED_MCP_SERVER_ID,
        url: "https://stale.example.com/mcp",
        enabled: false,
      },
    ]);

    expect(
      servers.map(({ id, url, enabled }) => ({ id, url, enabled })),
    ).toEqual([
      { id: GRADIATED_MCP_SERVER_ID, url: GRADIATED_MCP_URL, enabled: false },
      { id: "docs", url: "https://docs.example.com/mcp", enabled: true },
    ]);
  });

  it("restores Gradiated if a saved list lost it", () => {
    expect(installedServers([server("docs")])[0]?.id).toBe(
      GRADIATED_MCP_SERVER_ID,
    );
  });
});

describe("credentialHeaders", () => {
  const github = MCP_CATALOG.find(({ id }) => id === "github")!;
  const context7 = MCP_CATALOG.find(({ id }) => id === "context7")!;

  it("sends a token in the server's header", () => {
    expect(credentialHeaders(github.credential, " ghp_123 ")).toEqual({
      Authorization: "Bearer ghp_123",
    });
    expect(credentialHeaders(context7.credential, "key")).toEqual({
      CONTEXT7_API_KEY: "key",
    });
  });

  it("sends nothing without a value", () => {
    expect(credentialHeaders(context7.credential, "  ")).toEqual({});
  });
});

describe("playgroundTools", () => {
  it("prefixes tools with their server and keeps function names valid and unique", () => {
    const tools = playgroundTools([
      {
        server: server("Docs Search"),
        tools: [tool("search"), tool("read.page")],
      },
      {
        server: server("docs search", { id: "other" }),
        tools: [tool("search")],
      },
      { server: server("x".repeat(80)), tools: [tool("y".repeat(40))] },
    ]);

    expect(tools.map(({ name }) => name)).toEqual([
      "docs_search__search",
      "docs_search__read_page",
      "docs_search__search_2",
      `${"x".repeat(64)}`,
    ]);
    expect(tools[2]?.server.id).toBe("other");
    expect(tools[3]?.tool.name).toBe("y".repeat(40));
  });

  it("describes each tool to the model as a function", () => {
    const [definition] = functionTools(
      playgroundTools([
        {
          server: server("docs"),
          tools: [
            tool("search", {
              title: "Search",
              input_schema: { type: "object", properties: {} },
            }),
          ],
        },
      ]),
    );

    expect(definition).toEqual({
      type: "function",
      function: {
        name: "docs__search",
        description: "Search",
        parameters: { type: "object", properties: {} },
      },
    });
  });
});
