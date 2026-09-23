import { useQuery } from "@tanstack/react-query";
import { useSearch } from "@tanstack/react-router";
import {
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  RefreshCw,
  Search,
  TerminalSquare,
} from "lucide-react";
import { useDeferredValue, useState } from "react";

import {
  apiKeysQuery,
  generationLogsQuery,
  modelsQuery,
  type GenerationLog,
} from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useProductContext } from "@/hooks/use-product-context";
import { formatLatency, formatNanoUsd } from "@/lib/format";
import { ConsolePage, LoadFailed } from "@/pages/console-page";
import {
  GenerationDetails,
  StatusBadge,
  generationLatency,
} from "@/pages/generation-details";
import {
  ALL,
  LOG_PAGE_SIZE,
  RANGE_OPTIONS,
  SORT_OPTIONS,
  STATUS_OPTIONS,
  dateRange,
  firstPage,
  generationLogParams,
  logQueryKey,
  nextPage,
  pageCursors,
  previousPage,
  type LogFilters,
  type RangeKey,
} from "@/pages/logs-filters";
import { OptionSelect, type Option } from "@/pages/option-select";

const completedTime = new Intl.DateTimeFormat(undefined, {
  hour: "numeric",
  minute: "2-digit",
});

const completedDay = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

const compactId = (id: string) => `${id.slice(0, 8)}…${id.slice(-6)}`;

const namedOptions = (
  items: readonly { id: string; name: string }[] | undefined,
): Option<string>[] =>
  (items ?? []).map((item) => ({ value: item.id, label: item.name }));

