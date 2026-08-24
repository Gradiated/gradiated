import { useQuery } from "@tanstack/react-query";
import { useSearch } from "@tanstack/react-router";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  LoaderCircle,
  Search,
  TerminalSquare,
} from "lucide-react";
import {
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  listGenerationLogs,
  listApiKeys,
  listModels,
  type GenerationLog,
} from "@/api/queries";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
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
import { useProductContext } from "@/hooks/use-product-context";
import { formatNanoUsd } from "@/lib/format";

type RangeKey = "24h" | "7d" | "30d";
type SortKey = "newest" | "highest_cost";
type StatusFilter = "all" | GenerationLog["status"];

const dateRange = (key: RangeKey) => {
  const to = new Date();
  const from = new Date(to);
  if (key === "24h") from.setUTCHours(from.getUTCHours() - 24);
  else from.setUTCDate(from.getUTCDate() - (key === "7d" ? 7 : 30));
  return { from: from.toISOString(), to: to.toISOString() };
};

const duration = (generation: GenerationLog) => {
  const milliseconds =
    new Date(generation.completed_at).getTime() -
    new Date(generation.received_at).getTime();
  if (milliseconds < 1_000) return `${milliseconds} ms`;
  return `${(milliseconds / 1_000).toFixed(milliseconds < 10_000 ? 2 : 1)} s`;
};

const dateTime = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));

const preciseDateTime = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  }).format(new Date(value));

const compactId = (id: string) => `${id.slice(0, 8)}…${id.slice(-6)}`;

