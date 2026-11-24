import type {
  EvalCheck,
  EvalMessage,
  EvalMetric,
  EvalModel,
  EvalRollout,
} from "@gradiated/contracts";
import { Check, ChevronLeft, ChevronRight, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  checkCounts,
  formatMetric,
  passedOf,
  pickMetric,
  pickModels,
  rolloutsOf,
  scoreOf,
  type EvalIndex,
} from "@/lib/eval-data";
import { cn } from "@/lib/utils";
import type { EvalView } from "./eval-context";
import { ModelMark, SectionLabel } from "./eval-ui";
import { TraceView } from "./trace-view";

const Card = ({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) => (
  <section
    className={cn("flex min-w-0 flex-col rounded-xl border bg-card", className)}
  >
    {children}
  </section>
);

const LABELS = {
  system: "System",
  user: "User",
  assistant: "Assistant",
  tool: "Tool",
};
const CONTEXT_CHARS = 400;

const Request = ({ messages }: { messages: EvalMessage[] }) => {
  const shown = messages.filter(
    (message): message is EvalMessage & { role: keyof typeof LABELS } =>
      message.role in LABELS && Boolean(message.content),
  );
  const request = shown.findLastIndex((message) => message.role === "user");
  const earlier = shown.slice(0, Math.max(request, 0));
  const [open, setOpen] = useState(false);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <span className="text-xs text-muted-foreground">Request</span>
      {earlier.length ? (
        open ? (
          <div className="flex flex-col gap-2 border-l-2 pl-3">
            {earlier.map((message, position) => (
              <p
                key={position}
                className="text-[13px] leading-5 break-words whitespace-pre-wrap text-muted-foreground"
              >
                <span className="font-medium text-foreground/70">
                  {LABELS[message.role]}:
                </span>{" "}
                {message.content!.length > CONTEXT_CHARS
                  ? `${message.content!.slice(0, CONTEXT_CHARS)}…`
                  : message.content}
              </p>
            ))}
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="self-start text-xs text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
          >
            Show {earlier.length} earlier{" "}
            {earlier.length === 1 ? "message" : "messages"}
          </button>
        )
      ) : null}
      {request >= 0 ? (
        <p className="text-[15px] leading-6 break-words whitespace-pre-wrap">
          {shown[request]!.content}
        </p>
      ) : null}
    </div>
  );
};

const asText = (value: unknown) =>
  typeof value === "string" ? value : JSON.stringify(value, null, 2);

