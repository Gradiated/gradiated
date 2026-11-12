import { describe, expect, it } from "vitest";

import { GRADIATED_MCP_SERVER_ID } from "@/lib/mcp";
import { DEFAULT_SETTINGS } from "@/lib/playground";
import { playgroundConversation, usePlaygroundStore } from "@/store/playground";

describe("playgroundConversation", () => {
  it("starts empty for a workspace without a saved conversation", () => {
    const conversation = playgroundConversation({}, "workspace");

    expect(conversation.messages).toEqual([]);
    expect(conversation.options).toEqual(DEFAULT_SETTINGS);
  });

  it("fills settings added after the conversation was saved", () => {
    const { options } = playgroundConversation(
      {
        workspace: {
          model: "z-ai/glm-5.3-flash",
          options: { systemPrompt: "Be brief." } as typeof DEFAULT_SETTINGS,
          messages: [],
          sessionId: "session",
          mcpServers: [],
        },
      },
      "workspace",
    );

    expect(options).toEqual({ ...DEFAULT_SETTINGS, systemPrompt: "Be brief." });
  });

  it("installs the Gradiated MCP server in conversations saved before MCP", () => {
    const { mcpServers } = playgroundConversation(
      {
        workspace: {
          model: undefined,
          options: DEFAULT_SETTINGS,
          messages: [],
          sessionId: "session",
        } as unknown as Parameters<typeof playgroundConversation>[0][string],
      },
      "workspace",
    );

    expect(mcpServers).toMatchObject([
      { id: GRADIATED_MCP_SERVER_ID, enabled: true },
    ]);
  });
});

describe("usePlaygroundStore", () => {
  it("saves nothing until the workspace is known", () => {
    const { update, reset } = usePlaygroundStore.getState();
    reset();

    update("", (conversation) => ({ ...conversation, model: "model" }));
    update("workspace", (conversation) => ({
      ...conversation,
      model: "model",
    }));

    expect(Object.keys(usePlaygroundStore.getState().conversations)).toEqual([
      "workspace",
    ]);
  });
});
