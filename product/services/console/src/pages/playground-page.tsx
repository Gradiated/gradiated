import { useNavigate, useSearch } from "@tanstack/react-router";
import { MessagesSquare, RotateCcw } from "lucide-react";
import { useEffect, useRef } from "react";

import { ModelIcon } from "@/components/model-label";
import { ChatComposer } from "@/components/playground/chat-composer";
import { ChatMessage } from "@/components/playground/chat-message";
import { CodeDialog } from "@/components/playground/code-dialog";
import { McpPicker } from "@/components/playground/mcp-picker";
import { PlaygroundSettingsPanel } from "@/components/playground/playground-settings";
import { Button } from "@/components/ui/button";
import { usePlaygroundChat } from "@/hooks/use-playground-chat";
import { usePlaygroundCredential } from "@/hooks/use-playground-credential";
import { usePlaygroundMcp } from "@/hooks/use-playground-mcp";
import { usePlaygroundModels } from "@/hooks/use-playground-models";
import { useProductContext } from "@/hooks/use-product-context";
import { functionTools } from "@/lib/mcp";
import {
  chatRequest,
  DEFAULT_SETTINGS,
  supportsTools,
  NO_CAPABILITIES,
  type PlaygroundMessage,
  type PlaygroundModel,
  type PlaygroundSettings,
  type PlaygroundSettingsPatch,
} from "@/lib/playground";
import { ConsolePage, LoadFailed } from "@/pages/console-page";
import { usePlaygroundStore } from "@/store/playground";

export const PlaygroundPage = () => {
  const search = useSearch({ from: "/playground" });
  const navigate = useNavigate({ from: "/playground" });
  const apiKey = usePlaygroundCredential();
  const { models, hosted, settled } = usePlaygroundModels(
    search.model && search.task
      ? { name: search.model, task: search.task }
      : undefined,
  );
  const { workspaceId } = useProductContext();
  const stored = usePlaygroundStore(
    ({ conversations }) => conversations[workspaceId],
  );
  const update = usePlaygroundStore((state) => state.update);
  const options = { ...DEFAULT_SETTINGS, ...stored?.options };
  const chat = usePlaygroundChat(workspaceId);
  const mcp = usePlaygroundMcp(workspaceId, apiKey);

  // A model in the URL wins; otherwise reopen the last one used here.
  const model =
    models.find(
      (entry) =>
        entry.available && entry.id === (search.model ?? stored?.model),
    ) ?? models.find((entry) => entry.available);
  const modelId = model?.id;

  // Wait for tasks too, or a saved task would be replaced by a hosted fallback.
  useEffect(() => {
    if (settled && modelId && modelId !== stored?.model) {
      update(workspaceId, (conversation) => ({
        ...conversation,
        model: modelId,
      }));
    }
  }, [settled, modelId, stored?.model, update, workspaceId]);

  const settings: PlaygroundSettings = {
    ...options,
    model: model?.id ?? "",
    capabilities: model?.capabilities ?? NO_CAPABILITIES,
  };
  const toolsSupported = supportsTools(settings.capabilities);

  const changeSettings = ({
    model: nextModel,
    ...patch
  }: PlaygroundSettingsPatch) => {
    if (nextModel !== undefined) {
      void navigate({
        search: (current) =>
          nextModel === current.model ? current : { model: nextModel },
        replace: true,
      });
    }

    update(workspaceId, (conversation) => ({
      ...conversation,
      options: { ...conversation.options, ...patch },
    }));
  };

  return (
    <ConsolePage
      page="playground"
      title="Playground"
      description="Chat with hosted and fine-tuned models before calling them from your application."
      width="wide"
      actions={
        <>
          <CodeDialog
            request={chatRequest(
              settings,
              chat.messages,
              toolsSupported ? functionTools(mcp.tools) : [],
            )}
            disabled={!model || !chat.messages.length}
          />
          <Button
            variant="outline"
            disabled={!chat.messages.length}
            onClick={chat.clear}
          >
            <RotateCcw />
            Clear
          </Button>
        </>
      }
    >
      {hosted.isError ? (
        <LoadFailed
          subject="models"
          retrying={hosted.isFetching}
          onRetry={() => void hosted.refetch()}
          className="min-h-64 rounded-xl border bg-card"
        />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <section
            aria-label="Conversation"
            className="flex h-[calc(100svh-15rem)] min-h-[28rem] flex-col overflow-hidden rounded-xl border bg-card shadow-sm"
          >
            <Conversation messages={chat.messages} model={model} />
            <div className="border-t p-3">
              <ChatComposer
                disabled={!model}
                streaming={chat.streaming}
                placeholder={`Message ${model?.label ?? "the model"}`}
                onStop={chat.stop}
                tools={<McpPicker mcp={mcp} toolsSupported={toolsSupported} />}
                onSend={(content) =>
                  void chat.send({
                    apiKey,
                    settings,
                    content,
                    tools: mcp.tools,
                    callTool: mcp.callTool,
                  })
                }
              />
            </div>
          </section>
          <aside
            aria-label="Settings"
            className="space-y-6 rounded-xl border bg-card p-5 shadow-sm lg:max-h-[max(calc(100svh-15rem),28rem)] lg:self-start lg:overflow-y-auto"
          >
            <PlaygroundSettingsPanel
              models={models}
              loading={hosted.isLoading}
              tiers={hosted.data?.service_tiers ?? []}
              settings={settings}
              onChange={changeSettings}
            />
          </aside>
        </div>
      )}
    </ConsolePage>
  );
};

const PINNED_THRESHOLD_PX = 32;

const Conversation = ({
  messages,
  model,
}: {
  messages: readonly PlaygroundMessage[];
  model: PlaygroundModel | undefined;
}) => {
  const scroller = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    const element = scroller.current;
    if (element && pinned.current) element.scrollTop = element.scrollHeight;
  }, [messages]);

  return (
    <div
      ref={scroller}
      className="min-h-0 flex-1 overflow-y-auto"
      onScroll={(event) => {
        const { scrollHeight, scrollTop, clientHeight } = event.currentTarget;
        pinned.current =
          scrollHeight - scrollTop - clientHeight < PINNED_THRESHOLD_PX;
      }}
    >
      {messages.length ? (
        <div className="mx-auto max-w-3xl space-y-6 p-5">
          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}
        </div>
      ) : (
        <div className="grid h-full place-items-center p-6 text-center">
          <div className="max-w-sm">
            <span className="mx-auto grid size-11 place-items-center rounded-xl bg-muted">
              {model ? (
                <ModelIcon id={model.iconId} className="size-6" />
              ) : (
                <MessagesSquare className="size-5 text-muted-foreground" />
              )}
            </span>
            <p className="mt-4 font-medium">
              {model ? `Try ${model.label}` : "Choose a model"}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Messages use the model and parameters in the settings panel.
              Change them at any point in the conversation.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
