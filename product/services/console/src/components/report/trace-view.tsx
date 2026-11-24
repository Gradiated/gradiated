import type { EvalMessage } from "@gradiated/contracts";
import { ChevronRight, Lightbulb, Wrench } from "lucide-react";
import { useState, type ReactNode } from "react";

import { MessageMarkdown } from "@/components/playground/message-markdown";
import { cn } from "@/lib/utils";

type ToolCall = NonNullable<EvalMessage["tool_calls"]>[number];
type CallStep = {
  kind: "call";
  call: ToolCall;
  result?: EvalMessage | undefined;
};
type Step = { kind: "message"; message: EvalMessage } | CallStep;

const ASK_USER = /^(ask_user|ask_human|request_user_input)$/;
const GROUP_AFTER = 4;

const pretty = (text: string) => {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
};

const toolName = (name: string) => {
  const words = name.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

const argsPreview = (text: string) => {
  try {
    const value: unknown = JSON.parse(text);
    if (value && typeof value === "object" && !Array.isArray(value))
      return Object.entries(value)
        .map(
          ([key, item]) =>
            `${key.replace(/_/g, " ")}: ${typeof item === "string" ? item : JSON.stringify(item)}`,
        )
        .join(" · ");
  } catch {
    return text;
  }

  return text;
};

const questionOf = (call: ToolCall) => {
  try {
    const value = JSON.parse(call.function.arguments) as Record<
      string,
      unknown
    >;
    const text = value.question ?? value.message ?? value.prompt;
    return typeof text === "string" ? text : call.function.arguments;
  } catch {
    return call.function.arguments;
  }
};

const toSteps = (messages: EvalMessage[]) => {
  const steps: Step[] = [];
  const pending = new Map<string, CallStep>();

  for (const message of messages) {
    if (message.role === "tool" && message.tool_call_id) {
      const step = pending.get(message.tool_call_id);
      if (step) {
        step.result = message;
        continue;
      }
    }

    if (message.role !== "assistant" || message.content || message.reasoning)
      steps.push({ kind: "message", message: { ...message, tool_calls: [] } });

    for (const call of message.tool_calls ?? []) {
      const step: CallStep = { kind: "call", call };
      pending.set(call.id, step);
      steps.push(step);
    }
  }

  return steps;
};

const Code = ({ children }: { children: string }) => (
  <pre className="max-h-80 overflow-auto rounded-md bg-muted/70 px-3 py-2 font-mono text-[11.5px] leading-5 break-words whitespace-pre-wrap">
    {children}
  </pre>
);

const Thought = ({ text }: { text: string }) => {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 self-start text-[12.5px] text-muted-foreground hover:text-foreground"
      >
        <Lightbulb aria-hidden className="size-3.5" />
        Thought · {text.length.toLocaleString()} characters
      </button>
      {open ? (
        <p className="border-l-2 pl-3 text-[12.5px] leading-5 whitespace-pre-wrap text-muted-foreground">
          {text}
        </p>
      ) : null}
    </div>
  );
};

const Bubble = ({
  label,
  align,
  children,
}: {
  label: string;
  align: "left" | "right";
  children: ReactNode;
}) => (
  <div
    className={cn(
      "flex max-w-[88%] flex-col gap-0.5 rounded-xl px-3.5 py-2.5",
      align === "right" ? "ml-auto bg-muted" : "mr-auto border bg-card",
    )}
  >
    <span className="text-[11.5px] text-muted-foreground">{label}</span>
    <div className="text-sm leading-6 break-words whitespace-pre-wrap">
      {children}
    </div>
  </div>
);

const ToolCard = ({ call, result }: Omit<CallStep, "kind">) => {
  const [open, setOpen] = useState(false);

  return (
    <div
      className={cn(
        "rounded-lg border bg-card",
        result?.is_error && "border-red-200",
      )}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full min-w-0 items-center gap-2 px-3 py-2 text-left text-[13px]"
      >
        <Wrench
          aria-hidden
          className="size-3.5 shrink-0 text-muted-foreground"
        />
        <span className="shrink-0 font-medium">
          {toolName(call.function.name)}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
          {argsPreview(call.function.arguments)}
        </span>
        {result?.is_error ? (
          <span className="shrink-0 rounded bg-red-50 px-1.5 text-[11px] text-red-700">
            Error
          </span>
        ) : null}
        <ChevronRight
          aria-hidden
          className={cn(
            "size-3.5 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-90",
          )}
        />
      </button>
      {open ? (
        <div className="flex flex-col gap-2 border-t px-3 py-2.5">
          <span className="text-[11.5px] text-muted-foreground">Arguments</span>
          <Code>{pretty(call.function.arguments)}</Code>
          <span className="text-[11.5px] text-muted-foreground">Result</span>
          {result ? (
            <Code>{pretty(result.content ?? "")}</Code>
          ) : (
            <span className="text-xs text-muted-foreground">
              No result recorded.
            </span>
          )}
        </div>
      ) : null}
    </div>
  );
};

const StepView = ({ step }: { step: Step }) => {
  if (step.kind === "call") {
    if (!ASK_USER.test(step.call.function.name))
      return <ToolCard call={step.call} result={step.result} />;

    return (
      <>
        <Bubble label="Question for the user" align="left">
          {questionOf(step.call)}
        </Bubble>
        {step.result?.content ? (
          <Bubble label="User" align="right">
            {step.result.content}
          </Bubble>
        ) : null}
      </>
    );
  }

  const { message } = step;
  if (message.role === "user")
    return (
      <Bubble label="User" align="right">
        {message.content}
      </Bubble>
    );
  if (message.role !== "assistant")
    return message.content ? <Code>{message.content}</Code> : null;

  return (
    <>
      {message.reasoning ? <Thought text={message.reasoning} /> : null}
      {message.content ? <MessageMarkdown content={message.content} /> : null}
    </>
  );
};

const isPlainCall = (step: Step) =>
  step.kind === "call" && !ASK_USER.test(step.call.function.name);

export const TraceView = ({ messages }: { messages: EvalMessage[] }) => {
  const steps = toSteps(messages);
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set());
  const blocks: ReactNode[] = [];

  for (let index = 0; index < steps.length;) {
    let end = index;
    while (end < steps.length && isPlainCall(steps[end]!)) end++;

    const start = index;
    const collapsed = end - start > GROUP_AFTER && !expanded.has(start);
    const stop = collapsed ? start + 2 : Math.max(end, start + 1);
    for (let shown = start; shown < stop; shown++)
      blocks.push(<StepView key={shown} step={steps[shown]!} />);
    if (collapsed)
      blocks.push(
        <button
          key={`more-${start}`}
          type="button"
          onClick={() => setExpanded(new Set([...expanded, start]))}
          className="self-start rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          Show {end - stop} more tool calls
        </button>,
      );

    index = Math.max(end, start + 1);
  }

  return steps.length ? (
    <div className="flex min-w-0 flex-col gap-2.5">{blocks}</div>
  ) : (
    <p className="text-sm text-muted-foreground">No trace recorded.</p>
  );
};
