import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { ChevronRight, GitBranch } from "lucide-react";
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

export const TaskTracesTab = ({ task }: { task: { name: string } }) => {
  const { organizationId, workspaceId } = useProductContext();
  return (
    <StoredTraces
      key={`${organizationId}:${workspaceId}:${task.name}`}
      organization={organizationId}
      workspace={workspaceId}
      task={task.name}
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
    staleTime: 300_000,
    refetchInterval: 300_000,
    refetchOnWindowFocus: "always",
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
      <section
        aria-label="Traces"
        aria-busy={query.isPending}
        className="overflow-hidden rounded-lg border bg-card"
      >
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow>
              <TableHead>Trace</TableHead>
              <TableHead>Started</TableHead>
              <TableHead className="text-right">Generations</TableHead>
              <TableHead>Sources</TableHead>
              <TableHead className="w-10">
                <span className="sr-only">Open trace</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.isPending
              ? Array.from({ length: 6 }, (_, index) => (
                  <TableRow key={`loading-${index}`} aria-hidden="true">
                    <TableCell>
                      <Skeleton className="h-4 w-48" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-36" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="ml-auto h-5 w-8" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-5 w-16" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="size-4" />
                    </TableCell>
                  </TableRow>
                ))
              : null}
            {traces.map((trace) => (
              <TableRow
                key={trace.id}
                onClick={() => setSelectedTrace(trace.id)}
                className="group cursor-pointer transition-colors hover:bg-muted/40 data-[state=selected]:bg-muted/60"
                data-state={selectedTrace === trace.id ? "selected" : undefined}
              >
                <TableCell className="py-3">
                  <div className="flex items-center gap-3">
                    <GitBranch className="size-4 shrink-0 text-muted-foreground" />
                    <button
                      className="max-w-80 truncate text-sm font-medium group-hover:underline focus-visible:underline"
                      onClick={() => setSelectedTrace(trace.id)}
                    >
                      {trace.id}
                    </button>
                  </div>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground tabular-nums">
                  {new Date(trace.rows[0]!.started_at).toLocaleString(
                    undefined,
                    { dateStyle: "medium", timeStyle: "medium" },
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <Badge variant="secondary" className="tabular-nums">
                    {trace.rows.length}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {[...new Set(trace.rows.map((row) => row.source))].map(
                      (source) => (
                        <Badge
                          key={source}
                          variant="outline"
                          className="text-xs font-normal"
                        >
                          {source}
                        </Badge>
                      ),
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <ChevronRight className="size-4 text-muted-foreground" />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {!traces.length && !query.isPending ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            {!task
              ? "Choose a task to view its traces."
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
  return (
    <ol aria-label="Trace timeline" className="space-y-6 p-4">
      {rows.map((row, index) => (
        <li
          key={row.generation_id}
          className="relative border-l-2 border-muted pl-5"
        >
          <span className="absolute -left-1.5 top-2 size-2.5 rounded-full bg-primary" />
          <GenerationContent
            organization={organization}
            workspace={workspace}
            row={row}
            index={index}
          />
        </li>
      ))}
    </ol>
  );
};

const GenerationContent = ({
  organization,
  workspace,
  row,
  index,
}: {
  organization: string;
  workspace: string;
  row: StoredGeneration;
  index: number;
}) => {
  const content = useQuery({
    queryKey: ["trace-content", organization, workspace, row.generation_id],
    queryFn: () => getTraceGeneration(organization, workspace, row),
    gcTime: 0,
    retry: 1,
  });
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>Generation {index + 1}</span>
        <time dateTime={row.started_at}>
          {new Date(row.started_at).toLocaleString()}
        </time>
      </div>
      <section className="space-y-2 rounded-lg border bg-card p-4">
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
