import { create } from "zustand";
import { persist } from "zustand/middleware";

import {
  DEFAULT_SETTINGS,
  type PlaygroundMessage,
  type PlaygroundOptions,
} from "@/lib/playground";

export interface PlaygroundConversation {
  model: string | undefined;
  options: PlaygroundOptions;
  messages: PlaygroundMessage[];
  sessionId: string;
}

const emptyConversation = (): PlaygroundConversation => ({
  model: undefined,
  options: DEFAULT_SETTINGS,
  messages: [],
  sessionId: crypto.randomUUID(),
});

interface PlaygroundState {
  conversations: Record<string, PlaygroundConversation>;
  update: (
    workspaceId: string,
    change: (conversation: PlaygroundConversation) => PlaygroundConversation,
  ) => void;
  reset: () => void;
}

export const playgroundConversation = (
  conversations: Record<string, PlaygroundConversation>,
  workspaceId: string,
): PlaygroundConversation => {
  const stored = conversations[workspaceId];

  // Options saved by an older version gain any settings added since.
  return stored
    ? { ...stored, options: { ...DEFAULT_SETTINGS, ...stored.options } }
    : emptyConversation();
};

// A reply cannot resume after a reload, so one saved mid-stream ends as stopped.
const settled = (messages: PlaygroundMessage[]): PlaygroundMessage[] =>
  messages.map((message) =>
    message.role === "assistant" && message.status === "streaming"
      ? { ...message, status: "stopped" }
      : message,
  );

// Each workspace keeps its own conversation and settings across reloads.
export const usePlaygroundStore = create<PlaygroundState>()(
  persist(
    (set) => ({
      conversations: {},
      update: (workspaceId, change) =>
        // Nothing is saved before the workspace is known.
        set(({ conversations }) =>
          workspaceId === ""
            ? {}
            : {
                conversations: {
                  ...conversations,
                  [workspaceId]: change(
                    playgroundConversation(conversations, workspaceId),
                  ),
                },
              },
        ),
      reset: () => set({ conversations: {} }),
    }),
    {
      name: "gradiated-playground",
      version: 1,
      merge: (persisted, current) => {
        const conversations =
          (persisted as Partial<PlaygroundState> | undefined)?.conversations ??
          {};

        return {
          ...current,
          conversations: Object.fromEntries(
            Object.entries(conversations)
              .filter(([workspaceId]) => workspaceId !== "")
              .map(([workspaceId, conversation]) => [
                workspaceId,
                { ...conversation, messages: settled(conversation.messages) },
              ]),
          ),
        };
      },
    },
  ),
);