export const LogsPage = () => {
  const context = useProductContext();
  const searchParams = useSearch({ from: "/logs" });
  const [rangeKey, setRangeKey] = useState<RangeKey>("24h");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [model, setModel] = useState("all");
  const [apiKey, setApiKey] = useState(searchParams.apiKeyId ?? "all");
  const [sort, setSort] = useState<SortKey>("newest");
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [cursorHistory, setCursorHistory] = useState<string[]>([]);
  const [selected, setSelected] = useState<GenerationLog | null>(null);
  const deferredSearch = useDeferredValue(search.trim());
  const range = useMemo(() => dateRange(rangeKey), [rangeKey]);
  const models = useQuery({ queryKey: ["models"], queryFn: listModels });
  const apiKeys = useQuery({
    queryKey: ["api-keys", context.organizationId, context.workspaceId],
    queryFn: () => listApiKeys(context.organizationId, context.workspaceId),
    enabled: Boolean(context.organizationId && context.workspaceId),
  });
  const logs = useQuery({
    queryKey: [
      "generation-logs",
      context.organizationId,
      context.workspaceId,
      rangeKey,
      status,
      model,
      apiKey,
      sort,
      deferredSearch,
      cursor,
    ],
    queryFn: () =>
      listGenerationLogs(context.organizationId, context.workspaceId, {
        ...range,
        limit: 25,
        sort,
        ...(cursor ? { cursor } : {}),
        ...(apiKey !== "all" ? { api_key_id: apiKey } : {}),
        ...(model !== "all" ? { model } : {}),
        ...(status !== "all" ? { status } : {}),
        ...(deferredSearch ? { search: deferredSearch } : {}),
      }),
    enabled: Boolean(context.organizationId && context.workspaceId),
    placeholderData: (previous) => previous,
  });

  useEffect(() => {
    setCursor(undefined);
    setCursorHistory([]);
  }, [apiKey, deferredSearch, model, rangeKey, sort, status]);

  const nextPage = () => {
    if (!logs.data?.next_cursor) return;
    setCursorHistory((current) => [...current, cursor ?? ""]);
    setCursor(logs.data.next_cursor);
  };

  const previousPage = () => {
    const previous = cursorHistory[cursorHistory.length - 1];
    setCursor(previous || undefined);
    setCursorHistory((current) => current.slice(0, -1));
  };

  return (
    <AppShell
      user={context.user}
      organizationId={context.organizationId}
      workspaces={context.workspaces}
      workspaceId={context.workspaceId}
      onSelectOrganization={context.selectOrganization}
      onSelectWorkspace={context.selectWorkspace}
      onSignOut={context.signOut}
      activePage="logs"
      pageTitle="Logs"
    >
      <main className="min-w-0 flex-1 px-5 py-8 lg:px-10 lg:py-10">
        <div className="mx-auto w-full max-w-7xl">
          <div className="mb-7">
            <h1 className="text-3xl font-semibold tracking-[-0.035em]">Logs</h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Inspect request status, token usage, timing, and cost.
            </p>
          </div>

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
              <Select
                value={rangeKey}
                onValueChange={(value) => setRangeKey(value as RangeKey)}
              >
                <SelectTrigger className="min-w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="24h">Last 24 hours</SelectItem>
                  <SelectItem value="7d">Last 7 days</SelectItem>
                  <SelectItem value="30d">Last 30 days</SelectItem>
                </SelectContent>
              </Select>
              <Select
                value={status}
                onValueChange={(value) => setStatus(value as StatusFilter)}
              >
                <SelectTrigger className="min-w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="succeeded">Succeeded</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                  <SelectItem value="abandoned">Abandoned</SelectItem>
                </SelectContent>
              </Select>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="min-w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All models</SelectItem>
                  {models.data?.data.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={apiKey} onValueChange={setApiKey}>
                <SelectTrigger className="min-w-40" aria-label="API key">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All API keys</SelectItem>
                  {apiKeys.data?.data.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={sort}
                onValueChange={(value) => setSort(value as SortKey)}
              >
                <SelectTrigger className="min-w-36">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="newest">Newest first</SelectItem>
                  <SelectItem value="highest_cost">Highest cost</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {logs.isError ? (
            <div className="mb-4 rounded-lg border border-destructive/25 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {logs.error.message}
            </div>
          ) : null}

          <section className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <div className="flex h-12 items-center justify-between border-b px-4 text-xs text-muted-foreground">
              <span>{logs.data?.data.length ?? 0} results</span>
              {logs.isFetching ? (
                <span className="flex items-center gap-2">
                  <LoaderCircle className="size-3.5 animate-spin" /> Updating
                </span>
              ) : null}
            </div>
            {logs.isLoading ? (
              <div className="grid min-h-80 place-items-center">
                <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
              </div>
            ) : logs.data?.data.length ? (
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/35 hover:bg-muted/35">
                    <TableHead className="w-28 px-4">Status</TableHead>
                    <TableHead>Generation</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead className="hidden md:table-cell">
                      Tokens
                    </TableHead>
                    <TableHead className="hidden lg:table-cell">
                      Latency
                    </TableHead>
                    <TableHead className="hidden lg:table-cell">Cost</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.data.data.map((generation) => (
                    <TableRow
                      key={generation.id}
                      role="button"
                      tabIndex={0}
                      className="cursor-pointer"
                      onClick={() => setSelected(generation)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelected(generation);
                        }
                      }}
                    >
                      <TableCell className="px-4">
                        <StatusBadge status={generation.status} />
                      </TableCell>
                      <TableCell>
                        <code className="text-xs font-medium">
                          {compactId(generation.id)}
                        </code>
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
                        {duration(generation)}
                      </TableCell>
                      <TableCell className="hidden tabular-nums lg:table-cell">
                        {formatNanoUsd(generation.charge)}
                      </TableCell>
                      <TableCell>
                        <span className="text-xs">
                          {new Intl.DateTimeFormat(undefined, {
                            hour: "numeric",
                            minute: "2-digit",
                          }).format(new Date(generation.completed_at))}
                        </span>
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {new Intl.DateTimeFormat(undefined, {
                            month: "short",
                            day: "numeric",
                          }).format(new Date(generation.completed_at))}
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
                25 rows per page
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="icon-sm"
                  disabled={!cursorHistory.length || logs.isFetching}
                  onClick={previousPage}
                  aria-label="Previous page"
                >
                  <ChevronLeft />
                </Button>
                <span className="min-w-6 text-center text-xs font-medium">
                  {cursorHistory.length + 1}
                </span>
                <Button
                  variant="outline"
                  size="icon-sm"
                  disabled={!logs.data?.next_cursor || logs.isFetching}
                  onClick={nextPage}
                  aria-label="Next page"
                >
                  <ChevronRight />
                </Button>
              </div>
            </div>
          </section>
        </div>
      </main>

      <Sheet
        open={Boolean(selected)}
        onOpenChange={(open) => !open && setSelected(null)}
      >
        {selected ? <GenerationDetails generation={selected} /> : null}
      </Sheet>
    </AppShell>
  );
};

const StatusBadge = ({ status }: { status: GenerationLog["status"] }) => {
  const styles: Record<GenerationLog["status"], string> = {
    succeeded: "border-[#cadb87] bg-[#f2f7d9] text-[#475617]",
    failed: "border-destructive/25 bg-destructive/5 text-destructive",
    cancelled: "border-border bg-muted text-muted-foreground",
    abandoned: "border-[#e4c880] bg-[#fbf3db] text-[#755b15]",
  };
  return (
    <Badge variant="outline" className={styles[status]}>
      {status === "succeeded" ? <Check /> : null}
      {status[0]?.toUpperCase()}
      {status.slice(1)}
    </Badge>
  );
};

const GenerationDetails = ({ generation }: { generation: GenerationLog }) => {
  const [copied, setCopied] = useState(false);
  const copyId = async () => {
    await navigator.clipboard.writeText(generation.id);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_200);
  };
  const firstToken = generation.first_token_at
    ? new Date(generation.first_token_at).getTime() -
      new Date(generation.received_at).getTime()
    : null;

  return (
    <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-xl">
      <SheetHeader className="border-b p-6 pr-12">
        <div className="flex items-center gap-2">
          <StatusBadge status={generation.status} />
          <span className="text-xs text-muted-foreground">
            {dateTime(generation.completed_at)}
          </span>
        </div>
        <SheetTitle className="mt-3 flex items-center gap-2 font-mono text-sm font-medium">
          {generation.id}
          <button
            type="button"
            onClick={copyId}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Copy generation ID"
          >
            {copied ? (
              <Check className="size-3.5" />
            ) : (
              <Copy className="size-3.5" />
            )}
          </button>
        </SheetTitle>
        <SheetDescription>Request details and measured usage.</SheetDescription>
      </SheetHeader>

      <div className="space-y-7 p-6">
        <DetailSection title="Overview">
          <DetailGrid>
            <Detail label="Model" value={generation.model_id} />
            <Detail label="Cost" value={formatNanoUsd(generation.charge)} />
            <Detail label="Latency" value={duration(generation)} />
            <Detail
              label="Streamed"
              value={generation.streamed ? "Yes" : "No"}
            />
          </DetailGrid>
        </DetailSection>

        <Separator />
        <DetailSection title="Token usage">
          <DetailGrid>
            <Detail
              label="Input"
              value={generation.input_tokens.toLocaleString()}
            />
            <Detail
              label="Output"
              value={generation.output_tokens.toLocaleString()}
            />
            <Detail
              label="Cached input"
              value={generation.cached_input_tokens.toLocaleString()}
            />
            <Detail
              label="Reasoning"
              value={generation.reasoning_tokens.toLocaleString()}
            />
          </DetailGrid>
        </DetailSection>

        <Separator />
        <DetailSection title="Outcome">
          <dl className="divide-y rounded-lg border">
            <Property
              label="Finish reason"
              value={generation.finish_reason ?? "—"}
            />
            <Property label="Error code" value={generation.error_code ?? "—"} />
            <Property
              label="Output delivered"
              value={generation.usable_output_delivered ? "Yes" : "No"}
            />
            <Property
              label="Cancellation owner"
              value={generation.cancellation_owner ?? "—"}
            />
            <Property
              label="External ID"
              value={generation.external_id ?? "—"}
            />
          </dl>
        </DetailSection>

        <Separator />
        <DetailSection title="Timing">
          <dl className="divide-y rounded-lg border">
            <Property
              label="Received"
              value={preciseDateTime(generation.received_at)}
            />
            <Property
              label="Started"
              value={
                generation.started_at
                  ? preciseDateTime(generation.started_at)
                  : "—"
              }
            />
            <Property
              label="Time to first token"
              value={
                firstToken === null ? "—" : `${firstToken.toLocaleString()} ms`
              }
            />
            <Property
              label="Completed"
              value={preciseDateTime(generation.completed_at)}
            />
          </dl>
        </DetailSection>
      </div>
    </SheetContent>
  );
};

const DetailSection = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) => (
  <section>
    <h3 className="mb-3 text-sm font-medium">{title}</h3>
    {children}
  </section>
);

const DetailGrid = ({ children }: { children: ReactNode }) => (
  <dl className="grid grid-cols-2 gap-x-6 gap-y-5">{children}</dl>
);

const Detail = ({ label, value }: { label: string; value: string }) => (
  <div className="min-w-0">
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd className="mt-1 truncate text-sm font-medium">{value}</dd>
  </div>
);

const Property = ({ label, value }: { label: string; value: string }) => (
  <div className="flex items-center justify-between gap-4 px-3 py-2.5 text-xs">
    <dt className="text-muted-foreground">{label}</dt>
    <dd className="max-w-[65%] truncate text-right font-medium">{value}</dd>
  </div>
);