const Expected = ({ index, caseId }: { index: EvalIndex; caseId: string }) => {
  const { expected, expected_output: output } = index.caseById.get(caseId)!;
  if (!expected.length && output === undefined) return null;

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <span className="text-xs text-muted-foreground">
        {expected.length === 1 ? "Expected change" : "Expected"}
        {expected.length > 1 ? ` · ${expected.length} changes` : ""}
      </span>
      {output !== undefined ? (
        <pre className="max-h-64 overflow-auto rounded-md bg-muted/70 px-3 py-2 font-mono text-xs leading-5 whitespace-pre-wrap">
          {asText(output)}
        </pre>
      ) : null}
      {expected.length ? (
        <ul className="flex flex-col gap-2.5">
          {expected.map((row, position) => (
            <li key={row.id ?? position} className="flex flex-col gap-0.5">
              <span className="text-[15px] leading-6">
                {row.label} <span className="text-muted-foreground">→</span>{" "}
                <span className="font-mono text-[13px]">{row.value}</span>
              </span>
              {row.group ? (
                <span className="text-[13px] leading-5 text-muted-foreground">
                  {row.group}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};

const SHOWN_CHECKS = 5;

const Checks = ({ checks }: { checks: EvalCheck[] }) => {
  const [all, setAll] = useState(false);
  const groups = [
    {
      title: "Wrong or missing",
      dot: "bg-red-600",
      rows: checks.filter(
        (check) => check.status === "wrong" || check.status === "missing",
      ),
    },
    {
      title: "Not requested",
      dot: "bg-amber-500",
      rows: checks.filter((check) => check.status === "unexpected"),
    },
  ].filter((group) => group.rows.length);
  if (!groups.length) return null;

  const total = groups.reduce((sum, group) => sum + group.rows.length, 0);
  let budget = all ? Infinity : SHOWN_CHECKS;

  return (
    <div className="overflow-hidden rounded-lg border">
      <table className="w-full table-fixed text-[13px]">
        <colgroup>
          <col className="w-[22%]" />
          <col className="w-[22%]" />
          <col />
          <col />
        </colgroup>
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="px-3 py-2 font-normal">Record</th>
            <th className="px-3 py-2 font-normal">Field</th>
            <th className="px-3 py-2 font-normal">Expected</th>
            <th className="px-3 py-2 font-normal">This run</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => {
            const rows = group.rows.slice(0, Math.max(0, budget));
            budget -= rows.length;
            if (!rows.length) return null;

            return [
              <tr key={group.title} className="border-b bg-muted/50">
                <td colSpan={4} className="px-3 py-1.5 text-xs">
                  <span className="inline-flex items-center gap-1.5">
                    <span className={cn("size-1.5 rounded-full", group.dot)} />
                    {group.title}
                    <span className="text-muted-foreground">
                      · {group.rows.length}
                    </span>
                  </span>
                </td>
              </tr>,
              ...rows.map((check, position) => (
                <tr
                  key={`${group.title}-${position}`}
                  className="border-b align-top last:border-0"
                >
                  <td className="px-3 py-2 break-words">
                    {check.group ?? "—"}
                  </td>
                  <td className="px-3 py-2 break-words">{check.label}</td>
                  <td className="px-3 py-2 font-mono text-xs leading-5 break-words">
                    {check.expected ?? "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs leading-5 break-words">
                    {check.status === "missing" ? (
                      <span className="text-muted-foreground">
                        {check.actual ?? "—"}
                        <span className="block font-sans text-[11px]">
                          not changed
                        </span>
                      </span>
                    ) : (
                      <span className="text-[#bb322b]">
                        {check.actual ?? "—"}
                      </span>
                    )}
                  </td>
                </tr>
              )),
            ];
          })}
        </tbody>
      </table>
      {!all && total > SHOWN_CHECKS ? (
        <button
          type="button"
          onClick={() => setAll(true)}
          className="w-full border-t px-3 py-2 text-left text-xs text-muted-foreground hover:text-foreground"
        >
          Show {total - SHOWN_CHECKS} more
        </button>
      ) : null}
    </div>
  );
};

const plural = (count: number, word: string) =>
  `${count.toLocaleString()} ${word}${count === 1 ? "" : "s"}`;

const Result = ({
  rollout,
  messages,
  metric,
}: {
  rollout: EvalRollout;
  messages: EvalMessage[];
  metric: EvalMetric;
}) => {
  if (rollout.status !== "completed")
    return (
      <div className="flex flex-col gap-3 border-l-4 border-l-border px-5 py-4">
        <div className="flex flex-col gap-1">
          <p className="font-semibold">Didn’t finish</p>
          <p className="text-[13px] text-muted-foreground">
            {rollout.error ?? `The run ended with ${rollout.status}.`} Left out
            of the scores.
          </p>
        </div>
        <Checks checks={rollout.checks} />
      </div>
    );

  const passed = passedOf(rollout, metric);
  const counts = checkCounts(rollout);
  const expected = counts.passed + counts.wrong + counts.missing;
  const calls = messages.reduce(
    (sum, message) => sum + (message.tool_calls?.length ?? 0),
    0,
  );
  const replies = messages.filter((message) => message.role === "user").length;
  const stats = [
    rollout.duration_ms ? `${(rollout.duration_ms / 1000).toFixed(1)} s` : null,
    calls ? plural(calls, "tool call") : null,
    replies ? plural(replies, "user reply") : null,
    rollout.usage?.output_tokens
      ? plural(rollout.usage.output_tokens, "output token")
      : null,
  ].filter(Boolean);
  const title =
    metric.kind !== "pass"
      ? `${metric.name}: ${formatMetric(metric, scoreOf(rollout, metric))}`
      : passed === null
        ? "Not scored"
        : passed
          ? "Passed"
          : "Failed";

  return (
    <div
      className={cn(
        "flex flex-col gap-3 border-l-4 px-5 py-4",
        passed === false
          ? "border-l-[#bb322b]"
          : passed
            ? "border-l-[#8aa63a]"
            : "border-l-border",
      )}
    >
      <div className="flex items-center gap-3">
        {passed === null ? null : (
          <span
            className={cn(
              "grid size-9 shrink-0 place-items-center rounded-full",
              passed
                ? "bg-[#f2f7d9] text-[#475617]"
                : "bg-[#fcecea] text-[#bb322b]",
            )}
          >
            {passed ? (
              <Check aria-hidden className="size-4.5" />
            ) : (
              <X aria-hidden className="size-4.5" />
            )}
          </span>
        )}
        <div className="flex flex-col">
          <span className="text-base leading-6 font-semibold">{title}</span>
          {expected ? (
            <span className="text-[13px] text-muted-foreground">
              {counts.passed} of {expected} expected changes made
              {counts.unexpected ? ` · ${counts.unexpected} not requested` : ""}
            </span>
          ) : null}
        </div>
      </div>
      {expected ? (
        <div className="flex h-1.5 gap-px overflow-hidden rounded-full">
          <span className="bg-[#8aa63a]" style={{ flex: counts.passed }} />
          <span
            className="bg-[#e07a72]"
            style={{ flex: counts.wrong + counts.missing }}
          />
          <span className="bg-[#e4c880]" style={{ flex: counts.unexpected }} />
        </div>
      ) : null}
      {stats.length ? (
        <p className="text-[13px] text-muted-foreground">{stats.join(" · ")}</p>
      ) : null}
      {rollout.output !== undefined ? (
        <pre className="max-h-64 overflow-auto rounded-md bg-muted/70 px-3 py-2 font-mono text-xs leading-5 whitespace-pre-wrap">
          {asText(rollout.output)}
        </pre>
      ) : null}
      {rollout.explanation ? (
        <p className="text-[13px] text-muted-foreground">
          {rollout.explanation}
        </p>
      ) : null}
      <Checks checks={rollout.checks} />
    </div>
  );
};

const same = (left?: EvalMessage, right?: EvalMessage) =>
  left?.role === right?.role && left?.content === right?.content;

// Traces repeat either the whole task conversation or only its final request.
const withoutPrefix = (messages: EvalMessage[], prefix: EvalMessage[]) => {
  if (
    prefix.length &&
    prefix.every((message, at) => same(message, messages[at]))
  )
    return messages.slice(prefix.length);

  return same(messages[0], prefix.at(-1)) ? messages.slice(1) : messages;
};

const ModelColumn = ({
  index,
  caseId,
  model,
  metric,
}: {
  index: EvalIndex;
  caseId: string;
  model: EvalModel;
  metric: EvalMetric;
}) => {
  const rollouts = rolloutsOf(index, caseId, model.id);
  const [selected, setSelected] = useState(0);
  const rollout = rollouts[Math.min(selected, rollouts.length - 1)];
  const messages = rollout
    ? withoutPrefix(rollout.messages, index.caseById.get(caseId)!.messages)
    : [];

  return (
    <Card>
      <div className="flex flex-col gap-3 px-5 pt-4 pb-3">
        <div className="flex items-center gap-2.5">
          <ModelMark model={model} boxed />
          <div className="flex min-w-0 flex-col">
            <span className="text-[15px] leading-5 font-semibold">
              {model.name}
            </span>
            {model.description ? (
              <span className="text-xs text-muted-foreground">
                {model.description}
              </span>
            ) : null}
          </div>
        </div>
        {rollouts.length ? (
          <div
            role="tablist"
            aria-label={`${model.name} runs`}
            className="flex flex-wrap gap-1.5"
          >
            {rollouts.map((item, position) => {
              const passed = passedOf(item, metric);

              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={item === rollout}
                  onClick={() => setSelected(position)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[13px]",
                    item === rollout
                      ? "border-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {passed === null ? null : (
                    <span
                      className={cn(
                        "grid size-3.5 place-items-center rounded-full",
                        passed
                          ? "bg-[#f2f7d9] text-[#475617]"
                          : "bg-[#fcecea] text-[#bb322b]",
                      )}
                    >
                      {passed ? (
                        <Check aria-hidden className="size-2.5" />
                      ) : (
                        <X aria-hidden className="size-2.5" />
                      )}
                    </span>
                  )}
                  Run {position + 1}
                </button>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No runs for this task.
          </p>
        )}
      </div>
      {rollout ? (
        <>
          <div className="border-t">
            <Result rollout={rollout} messages={messages} metric={metric} />
          </div>
          <div className="flex flex-col gap-3 border-t px-5 py-4">
            <SectionLabel>Rollout</SectionLabel>
            <TraceView messages={messages} />
          </div>
        </>
      ) : null}
    </Card>
  );
};

export const EvalCasePanel = ({
  index,
  caseId,
  order,
  view,
  onNavigate,
  onClose,
}: {
  index: EvalIndex | null;
  caseId: string | null;
  order: readonly string[];
  view?: EvalView | undefined;
  onNavigate: (caseId: string) => void;
  onClose: () => void;
}) => {
  const item = index && caseId ? index.caseById.get(caseId) : undefined;
  const position = caseId ? order.indexOf(caseId) : -1;

  return (
    <Sheet
      open={Boolean(item)}
      onOpenChange={(open) => (open ? null : onClose())}
    >
      <SheetContent
        side="right"
        className="w-full overflow-y-auto bg-background p-0 sm:max-w-[min(1440px,96vw)]"
      >
        {index && item ? (
          <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 px-8 py-6">
            <div className="flex flex-wrap items-center justify-between gap-3 pr-8">
              <span className="text-[13px] text-muted-foreground">
                {index.eval.title}
              </span>
              {position >= 0 ? (
                <div className="flex items-center gap-2">
                  <span className="mr-1 text-[13px] text-muted-foreground tabular-nums">
                    {position + 1} of {order.length}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={position <= 0}
                    onClick={() => onNavigate(order[position - 1]!)}
                  >
                    <ChevronLeft aria-hidden /> Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={position >= order.length - 1}
                    onClick={() => onNavigate(order[position + 1]!)}
                  >
                    Next <ChevronRight aria-hidden />
                  </Button>
                </div>
              ) : null}
            </div>
            <div className="flex flex-col gap-2.5">
              <SheetTitle className="text-2xl leading-8 font-semibold tracking-[-0.01em]">
                {item.title}
              </SheetTitle>
              <SheetDescription className="text-[13px] text-muted-foreground">
                {Object.values(item.tags).join(" · ")}
              </SheetDescription>
              {item.description ? (
                <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
                  {item.description}
                </p>
              ) : null}
            </div>
            <Card className="grid gap-6 px-5 py-4 lg:grid-cols-2">
              <Request messages={item.messages} />
              <Expected index={index} caseId={item.id} />
            </Card>
            <div className="grid items-start gap-4 lg:grid-cols-2">
              {pickModels(index, view?.models).map((model) => (
                <ModelColumn
                  key={`${item.id}-${model.id}`}
                  index={index}
                  caseId={item.id}
                  model={model}
                  metric={pickMetric(index, view?.metric)}
                />
              ))}
            </div>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
};