export const LogsPage = () => {
  const context = useProductContext();
  const searchParams = useSearch({ from: "/logs" });
  const [rangeKey, setRangeKey] = useState<RangeKey>("24h");
  const [rangeEnd, setRangeEnd] = useState(() => new Date());
  const [status, setStatus] = useState<LogFilters["status"]>(ALL);
  const [model, setModel] = useState<string>(ALL);
  const [apiKeyId, setApiKeyId] = useState(searchParams.apiKeyId ?? ALL);
  const [sort, setSort] = useState<LogFilters["sort"]>("newest");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<GenerationLog | null>(null);
  const deferredSearch = useDeferredValue(search.trim());
  const range = dateRange(rangeKey, rangeEnd);

  const filters: LogFilters = {
    range: rangeKey,
    status,
    model,
    apiKeyId,
    sort,
    search: deferredSearch,
  };
  const queryKey = logQueryKey(filters, range);
  const [pages, setPages] = useState(() => firstPage(queryKey));
  const cursors = pageCursors(pages, queryKey);
  const cursor = cursors.at(-1);

  const models = useQuery(modelsQuery());
  const apiKeys = useQuery(
    apiKeysQuery(context.organizationId, context.workspaceId),
  );
  const logs = useQuery({
    ...generationLogsQuery(
      context.organizationId,
      context.workspaceId,
      generationLogParams(filters, range, cursor),
    ),
    placeholderData: (previous) => previous,
  });
  const nextCursor = logs.data?.next_cursor;

  const showNextPage = () => {
    if (!nextCursor) return;

    setPages(nextPage(pages, queryKey, nextCursor));
  };

  const showPreviousPage = () => {
    setPages(previousPage(pages, queryKey));
  };

  const selectRange = (key: RangeKey) => {
    setRangeKey(key);
    setRangeEnd(new Date());
  };

  return (
    <ConsolePage
      page="logs"
      title="Logs"
      description="Inspect request status, token usage, timing, and cost."
      width="wide"
    >
      <div className="mb-4 flex flex-col gap-2 rounded-lg border bg-card p-2 shadow-xs xl:flex-row xl:items-center">
        <div className="relative min-w-0 flex-1 xl:max-w-lg">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="pl-9"
            placeholder="Search generation ID, external ID, or model"
            aria-label="Search logs"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <OptionSelect
            value={rangeKey}
            options={RANGE_OPTIONS}
            onValueChange={selectRange}
            className="min-w-32"
          />
          <OptionSelect
            value={status}
            options={STATUS_OPTIONS}
            onValueChange={setStatus}
            className="min-w-32"
          />
          <OptionSelect
            value={model}
            options={[
              { value: ALL, label: "All models" },
              ...namedOptions(models.data?.data),
            ]}
            onValueChange={setModel}
            className="min-w-44"
          />
          <OptionSelect
            value={apiKeyId}
            options={[
              { value: ALL, label: "All API keys" },
              ...namedOptions(apiKeys.data?.data),
            ]}
            onValueChange={setApiKeyId}
            label="API key"
            className="min-w-40"
          />
          <OptionSelect
            value={sort}
            options={SORT_OPTIONS}
            onValueChange={setSort}
            className="min-w-36"
          />
        </div>
      </div>

      <section className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <div className="flex h-12 items-center justify-between border-b px-4 text-xs text-muted-foreground">
          <span>{logs.data?.data.length ?? 0} results</span>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Refresh logs"
            onClick={() => setRangeEnd(new Date())}
          >
            <RefreshCw className={logs.isFetching ? "animate-spin" : ""} />
          </Button>
        </div>
        {logs.isLoading ? (
          <div className="grid min-h-80 place-items-center">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : logs.isError ? (
          <LoadFailed
            subject="logs"
            retrying={logs.isFetching}
            onRetry={() => void logs.refetch()}
            className="min-h-80"
          />
        ) : logs.data?.data.length ? (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/35 hover:bg-muted/35">
                <TableHead className="w-28 px-4">Status</TableHead>
                <TableHead>Generation</TableHead>
                <TableHead>Model</TableHead>
                <TableHead className="hidden md:table-cell">Tokens</TableHead>
                <TableHead className="hidden lg:table-cell">Latency</TableHead>
                <TableHead className="hidden lg:table-cell">Cost</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.data.data.map((generation) => (
                <TableRow
                  key={generation.id}
                  className="cursor-pointer"
                  onClick={() => setSelected(generation)}
                >
                  <TableCell className="px-4">
                    <StatusBadge status={generation.status} />
                  </TableCell>
                  <TableCell>
                    <button
                      type="button"
                      className="rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                    >
                      <code className="text-xs font-medium">
                        {compactId(generation.id)}
                      </code>
                    </button>
                    {generation.external_id ? (
                      <p className="mt-1 max-w-40 truncate text-xs text-muted-foreground">
                        {generation.external_id}
                      </p>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <span className="block max-w-52 truncate text-xs font-medium">
                      {generation.model_id}
                    </span>
                  </TableCell>
                  <TableCell className="hidden tabular-nums md:table-cell">
                    {(
                      generation.input_tokens + generation.output_tokens
                    ).toLocaleString()}
                  </TableCell>
                  <TableCell className="hidden tabular-nums lg:table-cell">
                    {formatLatency(generationLatency(generation))}
                  </TableCell>
                  <TableCell className="hidden tabular-nums lg:table-cell">
                    {formatNanoUsd(generation.charge)}
                  </TableCell>
                  <TableCell>
                    <span className="text-xs">
                      {completedTime.format(new Date(generation.completed_at))}
                    </span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {completedDay.format(new Date(generation.completed_at))}
                    </span>
                  </TableCell>
                  <TableCell>
                    <ChevronRight className="size-4 text-muted-foreground" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="grid min-h-80 place-items-center px-6 text-center">
            <div>
              <TerminalSquare className="mx-auto size-5 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium">No logs found</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Change the filters or make a request in this workspace.
              </p>
            </div>
          </div>
        )}
        <div className="flex h-14 items-center justify-between border-t px-4">
          <span className="text-xs text-muted-foreground">
            {LOG_PAGE_SIZE} rows per page
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon-sm"
              disabled={!cursors.length || logs.isFetching}
              onClick={showPreviousPage}
              aria-label="Previous page"
            >
              <ChevronLeft />
            </Button>
            <span className="min-w-6 text-center text-xs font-medium">
              {cursors.length + 1}
            </span>
            <Button
              variant="outline"
              size="icon-sm"
              disabled={!nextCursor || logs.isFetching}
              onClick={showNextPage}
              aria-label="Next page"
            >
              <ChevronRight />
            </Button>
          </div>
        </div>
      </section>

      <Sheet
        open={Boolean(selected)}
        onOpenChange={(open) => !open && setSelected(null)}
      >
        {selected ? <GenerationDetails generation={selected} /> : null}
      </Sheet>
    </ConsolePage>
  );
};
