import type {
  EvalCheck,
  EvalMessage,
  EvalMetric,
  EvalModel,
  EvalRollout,
} from "@gradiated/contracts";
import { ChevronLeft, ChevronRight, CircleCheck, CircleX } from "lucide-react";
import { useState } from "react";

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
import { MODEL_COLORS, TagChip } from "./eval-blocks";
import type { EvalView } from "./eval-context";
import { TraceView } from "./trace-view";

const Conversation = ({
  index,
  caseId,
}: {
  index: EvalIndex;
  caseId: string;
}) => {
  const messages = index.caseById
    .get(caseId)!
    .messages.filter((message) => message.content);
  const [showAll, setShowAll] = useState(false);
  const hidden = showAll ? 0 : Math.max(0, messages.length - 3);

  return (
    <section className="flex min-w-0 flex-col gap-2 rounded-xl border bg-card px-5 py-4">
      <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        Conversation
      </h3>
      {hidden ? (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="self-start text-xs text-muted-foreground hover:text-foreground"
        >
          Show {hidden} earlier messages
        </button>
      ) : null}
      {messages.slice(hidden).map((message, position, shown) => {
        const last = position === shown.length - 1;

        return (
          <div
            key={position}
            className={cn(
              "max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm leading-6 whitespace-pre-wrap break-words",
              message.role === "user" ? "self-end" : "self-start bg-muted",
              message.role === "user" &&
                (last ? "bg-foreground text-background" : "bg-muted"),
            )}
          >
            {last && message.role === "user" ? (
              <span className="mb-1 block text-[11px] opacity-70">
                Case request
              </span>
            ) : null}
            {message.content}
          </div>
        );
      })}
    </section>
  );
};

const asText = (value: unknown) =>
  typeof value === "string" ? value : JSON.stringify(value, null, 2);

const Output = ({ value }: { value: unknown }) => (
  <pre className="max-h-64 overflow-auto rounded-md bg-muted px-3 py-2 font-mono text-xs leading-5 whitespace-pre-wrap break-words">
    {asText(value)}
  </pre>
);

const Expected = ({ index, caseId }: { index: EvalIndex; caseId: string }) => {
  const { expected, expected_output: output } = index.caseById.get(caseId)!;
  if (!expected.length && output === undefined) return null;

  return (
    <section className="flex min-w-0 flex-col gap-2 rounded-xl border bg-card px-5 py-4">
      <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        Expected{expected.length ? ` · ${expected.length}` : ""}
      </h3>
      {output === undefined ? null : <Output value={output} />}
      <table className="w-full text-sm">
        <tbody>
          {expected.map((row, position) => (
            <tr
              key={row.id ?? position}
              className="border-b align-top last:border-0"
            >
              <td className="py-1.5 pr-3">{row.group}</td>
              <td className="py-1.5 pr-3 text-muted-foreground">{row.label}</td>
              <td className="py-1.5 font-mono text-xs leading-5">
                {row.value}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
};

const Checks = ({ checks }: { checks: EvalCheck[] }) => {
  const [showAll, setShowAll] = useState(false);
  const groups = [
    {
      title: "Wrong or missing",
      rows: checks.filter(
        (check) => check.status === "wrong" || check.status === "missing",
      ),
    },
    {
      title: "Not requested",
      rows: checks.filter((check) => check.status === "unexpected"),
    },
  ].filter((group) => group.rows.length);
  if (!groups.length) return null;

  let budget = showAll ? Infinity : 6;
  const total = groups.reduce((sum, group) => sum + group.rows.length, 0);

  return (
    <div className="flex flex-col gap-1">
      <table className="w-full table-fixed text-xs">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="py-1 font-normal">Record</th>
            <th className="py-1 font-normal">Field</th>
            <th className="py-1 font-normal">Expected</th>
            <th className="py-1 font-normal">This rollout</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => {
            const rows = group.rows.slice(0, Math.max(0, budget));
            budget -= rows.length;
            if (!rows.length) return null;

            return [
              <tr key={group.title}>
                <td colSpan={4} className="pt-2 pb-1 font-medium">
                  {group.title} · {group.rows.length}
                </td>
              </tr>,
              ...rows.map((check, position) => (
                <tr
                  key={`${group.title}-${position}`}
                  className="border-t align-top"
                >
                  <td className="py-1.5 pr-2 break-words">
                    {check.group ?? "—"}
                  </td>
                  <td className="py-1.5 pr-2 break-words text-muted-foreground">
                    {check.label}
                  </td>
                  <td className="py-1.5 pr-2 font-mono break-words">
                    {check.expected ?? "—"}
                  </td>
                  <td className="py-1.5 font-mono break-words">
                    <span
                      className={
                        check.status === "missing"
                          ? "text-muted-foreground"
                          : "text-red-700"
                      }
                    >
                      {check.actual ?? "—"}
                    </span>
                    {check.status === "missing" ? (
                      <span className="block font-sans text-[11px] text-muted-foreground">
                        Not changed
                      </span>
                    ) : null}
                  </td>
                </tr>
              )),
            ];
          })}
        </tbody>
      </table>
      {!showAll && total > 6 ? (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="self-start text-xs text-muted-foreground hover:text-foreground"
        >
          Show {total - 6} more
        </button>
      ) : null}
    </div>
  );
};

const Result = ({
  rollout,
  metric,
}: {
  rollout: EvalRollout;
  metric: EvalMetric;
}) => {
  const passed = passedOf(rollout, metric);
  const counts = checkCounts(rollout);
  const expected = counts.passed + counts.wrong + counts.missing;
  const calls = rollout.messages.reduce(
    (sum, message) => sum + (message.tool_calls?.length ?? 0),
    0,
  );
  const stats = [
    calls ? `${calls} tool calls` : null,
    rollout.usage?.output_tokens
      ? `${rollout.usage.output_tokens.toLocaleString()} output tokens`
      : null,
    rollout.duration_ms ? `${Math.round(rollout.duration_ms / 1000)} s` : null,
  ].filter(Boolean);

  if (rollout.status !== "completed")
    return (
      <div className="rounded-lg border border-dashed px-4 py-3 text-sm">
        <p className="font-medium">Didn’t complete ({rollout.status})</p>
        {rollout.error ? (
          <p className="text-xs text-muted-foreground">{rollout.error}</p>
        ) : null}
        <p className="text-xs text-muted-foreground">Left out of the scores.</p>
      </div>
    );

  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-lg border-l-4 bg-muted/40 px-4 py-3",
        passed === false
          ? "border-l-red-600"
          : passed
            ? "border-l-[#6e7f31]"
            : "border-l-border",
      )}
    >
      <div className="flex items-center gap-2">
        {passed === null ? null : passed ? (
          <CircleCheck aria-hidden className="size-5 text-[#6e7f31]" />
        ) : (
          <CircleX aria-hidden className="size-5 text-red-600" />
        )}
        <span className="text-base font-semibold">
          {metric.kind === "pass"
            ? passed === null
              ? "Not scored"
              : passed
                ? "Passed"
                : "Failed"
            : `${metric.name}: ${formatMetric(metric, scoreOf(rollout, metric))}`}
        </span>
      </div>
      {expected ? (
        <>
          <p className="text-sm">
            {counts.passed} of {expected} expected changes made
            {counts.unexpected ? ` · ${counts.unexpected} not requested` : ""}
          </p>
          <div className="flex h-1.5 overflow-hidden rounded-full bg-muted">
            <span className="bg-[#6e7f31]" style={{ flex: counts.passed }} />
            <span
              className="bg-red-500"
              style={{ flex: counts.wrong + counts.missing }}
            />
            <span
              className="bg-amber-400"
              style={{ flex: counts.unexpected }}
            />
          </div>
        </>
      ) : null}
      {rollout.output === undefined ? null : <Output value={rollout.output} />}
      {rollout.explanation ? (
        <p className="text-sm text-muted-foreground">{rollout.explanation}</p>
      ) : null}
      {stats.length ? (
        <p className="text-xs text-muted-foreground">{stats.join(" · ")}</p>
      ) : null}
    </div>
  );
};

