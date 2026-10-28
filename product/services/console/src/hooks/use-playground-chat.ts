import { useEffect, useRef } from "react";

import {
  InferenceError,
  streamChatCompletion,
  type ChatCompletionDelta,
  type ChatCompletionUsage,
} from "@/api/inference";
import { errorMessage } from "@/lib/errors";
import {
  chatRequest,
  type AssistantMessage,
  type PlaygroundMessage,
  type PlaygroundSettings,
} from "@/lib/playground";
import { playgroundConversation, usePlaygroundStore } from "@/store/playground";

const NO_MESSAGES: PlaygroundMessage[] = [];

export const usePlaygroundChat = (workspaceId: string) => {
  const messages = usePlaygroundStore(
    ({ conversations }) => conversations[workspaceId]?.messages ?? NO_MESSAGES,
  );
  const update = usePlaygroundStore((state) => state.update);
  const setMessages = (
    change: (current: PlaygroundMessage[]) => PlaygroundMessage[],
  ) =>
    update(workspaceId, (conversation) => ({
      ...conversation,
      messages: change(conversation.messages),
    }));
  const controller = useRef<AbortController | undefined>(undefined);
  const last = messages.at(-1);
  const streaming = last?.role === "assistant" && last.status === "streaming";

  useEffect(() => () => controller.current?.abort(), [workspaceId]);

  const updateReply = (
    id: string,
    update: (reply: AssistantMessage) => AssistantMessage,
  ) =>
    setMessages((current) =>
      current.map((message) =>
        message.id === id && message.role === "assistant"
          ? update(message)
          : message,
      ),
    );

  const send = async ({
    apiKey,
    settings,
    content,
  }: {
    apiKey: (renew: boolean) => Promise<string>;
    settings: PlaygroundSettings;
    content: string;
  }) => {
    const history: PlaygroundMessage[] = [
      ...messages,
      { id: crypto.randomUUID(), role: "user", content },
    ];
    const reply: AssistantMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      reasoning: "",
      status: "streaming",
    };
    const abort = new AbortController();
    const startedAt = Date.now();
    let firstTokenAt: number | undefined;
    let usage: ChatCompletionUsage | undefined;

    setMessages(() => [...history, reply]);
    controller.current = abort;
    // Saving the first message creates the conversation and its session id.
    const { sessionId } = playgroundConversation(
      usePlaygroundStore.getState().conversations,
      workspaceId,
    );

    const finish = (
      status: Exclude<AssistantMessage["status"], "streaming">,
      error?: string,
    ) =>
      updateReply(reply.id, (current) => ({
        ...current,
        status,
        ...(error ? { error } : {}),
        stats: {
          firstTokenMs:
            firstTokenAt === undefined ? undefined : firstTokenAt - startedAt,
          totalMs: Date.now() - startedAt,
          usage,
        },
      }));

    const onDelta = (delta: ChatCompletionDelta) => {
      usage = delta.usage ?? usage;
      if (!delta.content && !delta.reasoning) return;

      firstTokenAt ??= Date.now();
      updateReply(reply.id, (current) => ({
        ...current,
        content: current.content + delta.content,
        reasoning: current.reasoning + delta.reasoning,
      }));
    };

    const complete = async (renew: boolean) =>
      streamChatCompletion({
        apiKey: await apiKey(renew),
        request: { ...chatRequest(settings, history), session_id: sessionId },
        signal: abort.signal,
        onDelta,
      });

    try {
      // A rejected key fails before any output, so one retry with a new key is safe.
      await complete(false).catch((error: unknown) => {
        if (error instanceof InferenceError && error.status === 401)
          return complete(true);
        throw error;
      });
      finish("complete");
    } catch (error) {
      if (abort.signal.aborted) finish("stopped");
      else finish("failed", errorMessage(error, "The request failed."));
    }
  };

  const stop = () => controller.current?.abort();

  const clear = () => {
    stop();
    update(workspaceId, (conversation) => ({
      ...conversation,
      messages: [],
      sessionId: crypto.randomUUID(),
    }));
  };

  return { messages, streaming, send, stop, clear };
};
