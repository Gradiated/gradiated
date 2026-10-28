import { describe, expect, it } from "vitest";

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
        },
      },
      "workspace",
    );

    expect(options).toEqual({ ...DEFAULT_SETTINGS, systemPrompt: "Be brief." });
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
