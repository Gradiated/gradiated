import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  getTraceGeneration,
  listTraceGenerations,
  type StoredGeneration,
} from "@/api/traces";
import { useProductContext } from "@/hooks/use-product-context";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export const TaskTracesTab = ({ task }: { task: { slug: string } }) => {
  const { organizationId, workspaceId } = useProductContext();
  return (
    <StoredTraces
      key={`${organizationId}:${workspaceId}:${task.slug}`}
      organization={organizationId}
      workspace={workspaceId}
      task={task.slug}
    />
  );
};
const StoredTraces = ({
  organization,
  workspace,
  task,
}: {
  organization: string;
  workspace: string;
  task: string;
}) => {
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const query = useInfiniteQuery({
    queryKey: ["trace-generations", organization, workspace, task],
    queryFn: ({ pageParam }) =>
      listTraceGenerations(organization, workspace, task, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: Boolean(organization && workspace && task),
    gcTime: 0,
  });
  const traces = useMemo(() => {
    const generations = new Map<string, StoredGeneration>();
    for (const page of query.data?.pages ?? [])
      for (const row of page.data) generations.set(row.generation_id, row);
    const groups = new Map<string, StoredGeneration[]>();
    for (const row of generations.values())
      groups.set(row.trace_id, [...(groups.get(row.trace_id) ?? []), row]);
    return [...groups]
      .map(([id, rows]) => ({
        id,
        rows: rows.sort((a, b) => a.started_at.localeCompare(b.started_at)),
      }))
      .sort((a, b) =>
        b.rows[0]!.started_at.localeCompare(a.rows[0]!.started_at),
      );
  }, [query.data]);
  const selected = traces.find((trace) => trace.id === selectedTrace);
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Button
          variant="outline"
          disabled={!task || query.isFetching}
          onClick={() => void query.refetch()}
        >
          Refresh
        </Button>
      </div>
      <p className="mb-3 text-sm text-muted-foreground">
        Captured requests and responses for this workspace. New content usually
        appears within a minute. Relayed content is not used for automatic
        training.
      </p>
      {query.error ? (
        <p role="alert" className="mb-3 text-sm text-destructive">
          Could not load traces. {query.error.message}{" "}
          <button onClick={() => void query.refetch()}>Retry</button>
        </p>
      ) : null}
      <section className="overflow-hidden rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Trace</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Loaded generations</TableHead>
              <TableHead>Sources</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {traces.map((trace) => (
              <TableRow
                key={trace.id}
                onClick={() => setSelectedTrace(trace.id)}
                className="cursor-pointer"
              >
                <TableCell>
                  <button
                    className="max-w-80 truncate font-mono text-xs"
                    onClick={() => setSelectedTrace(trace.id)}
                  >
                    {trace.id}
                  </button>
                </TableCell>
                <TableCell>
                  {new Date(trace.rows[0]!.started_at).toLocaleString()}
                </TableCell>
                <TableCell>{trace.rows.length}</TableCell>
                <TableCell>
                  {[...new Set(trace.rows.map((row) => row.source))].join(", ")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {!traces.length ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            {!task
              ? "Choose a task to view its traces."
              : query.isPending
                ? "Loading traces…"
                : "No traces in the loaded hours. Load older content, or enable capture in Settings and send a request with this task."}
          </div>
        ) : null}
      </section>
      {query.hasNextPage ? (
        <Button
          variant="ghost"
          className="mt-3"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          {query.isFetchingNextPage ? "Loading…" : "Load older content"}
        </Button>
      ) : null}
      <Sheet
        open={Boolean(selected)}
        onOpenChange={(open) => {
          if (!open) setSelectedTrace(null);
        }}
      >
        <SheetContent className="overflow-y-auto sm:max-w-3xl">
          <SheetHeader>
            <SheetTitle>Trace</SheetTitle>
            <SheetDescription className="break-all">
              {selected?.id}. Generations from the loaded pages; load older
              content to include earlier hours.
            </SheetDescription>
          </SheetHeader>
          {selected ? (
            <StoredContent
              organization={organization}
              workspace={workspace}
              rows={selected.rows}
            />
          ) : null}
        </SheetContent>
      </Sheet>
    </>
  );
};
const StoredContent = ({
  organization,
  workspace,
  rows,
}: {
  organization: string;
  workspace: string;
  rows: StoredGeneration[];
}) => {
  const [selected, setSelected] = useState(rows[0]!.generation_id);
  const row = rows.find((row) => row.generation_id === selected) ?? rows[0]!;
  const content = useQuery({
    queryKey: ["trace-content", organization, workspace, row.generation_id],
    queryFn: () => getTraceGeneration(organization, workspace, row),
    gcTime: 0,
    retry: 1,
  });
  return (
    <div className="space-y-4 p-4">
      <label className="flex flex-col gap-2 text-sm">
        Generation
        <select
          className="rounded-md border bg-background p-2"
          aria-label="Generation"
          value={row.generation_id}
          onChange={(event) => setSelected(event.target.value)}
        >
          {rows.map((row) => (
            <option key={row.generation_id} value={row.generation_id}>
              {new Date(row.started_at).toLocaleString()} · {row.model}
            </option>
          ))}
        </select>
      </label>
      <section className="space-y-2 rounded-lg border p-4">
        <h3 className="font-medium">{row.model}</h3>
        <p className="text-xs text-muted-foreground">
          {row.source} · {row.outcome ?? "Unknown outcome"} · HTTP{" "}
          {row.status ?? "—"}
        </p>
        <p className="break-all font-mono text-xs">{row.generation_id}</p>
        {row.usage ? (
          <p className="text-xs">Usage: {JSON.stringify(row.usage)}</p>
        ) : null}
        {content.isPending ? (
          <p>Loading content…</p>
        ) : content.error ? (
          <p role="alert">
            Content unavailable.{" "}
            <button onClick={() => void content.refetch()}>Retry</button>
          </p>
        ) : (
          <>
            {["request", "response"].map((key) => (
              <div key={key}>
                <h4 className="my-2 text-sm font-medium capitalize">{key}</h4>
                <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap break-words">
                  {JSON.stringify(content.data?.raw?.[key] ?? null, null, 2)}
                </pre>
              </div>
            ))}
          </>
        )}
      </section>
    </div>
  );
};
