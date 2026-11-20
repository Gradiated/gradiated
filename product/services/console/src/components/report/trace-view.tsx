import type { EvalMessage } from "@gradiated/contracts";
import { ChevronRight, MessageCircleQuestion, Wrench } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

type ToolCall = NonNullable<EvalMessage["tool_calls"]>[number];
type Step =
  | { kind: "message"; message: EvalMessage }
  | { kind: "call"; call: ToolCall; result?: EvalMessage };

const ASK_USER = /^(ask_user|ask_human|request_user_input)$/;

const pretty = (text: string) => {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
};

const argsPreview = (text: string) => {
  try {
    const value: unknown = JSON.parse(text);
    if (value && typeof value === "object" && !Array.isArray(value))
      return Object.entries(value)
        .map(
          ([key, item]) =>
            `${key}: ${typeof item === "string" ? item : JSON.stringify(item)}`,
        )
        .join(", ");
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
  const pending = new Map<string, Extract<Step, { kind: "call" }>>();

  for (const message of messages) {
    if (message.role === "tool" && message.tool_call_id) {
      const step = pending.get(message.tool_call_id);
      if (step) {
        step.result = message;
        continue;
      }
    }

    if (message.role === "assistant" && (message.content || message.reasoning))
      steps.push({ kind: "message", message: { ...message, tool_calls: [] } });
    else if (message.role !== "assistant")
      steps.push({ kind: "message", message });

    for (const call of message.tool_calls ?? []) {
      const step: Extract<Step, { kind: "call" }> = { kind: "call", call };
      pending.set(call.id, step);
      steps.push(step);
    }
  }

  return steps;
};

const Disclosure = ({
  summary,
  children,
  className,
}: {
  summary: ReactNode;
  children: ReactNode;
  className?: string;
}) => {
  const [open, setOpen] = useState(false);

  return (
    <div className={cn("min-w-0 rounded-lg border bg-card", className)}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full min-w-0 items-center gap-2 px-3 py-2 text-left text-xs"
      >
        <ChevronRight
          aria-hidden
          className={cn(
            "size-3.5 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-90",
          )}
        />
        {summary}
      </button>
      {open ? <div className="border-t px-3 py-2.5">{children}</div> : null}
    </div>
  );
};

const Code = ({ children }: { children: string }) => (
  <pre className="max-h-96 overflow-auto rounded-md bg-muted px-3 py-2 font-mono text-[11px] leading-5 whitespace-pre-wrap break-words">
    {children}
  </pre>
);

const Bubble = ({ role, children }: { role: string; children: ReactNode }) => (
  <div
    className={cn(
      "flex flex-col gap-1 rounded-xl px-3.5 py-2.5 text-sm leading-6",
      role === "user" ? "bg-muted" : "bg-card",
    )}
  >
    <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
      {role === "user"
        ? "User"
        : role === "system"
          ? "System"
          : role === "tool"
            ? "Tool"
            : "Assistant"}
    </span>
    <div className="whitespace-pre-wrap break-words">{children}</div>
  </div>
);

const MessageStep = ({ message }: { message: EvalMessage }) => (
  <div className="flex flex-col gap-2">
    {message.reasoning ? (
      <Disclosure
        className="border-dashed bg-transparent"
        summary={
          <span className="min-w-0 truncate text-muted-foreground">
            <span className="font-medium text-foreground/80">Thinking</span>
            {" · "}
            {message.reasoning.slice(0, 140)}
          </span>
        }
      >
        <p className="text-xs leading-5 whitespace-pre-wrap text-muted-foreground">
          {message.reasoning}
        </p>
      </Disclosure>
    ) : null}
    {message.content ? (
      <Bubble role={message.role}>{message.content}</Bubble>
    ) : null}
  </div>
);

const CallStep = ({
  call,
  result,
}: {
  call: ToolCall;
  result?: EvalMessage | undefined;
}) => {
  if (ASK_USER.test(call.function.name))
    return (
      <div className="flex flex-col gap-2">
        <div className="flex gap-2 rounded-xl border bg-card px-3.5 py-2.5 text-sm leading-6">
          <MessageCircleQuestion
            aria-hidden
            className="mt-1 size-4 shrink-0 text-muted-foreground"
          />
          <div className="min-w-0 whitespace-pre-wrap break-words">
            {questionOf(call)}
          </div>
        </div>
        {result?.content ? <Bubble role="user">{result.content}</Bubble> : null}
      </div>
    );

  return (
    <Disclosure
      className={cn(result?.is_error && "border-red-200")}
      summary={
        <>
          <Wrench
            aria-hidden
            className="size-3.5 shrink-0 text-muted-foreground"
          />
          <span className="shrink-0 font-mono font-medium">
            {call.function.name}
          </span>
          <span className="min-w-0 truncate font-mono text-muted-foreground">
            {argsPreview(call.function.arguments)}
          </span>
          {result?.is_error ? (
            <span className="ml-auto shrink-0 rounded bg-red-50 px-1.5 py-0.5 text-[11px] text-red-700">
              Error
            </span>
          ) : null}
        </>
      }
    >
      <div className="flex flex-col gap-2">
        <span className="text-[11px] text-muted-foreground">Arguments</span>
        <Code>{pretty(call.function.arguments)}</Code>
        {result ? (
          <>
            <span className="text-[11px] text-muted-foreground">Result</span>
            <Code>{pretty(result.content ?? "")}</Code>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">
            No result recorded.
          </span>
        )}
      </div>
    </Disclosure>
  );
};

const GROUP_AFTER = 4;

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
    <div className="flex min-w-0 flex-col gap-2">{blocks}</div>
  ) : (
    <p className="text-sm text-muted-foreground">No trace recorded.</p>
  );
};

const StepView = ({ step }: { step: Step }) =>
  step.kind === "message" ? (
    <MessageStep message={step.message} />
  ) : (
    <CallStep call={step.call} result={step.result} />
  );