const same = (left?: EvalMessage, right?: EvalMessage) =>
  left?.role === right?.role && left?.content === right?.content;

// Traces repeat either the whole case conversation or only its final request.
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
  color,
  metric,
}: {
  index: EvalIndex;
  caseId: string;
  model: EvalModel;
  color: string;
  metric: EvalMetric;
}) => {
  const rollouts = rolloutsOf(index, caseId, model.id);
  const [selected, setSelected] = useState(0);
  const rollout = rollouts[Math.min(selected, rollouts.length - 1)];

  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border bg-card px-5 py-4">
      <div className="flex flex-col gap-0.5">
        <span className="flex items-center gap-2 font-semibold">
          <span
            aria-hidden
            className="size-2.5 rounded-sm"
            style={{ background: color }}
          />
          {model.name}
        </span>
        {model.description ? (
          <span className="text-xs text-muted-foreground">
            {model.description}
          </span>
        ) : null}
        {model.setup?.notes ? (
          <span className="text-xs text-muted-foreground">
            {model.setup.notes}
          </span>
        ) : null}
      </div>
      {rollouts.length ? (
        <>
          <div
            role="tablist"
            aria-label={`${model.name} rollouts`}
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
                    "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs",
                    item === rollout
                      ? "border-foreground"
                      : "text-muted-foreground",
                  )}
                >
                  {passed === null ? null : passed ? (
                    <CircleCheck
                      aria-hidden
                      className="size-3.5 text-[#6e7f31]"
                    />
                  ) : (
                    <CircleX aria-hidden className="size-3.5 text-red-600" />
                  )}
                  Rollout {position + 1}
                  {metric.kind === "pass"
                    ? null
                    : ` · ${formatMetric(metric, scoreOf(item, metric))}`}
                </button>
              );
            })}
          </div>
          {rollout ? (
            <>
              <Result rollout={rollout} metric={metric} />
              <Checks checks={rollout.checks} />
              <h4 className="pt-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                Trace
              </h4>
              <TraceView
                messages={withoutPrefix(
                  rollout.messages,
                  index.caseById.get(caseId)!.messages,
                )}
              />
            </>
          ) : null}
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          No rollouts for this case.
        </p>
      )}
    </section>
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
          <div className="flex flex-col gap-4 px-6 py-5">
            <div className="flex flex-wrap items-center justify-between gap-3 pr-8">
              <span className="text-xs text-muted-foreground">
                {index.eval.title}
              </span>
              {position >= 0 ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground tabular-nums">
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
            <div className="flex flex-col gap-2">
              <SheetTitle className="text-xl font-semibold tracking-tight">
                {item.title}
              </SheetTitle>
              <SheetDescription className="flex flex-wrap gap-1">
                {Object.entries(item.tags).map(([key, value]) => (
                  <TagChip key={key} name={key} value={value} />
                ))}
              </SheetDescription>
              {item.description ? (
                <p className="text-sm text-muted-foreground">
                  {item.description}
                </p>
              ) : null}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Conversation index={index} caseId={item.id} />
              <Expected index={index} caseId={item.id} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              {pickModels(index, view?.models).map((model, slot) => (
                <ModelColumn
                  key={`${item.id}-${model.id}`}
                  index={index}
                  caseId={item.id}
                  model={model}
                  color={MODEL_COLORS[slot] ?? MODEL_COLORS[0]}
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
