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
import {
  NANO,
  type TraceGenerationRow,
  type TraceMessage,
  type TraceSummary,
} from "@/store/mock-fine-tuning";

const formatDateTime = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
const formatDuration = (ms: number) =>
  ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
/** Two significant figures below a cent, so $0.000032 doesn't collapse to $0.0000. */
export const formatNano = (nano: number) => {
  const value = nano / NANO;
  if (value === 0) return "$0";
  if (value < 0.01)
    return `$${Number(value.toPrecision(2)).toFixed(Math.max(2, -Math.floor(Math.log10(value)) + 1))}`;
  return `$${value.toFixed(3)}`;
};

const prettyArgs = (value: string) => {
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
          {prettyArgs(message.content ?? "")}
        </pre>
      </div>
    );
  }
  const generation = generations.find((g) => g.id === message.generation_id);
  return (
    <div>
      {generation ? (
        <div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground tabular-nums">
          <span className="font-mono">{generation.model}</span>
          <span>·</span>
          <span>{formatDuration(generation.latency_ms)}</span>
          <span>·</span>
          <span>
            {generation.input_tokens} in / {generation.output_tokens} out
          </span>
          <span>·</span>
          <span>{formatNano(generation.cost_nano_usd)}</span>
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
      {message.tool_call ? (
        <div className="max-w-[85%] rounded-2xl rounded-bl-sm border bg-card px-3.5 py-2.5">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Tool call · {message.tool_call.name}
          </p>
          <pre className="overflow-x-auto font-mono text-[11px] leading-5">
            {prettyArgs(message.tool_call.arguments)}
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

/** GET P/traces/{trace_id}: the trace's generations in order plus the normalized conversation. */
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
              {formatDateTime(trace.started_at)} · {trace.generation_count}{" "}
              generation{trace.generation_count === 1 ? "" : "s"} ·{" "}
              {formatDuration(trace.duration_ms)} ·{" "}
              {formatNano(trace.cost_nano_usd)}
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
