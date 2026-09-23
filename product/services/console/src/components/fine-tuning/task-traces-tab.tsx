import { useMemo, useState } from "react";

import { TraceSheet } from "@/components/fine-tuning/trace-sheet";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatLatency, formatNanoUsd } from "@/lib/format";
import type { TaskRow } from "@/store/fine-tuning-types";
import { traceSummaries } from "@/store/fine-tuning-views";
import { useMockFineTuning } from "@/store/mock-fine-tuning";

const TRACES_PAGE = 20;

const traceStart = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export const TaskTracesTab = ({ task }: { task: TaskRow }) => {
  const traces = useMockFineTuning((state) => state.traces);
  const conversations = useMockFineTuning((state) => state.conversations);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [tracesShown, setTracesShown] = useState(TRACES_PAGE);

  const summaries = useMemo(
    () => traceSummaries(traces, task.slug),
    [traces, task.slug],
  );
  const selectedTrace =
    summaries.find((trace) => trace.trace_id === selectedTraceId) ?? null;
  const selectedGenerations = useMemo(
    () =>
      traces
        .filter((row) => row.trace_id === selectedTraceId)
        .toSorted((a, b) => a.captured_at.localeCompare(b.captured_at)),
    [traces, selectedTraceId],
  );

  return (
    <>
      <p className="mb-3 text-sm text-muted-foreground">
        Sampled from your production traffic, these are used to fine-tune a
        model.
      </p>
      <section className="overflow-hidden rounded-lg border bg-card">
        {summaries.length ? (
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-11 pl-5">Trace</TableHead>
                <TableHead className="h-11 px-4">Started</TableHead>
                <TableHead className="h-11 px-4 text-right">
                  Generations
                </TableHead>
                <TableHead className="h-11 px-4 text-right">Duration</TableHead>
                <TableHead className="h-11 pr-5 text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summaries.slice(0, tracesShown).map((trace) => (
                <TableRow
                  key={trace.trace_id}
                  className="cursor-pointer"
                  onClick={() => setSelectedTraceId(trace.trace_id)}
                >
                  <TableCell className="h-14 pl-5 font-mono text-xs">
                    <button
                      type="button"
                      className="rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                    >
                      {trace.trace_id}
                    </button>
                  </TableCell>
                  <TableCell className="px-4 text-muted-foreground">
                    {traceStart.format(new Date(trace.started_at))}
                  </TableCell>
                  <TableCell className="px-4 text-right tabular-nums">
                    {trace.generation_count}
                  </TableCell>
                  <TableCell className="px-4 text-right text-muted-foreground tabular-nums">
                    {formatLatency(trace.duration_ms)}
                  </TableCell>
                  <TableCell className="pr-5 text-right text-muted-foreground tabular-nums">
                    {formatNanoUsd(trace.cost_nano_usd)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="flex min-h-48 flex-col items-center justify-center px-6 text-center">
            <h3 className="font-medium">No traces yet</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Turn on trace capture in Settings.
            </p>
          </div>
        )}
      </section>
      {summaries.length > tracesShown ? (
        <Button
          variant="ghost"
          size="sm"
          className="mt-2"
          onClick={() => setTracesShown((shown) => shown + TRACES_PAGE)}
        >
          Show more
        </Button>
      ) : null}

      <TraceSheet
        trace={selectedTrace}
        generations={selectedGenerations}
        messages={
          selectedTrace ? (conversations[selectedTrace.trace_id] ?? []) : []
        }
        open={Boolean(selectedTrace)}
        onOpenChange={(open) => !open && setSelectedTraceId(null)}
      />
    </>
  );
};
