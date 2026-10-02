import { ModelLabel } from "@/components/model-label";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { ChevronRight, GitBranch } from "lucide-react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import {
  getTraceGeneration,
  listTraceGenerations,
  type StoredGeneration,
} from "@/api/traces";
import { useInfiniteScroll } from "@/hooks/use-infinite-scroll";
import { useProductContext } from "@/hooks/use-product-context";
import {
  Sheet,
  SheetContent,
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
  const { traceId } = useSearch({ from: "/tasks/$taskId" });
  const navigate = useNavigate({ from: "/tasks/$taskId" });

  return (
    <StoredTraces
      key={`${organizationId}:${workspaceId}:${task.name}`}
      organization={organizationId}
      workspace={workspaceId}
      task={task.name}
      selectedTrace={traceId ?? null}
      onSelectTrace={(id) =>
        void navigate({
          search: id ? { traceId: id } : {},
          resetScroll: false,
        })
      }
    />
  );
};
const StoredTraces = ({
  organization,
  workspace,
  task,
  selectedTrace,
  onSelectTrace,
}: {
  organization: string;
  workspace: string;
  task: string;
  selectedTrace: string | null;
  onSelectTrace: (id: string | null) => void;
}) => {
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
  const { fetchNextPage, hasNextPage, isFetching, isError } = query;

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

  const loadMoreRef = useInfiniteScroll({
    ...query,
    enabled: !selectedTrace,
    autoLoad: Boolean(query.data?.pages.at(-1)?.data.length),
  });
  const traceLoadMoreRef = useInfiniteScroll({
    ...query,
    enabled: Boolean(selected),
    autoLoad: Boolean(
      query.data?.pages
        .at(-1)
        ?.data.some((row) => row.trace_id === selectedTrace),
    ),
  });

  useEffect(() => {
    if (selectedTrace && !selected && hasNextPage && !isFetching && !isError)
      void fetchNextPage({ cancelRefetch: false });
  }, [
    fetchNextPage,
    hasNextPage,
    isFetching,
    isError,
    selectedTrace,
    selected,
  ]);

  return (
    <>
      <p className="mb-3 text-sm text-muted-foreground">
        Captured requests and responses for this task.
      </p>
      {query.error ? (
        <p role="alert" className="mb-3 text-sm text-destructive">
          Could not load traces. {query.error.message}{" "}
          <button
            onClick={() =>
              void (query.isFetchNextPageError
                ? query.fetchNextPage()
                : query.refetch())
            }
          >
            Retry
          </button>
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
                onClick={() => onSelectTrace(trace.id)}
                className="group cursor-pointer transition-colors hover:bg-muted/40 data-[state=selected]:bg-muted/60"
                data-state={selectedTrace === trace.id ? "selected" : undefined}
              >
                <TableCell className="py-3">
                  <div className="flex items-center gap-3">
                    <GitBranch className="size-4 shrink-0 text-muted-foreground" />
                    <button className="max-w-80 truncate text-sm font-medium group-hover:underline focus-visible:underline">
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
                          className="text-xs font-normal capitalize"
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
            {query.isFetchingNextPage ? (
              <TableRow aria-hidden="true">
                {["w-48", "w-36", "w-8", "w-16", "w-4"].map((width, index) => (
                  <TableCell key={index} className="py-3">
                    <Skeleton className={`h-4 ${width}`} />
                  </TableCell>
                ))}
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
        {!traces.length && !query.isPending ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            {!task
              ? "Choose a task to view its traces."
              : query.hasNextPage
                ? "No traces in the loaded hours. Scroll to check earlier hours."
                : "No traces found. Enable capture in Settings and send a request with this task."}
          </div>
        ) : null}
      </section>
      {query.hasNextPage ? (
        <div
          ref={loadMoreRef}
          className="mt-3 h-4"
          role={query.isFetchingNextPage ? "status" : undefined}
          aria-label={
            query.isFetchingNextPage ? "Loading older content" : undefined
          }
        >
          {query.isFetchingNextPage ? (
            <span className="sr-only">Loading older content</span>
          ) : null}
        </div>
      ) : null}
      <Sheet
        open={Boolean(selectedTrace)}
        onOpenChange={(open) => {
          if (!open) onSelectTrace(null);
        }}
      >
        <SheetContent
          aria-describedby={undefined}
          className="overflow-y-auto sm:max-w-3xl"
        >
          <SheetHeader>
            <SheetTitle>Trace</SheetTitle>
          </SheetHeader>
          {selected ? (
            <>
              <StoredContent
                organization={organization}
                workspace={workspace}
                rows={selected.rows}
              />
              {query.isFetchingNextPage ? (
                <div
                  role="status"
                  aria-label="Loading earlier generations"
                  className="px-4 pb-4"
                >
                  <Skeleton className="h-48 w-full" />
                </div>
              ) : null}
              {query.isFetchNextPageError ? (
                <p role="alert" className="p-4 text-sm text-destructive">
                  Could not load earlier generations. {query.error?.message}{" "}
                  <button onClick={() => void query.fetchNextPage()}>
                    Retry
                  </button>
                </p>
              ) : null}
              {query.hasNextPage ? (
                <div ref={traceLoadMoreRef} className="h-4" />
              ) : null}
            </>
          ) : query.error ? (
            <p role="alert" className="p-4 text-sm text-destructive">
              Could not load traces. {query.error.message}{" "}
              <button
                onClick={() =>
                  void (query.isFetchNextPageError
                    ? query.fetchNextPage()
                    : query.refetch())
                }
              >
                Retry
              </button>
            </p>
          ) : query.isPending || query.hasNextPage ? (
            <div role="status" aria-label="Loading trace" className="p-4">
              <Skeleton className="h-48 w-full" />
            </div>
          ) : (
            <p role="status" className="p-4 text-sm text-muted-foreground">
              Trace not found in this task’s captured content.
            </p>
          )}
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
        <h3 className="font-medium">
          <ModelLabel id={row.model} />
        </h3>
        {row.usage ? (
          <p className="text-xs">Usage: {JSON.stringify(row.usage)}</p>
        ) : null}
        {content.isPending ? (
          <div
            role="status"
            aria-label="Loading trace content"
            className="space-y-3"
          >
            {[0, 1].map((key) => (
              <div key={key} className="space-y-2">
                <Skeleton className="h-5 w-24" />
                <Skeleton className="h-48 w-full" />
              </div>
            ))}
          </div>
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
