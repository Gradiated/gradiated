import { LoaderCircle, Plus, Trash2, Unplug } from "lucide-react";
import { useState } from "react";

import { AddMcpServerDialog } from "@/components/playground/add-mcp-server-dialog";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import type { McpServerState, PlaygroundMcp } from "@/hooks/use-playground-mcp";
import { GRADIATED_MCP_SERVER_ID } from "@/lib/mcp";

const stateLabel = (state: McpServerState) => {
  switch (state.status) {
    case "off":
      return "Off";
    case "loading":
      return "Connecting…";
    case "ready":
      return state.tools.length === 1
        ? "1 tool"
        : `${state.tools.length} tools`;
    case "error":
      return state.error;
  }
};

export const McpPicker = ({
  mcp,
  toolsSupported,
}: {
  mcp: PlaygroundMcp;
  toolsSupported: boolean;
}) => {
  const [adding, setAdding] = useState(false);
  const active = mcp.servers.filter(({ state }) => state.status !== "off");
  const connecting = active.some(({ state }) => state.status === "loading");

  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="MCP servers"
            className="text-muted-foreground"
          >
            {connecting ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <Unplug />
            )}
            MCP
            {toolsSupported && mcp.tools.length ? (
              <span className="rounded-full bg-muted px-1.5 text-xs tabular-nums">
                {mcp.tools.length}
              </span>
            ) : null}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80 p-0">
          <div className="border-b px-3 py-2.5">
            <p className="text-sm font-medium">MCP servers</p>
            <p className="text-xs text-muted-foreground">
              {toolsSupported
                ? "The model can call tools from servers that are on."
                : "This model does not accept tools, so none are sent."}
            </p>
          </div>
          <ul className="max-h-72 overflow-y-auto py-1">
            {mcp.servers.map(({ server, state }) => (
              <li key={server.id} className="flex items-center gap-3 px-3 py-2">
                <Switch
                  checked={server.enabled}
                  aria-label={`Use ${server.name}`}
                  onCheckedChange={(enabled) =>
                    mcp.setEnabled(server.id, enabled)
                  }
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{server.name}</p>
                  <p
                    className={
                      state.status === "error"
                        ? "line-clamp-2 text-xs text-destructive"
                        : "truncate text-xs text-muted-foreground"
                    }
                    title={state.status === "error" ? state.error : server.url}
                  >
                    {stateLabel(state)}
                  </p>
                </div>
                {server.id === GRADIATED_MCP_SERVER_ID ? null : (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-xs"
                    aria-label={`Remove ${server.name}`}
                    onClick={() => mcp.remove(server.id)}
                  >
                    <Trash2 />
                  </Button>
                )}
              </li>
            ))}
          </ul>
          <div className="border-t p-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="w-full justify-start"
              onClick={() => setAdding(true)}
            >
              <Plus />
              Add server
            </Button>
          </div>
        </PopoverContent>
      </Popover>
      <AddMcpServerDialog
        open={adding}
        installed={mcp.servers.map(({ server }) => server)}
        onOpenChange={setAdding}
        onAdd={(server) => {
          mcp.add(server);
          setAdding(false);
        }}
      />
    </>
  );
};
