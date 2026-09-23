import { Info } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatLatency, formatNanoUsd } from "@/lib/format";
import type {
  TraceGenerationRow,
  TraceMessage,
  TraceSummary,
} from "@/store/fine-tuning-types";

const traceStart = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

const prettyJson = (value: string) => {
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
};

const Message = ({
  message,
  generations,
}: {
  message: TraceMessage;
  generations: TraceGenerationRow[];
}) => {
  if (message.role === "system") {
    return (
      <div className="rounded-lg border border-dashed px-3 py-2">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          System
        </p>
        <p className="text-xs leading-5 text-muted-foreground">
          {message.content}
        </p>
      </div>
    );
  }

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2.5 text-sm leading-6 text-primary-foreground whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "tool") {
    return (
      <div className="ml-6 rounded-lg border bg-muted/40 px-3 py-2">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Tool result · {message.tool_name}
        </p>
        <pre className="overflow-x-auto font-mono text-[11px] leading-5">
          {prettyJson(message.content)}
        </pre>
      </div>
    );
  }

  const generation = generations.find(
    (candidate) => candidate.id === message.generation_id,
  );

  return (
    <div>
      {generation ? (
        <div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground tabular-nums">
          <span className="font-mono">{generation.model}</span>
          <span>·</span>
          <span>{formatLatency(generation.latency_ms)}</span>
          <span>·</span>
          <span>
            {generation.input_tokens} in / {generation.output_tokens} out
          </span>
          <span>·</span>
          <span>{formatNanoUsd(generation.cost_nano_usd)}</span>
          {generation.response_status !== 200 ? (
            <Badge
              variant="outline"
              className="border-destructive/25 bg-destructive/5 text-destructive"
            >
              {generation.response_status}
            </Badge>
          ) : null}
        </div>
      ) : null}
      {"tool_call" in message ? (
        <div className="max-w-[85%] rounded-2xl rounded-bl-sm border bg-card px-3.5 py-2.5">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Tool call · {message.tool_call.name}
          </p>
          <pre className="overflow-x-auto font-mono text-[11px] leading-5">
            {prettyJson(message.tool_call.arguments)}
          </pre>
        </div>
      ) : (
        <div className="max-w-[85%] rounded-2xl rounded-bl-sm border bg-card px-3.5 py-2.5 text-sm leading-6 whitespace-pre-wrap">
          {message.content}
        </div>
      )}
    </div>
  );
};

export const TraceSheet = ({
  trace,
  generations,
  messages,
  open,
  onOpenChange,
}: {
  trace: TraceSummary | null;
  generations: TraceGenerationRow[];
  messages: TraceMessage[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) => (
  <Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
      {trace ? (
        <>
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2 font-mono text-base">
              {trace.trace_id}
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="How this trace was grouped"
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <Info className="size-3.5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="text-xs">
                  {trace.single_generation
                    ? "A single generation; no trace id grouped it with others"
                    : "Generations sharing this trace id (from your x-gradiated-trace-id header)"}
                </TooltipContent>
              </Tooltip>
            </SheetTitle>
            <SheetDescription className="tabular-nums">
              {traceStart.format(new Date(trace.started_at))} ·{" "}
              {trace.generation_count} generation
              {trace.generation_count === 1 ? "" : "s"} ·{" "}
              {formatLatency(trace.duration_ms)} ·{" "}
              {formatNanoUsd(trace.cost_nano_usd)}
            </SheetDescription>
          </SheetHeader>
          <div className="mt-6 space-y-4">
            {messages.map((message, i) => (
              <Message key={i} message={message} generations={generations} />
            ))}
          </div>
        </>
      ) : null}
    </SheetContent>
  </Sheet>
);
