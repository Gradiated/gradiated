import { useEffect, useRef } from "react";

import {
  InferenceError,
  streamChatCompletion,
  type ChatCompletionDelta,
  type ChatCompletionUsage,
} from "@/api/inference";
import type { McpToolOutcome } from "@/hooks/use-playground-mcp";
import { errorMessage } from "@/lib/errors";
import { functionTools, type PlaygroundTool } from "@/lib/mcp";
import {
  chatRequest,
  supportsTools,
  type AssistantMessage,
  type PlaygroundMessage,
  type PlaygroundSettings,
  type PlaygroundToolCall,
} from "@/lib/playground";
import { playgroundConversation, usePlaygroundStore } from "@/store/playground";

const NO_MESSAGES: PlaygroundMessage[] = [];

export const MAX_TOOL_ROUNDS = 10;

type CallTool = (
  tool: PlaygroundTool,
  input: Record<string, unknown>,
  signal: AbortSignal,
) => Promise<McpToolOutcome>;

const newReply = (): AssistantMessage => ({
  id: crypto.randomUUID(),
  role: "assistant",
  content: "",
  reasoning: "",
  status: "streaming",
});

const withToolDeltas = (
  calls: PlaygroundToolCall[],
  deltas: ChatCompletionDelta["toolCalls"],
  tools: readonly PlaygroundTool[],
): PlaygroundToolCall[] => {
  const next = [...calls];

  for (const delta of deltas) {
    const current = next[delta.index] ?? {
      id: "",
      name: "",
      server: "",
      tool: "",
      arguments: "",
      status: "running" as const,
    };
    const name = current.name + (delta.name ?? "");
    const tool = tools.find((entry) => entry.name === name);

    next[delta.index] = {
      ...current,
      id: delta.id ?? current.id,
      name,
      server: tool?.server.name ?? current.server,
      tool: tool?.tool.name ?? name,
      arguments: current.arguments + (delta.arguments ?? ""),
    };
  }

  return next;
};

const parseArguments = (text: string): Record<string, unknown> | undefined => {
  try {
    const value: unknown = JSON.parse(text || "{}");

    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : undefined;
  } catch {
    return undefined;
  }
};

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
  const currentMessages = () =>
    playgroundConversation(
      usePlaygroundStore.getState().conversations,
      workspaceId,
    ).messages;
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
    tools: available = [],
    callTool,
  }: {
    apiKey: (renew: boolean) => Promise<string>;
    settings: PlaygroundSettings;
    content: string;
    tools?: readonly PlaygroundTool[];
    callTool?: CallTool;
  }) => {
    const abort = new AbortController();
    const tools =
      callTool && supportsTools(settings.capabilities) ? available : [];

    controller.current = abort;
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", content },
    ]);
    // Saving the first message creates the conversation and its session id.
    const { sessionId } = playgroundConversation(
      usePlaygroundStore.getState().conversations,
      workspaceId,
    );

    // One model response; returns whether the model asked for tools.
    const respond = async (): Promise<boolean> => {
      const history = currentMessages();
      const reply = newReply();
      const startedAt = Date.now();
      let firstTokenAt: number | undefined;
      let usage: ChatCompletionUsage | undefined;
      let calls: PlaygroundToolCall[] = [];

      setMessages((current) => [...current, reply]);

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
        if (!delta.content && !delta.reasoning && !delta.toolCalls.length)
          return;

        firstTokenAt ??= Date.now();
        calls = withToolDeltas(calls, delta.toolCalls, tools);
        updateReply(reply.id, (current) => ({
          ...current,
          content: current.content + delta.content,
          reasoning: current.reasoning + delta.reasoning,
          ...(calls.length ? { toolCalls: calls } : {}),
        }));
      };

      const complete = async (renew: boolean) =>
        streamChatCompletion({
          apiKey: await apiKey(renew),
          request: {
            ...chatRequest(settings, history, functionTools(tools)),
            session_id: sessionId,
          },
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
      } catch (error) {
        if (abort.signal.aborted) finish("stopped");
        else finish("failed", errorMessage(error, "The request failed."));

        return false;
      }

      if (!calls.length || !callTool) {
        finish("complete");

        return false;
      }

      // Every result must answer a call ID, so calls streamed without one get their own.
      calls = calls.map((call) =>
        call.id ? call : { ...call, id: `call_${crypto.randomUUID()}` },
      );
      updateReply(reply.id, (current) => ({ ...current, toolCalls: calls }));

      for (const call of calls) {
        const tool = tools.find(({ name }) => name === call.name);
        const input = parseArguments(call.arguments);
        const settle = (status: PlaygroundToolCall["status"], result: string) =>
          updateReply(reply.id, (current) => ({
            ...current,
            toolCalls: (current.toolCalls ?? []).map((entry) =>
              entry.id === call.id ? { ...entry, status, result } : entry,
            ),
          }));

        if (abort.signal.aborted) break;
        if (!tool) {
          settle("failed", `There is no tool named ${call.name}.`);
          continue;
        }
        if (!input) {
          settle("failed", "The arguments are not a JSON object.");
          continue;
        }

        await callTool(tool, input, abort.signal).then(
          ({ isError, text }) => settle(isError ? "failed" : "complete", text),
          (error: unknown) =>
            settle("failed", errorMessage(error, "The tool call failed.")),
        );
      }

      if (abort.signal.aborted) {
        finish("stopped");

        return false;
      }

      finish("complete");

      return true;
    };

    for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
      if (!(await respond())) return;
    }

    setMessages((current) => [
      ...current,
      {
        ...newReply(),
        status: "failed",
        error: `Stopped after ${MAX_TOOL_ROUNDS} rounds of tool calls.`,
      },
    ]);
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
