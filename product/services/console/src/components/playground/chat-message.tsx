import { Brain, LoaderCircle } from "lucide-react";

import { CopyStateIcon } from "@/components/copy-state-icon";
import { MessageMarkdown } from "@/components/playground/message-markdown";
import { Button } from "@/components/ui/button";
import { copyLabel, useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import {
  replyStats,
  type AssistantMessage,
  type PlaygroundMessage,
} from "@/lib/playground";

export const ChatMessage = ({ message }: { message: PlaygroundMessage }) =>
  message.role === "user" ? (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl bg-muted px-4 py-2.5 text-sm leading-6 break-words whitespace-pre-wrap">
        {message.content}
      </div>
    </div>
  ) : (
    <AssistantReply reply={message} />
  );

const AssistantReply = ({ reply }: { reply: AssistantMessage }) => {
  const thinking = reply.status === "streaming" && !reply.content;

  return (
    <div className="space-y-2">
      {reply.reasoning ? (
        <details
          className="group rounded-lg border bg-muted/40 px-3 py-2 text-sm"
          open={thinking}
        >
          <summary className="flex cursor-pointer items-center gap-2 text-muted-foreground select-none">
            <Brain className="size-4" />
            {thinking ? "Thinking…" : "Reasoning"}
          </summary>
          <p className="mt-2 leading-6 break-words whitespace-pre-wrap text-muted-foreground">
            {reply.reasoning}
          </p>
        </details>
      ) : null}
      {reply.content ? <MessageMarkdown content={reply.content} /> : null}
      {thinking && !reply.reasoning ? (
        <LoaderCircle
          aria-label="Generating"
          className="size-4 animate-spin text-muted-foreground"
        />
      ) : null}
      {reply.error ? (
        <p role="alert" className="text-sm text-destructive">
          {reply.error}
        </p>
      ) : null}
      {reply.status !== "streaming" ? <ReplyFooter reply={reply} /> : null}
    </div>
  );
};

const ReplyFooter = ({ reply }: { reply: AssistantMessage }) => {
  const { state, copy } = useCopyToClipboard();
  const stats = [
    ...(reply.status === "stopped" ? ["Stopped"] : []),
    ...(reply.stats ? replyStats(reply.stats) : []),
  ];

  return (
    <div className="flex min-h-6 items-center gap-2 text-xs text-muted-foreground">
      {reply.content ? (
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={copyLabel(state, "Copy reply")}
          onClick={() => void copy(reply.content)}
        >
          <CopyStateIcon state={state} />
        </Button>
      ) : null}
      <span>{stats.join(" · ")}</span>
    </div>
  );
};
