import { useQueries } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, requireData } from "@/api/client";
import {
  GRADIATED_MCP_SERVER_ID,
  installedServers,
  playgroundTools,
  type InstalledMcpServer,
  type McpTool,
  type PlaygroundTool,
} from "@/lib/mcp";
import { usePlaygroundStore } from "@/store/playground";

export type McpServerState =
  | { status: "off" }
  | { status: "loading" }
  | { status: "ready"; tools: McpTool[] }
  | { status: "error"; error: string };

export interface McpToolOutcome {
  isError: boolean;
  text: string;
}

const TOOL_LIST_STALE_MS = 5 * 60 * 1000;

// Distinguishes header values in the query key without keeping a credential there.
const fingerprint = (headers: Record<string, string>) => {
  let hash = 2166136261;
  for (const character of JSON.stringify(headers))
    hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);

  return (hash >>> 0).toString(36);
};

export const usePlaygroundMcp = (
  workspaceId: string,
  apiKey: (renew: boolean) => Promise<string>,
) => {
  const stored = usePlaygroundStore(
    ({ conversations }) => conversations[workspaceId]?.mcpServers,
  );
  const update = usePlaygroundStore((state) => state.update);
  const servers = useMemo(() => installedServers(stored), [stored]);

  // The Gradiated server takes the playground key, which is renewed once if it was rejected.
  const withConnection = async <Result>(
    server: InstalledMcpServer,
    use: (connection: {
      url: string;
      headers: Record<string, string>;
    }) => Promise<Result>,
  ): Promise<Result> => {
    if (server.id !== GRADIATED_MCP_SERVER_ID)
      return use({ url: server.url, headers: server.headers });

    const connect = async (renew: boolean) =>
      use({
        url: server.url,
        headers: { Authorization: `Bearer ${await apiKey(renew)}` },
      });

    return connect(false).catch(() => connect(true));
  };

  const lists = useQueries({
    queries: servers.map((server) => ({
      queryKey: [
        "playground-mcp-tools",
        workspaceId,
        server.id,
        server.url,
        fingerprint(server.headers),
      ],
      enabled: server.enabled && workspaceId !== "",
      staleTime: TOOL_LIST_STALE_MS,
      retry: false,
      queryFn: async () => {
        const list = await withConnection(server, (connection) =>
          requireData(
            api.POST(
              "/api/v1/workspaces/{workspace_id}/playground/mcp-tool-lists",
              {
                params: { path: { workspace_id: workspaceId } },
                body: { server: connection },
              },
            ),
          ),
        );
        // A malformed answer marks this one server as failed instead of breaking the page.
        if (!Array.isArray(list.tools))
          throw new Error("The server did not return a tool list.");

        return list;
      },
    })),
  });

  const states: { server: InstalledMcpServer; state: McpServerState }[] =
    servers.map((server, index) => {
      const list = lists[index];
      if (!server.enabled) return { server, state: { status: "off" } };
      if (list?.data)
        return { server, state: { status: "ready", tools: list.data.tools } };
      if (list?.error)
        return {
          server,
          state: { status: "error", error: list.error.message },
        };

      return { server, state: { status: "loading" } };
    });

  const tools: PlaygroundTool[] = playgroundTools(
    states.flatMap(({ server, state }) =>
      state.status === "ready" ? [{ server, tools: state.tools }] : [],
    ),
  );

  const setServers = (
    change: (current: InstalledMcpServer[]) => InstalledMcpServer[],
  ) =>
    update(workspaceId, (conversation) => ({
      ...conversation,
      mcpServers: installedServers(change(conversation.mcpServers)),
    }));

  const callTool = async (
    tool: PlaygroundTool,
    input: Record<string, unknown>,
    signal: AbortSignal,
  ): Promise<McpToolOutcome> => {
    const result = await withConnection(tool.server, (connection) =>
      requireData(
        api.POST(
          "/api/v1/workspaces/{workspace_id}/playground/mcp-tool-calls",
          {
            params: { path: { workspace_id: workspaceId } },
            body: {
              server: connection,
              name: tool.tool.name,
              arguments: input,
            },
            signal,
          },
        ),
      ),
    );

    return { isError: result.is_error, text: result.text };
  };

  return {
    servers: states,
    tools,
    callTool,
    setEnabled: (id: string, enabled: boolean) =>
      setServers((current) =>
        current.map((server) =>
          server.id === id ? { ...server, enabled } : server,
        ),
      ),
    add: (server: InstalledMcpServer) =>
      setServers((current) => [...current, server]),
    remove: (id: string) =>
      setServers((current) => current.filter((server) => server.id !== id)),
  };
};

export type PlaygroundMcp = ReturnType<typeof usePlaygroundMcp>;
