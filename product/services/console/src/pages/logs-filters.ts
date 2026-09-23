import type { GenerationLogQuery } from "@/api/queries";
import type { Option } from "@/pages/option-select";

export const LOG_PAGE_SIZE = 25;

export const ALL = "all";

export const RANGE_OPTIONS = [
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
] as const satisfies readonly Option<string>[];

export const STATUS_OPTIONS = [
  { value: ALL, label: "All statuses" },
  { value: "succeeded", label: "Succeeded" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
  { value: "abandoned", label: "Abandoned" },
] as const satisfies readonly Option<
  typeof ALL | NonNullable<GenerationLogQuery["status"]>
>[];

export const SORT_OPTIONS = [
  { value: "newest", label: "Newest first" },
  { value: "highest_cost", label: "Highest cost" },
] as const satisfies readonly Option<NonNullable<GenerationLogQuery["sort"]>>[];

export type RangeKey = (typeof RANGE_OPTIONS)[number]["value"];

export interface LogFilters {
  range: RangeKey;
  status: (typeof STATUS_OPTIONS)[number]["value"];
  model: string;
  apiKeyId: string;
  sort: (typeof SORT_OPTIONS)[number]["value"];
  search: string;
}

const RANGE_HOURS: Record<RangeKey, number> = {
  "24h": 24,
  "7d": 7 * 24,
  "30d": 30 * 24,
};

export interface DateRange {
  from: string;
  to: string;
}

export const dateRange = (key: RangeKey, now: Date): DateRange => {
  const from = new Date(now);
  from.setUTCHours(from.getUTCHours() - RANGE_HOURS[key]);

  return { from: from.toISOString(), to: now.toISOString() };
};

export const generationLogParams = (
  filters: LogFilters,
  range: DateRange,
  cursor: string | undefined,
): GenerationLogQuery => {
  const params: GenerationLogQuery = {
    ...range,
    limit: LOG_PAGE_SIZE,
    sort: filters.sort,
  };

  if (cursor) params.cursor = cursor;
  if (filters.status !== ALL) params.status = filters.status;
  if (filters.model !== ALL) params.model = filters.model;
  if (filters.apiKeyId !== ALL) params.api_key_id = filters.apiKeyId;
  if (filters.search) params.search = filters.search;

  return params;
};

export interface LogPages {
  queryKey: string;
  cursors: readonly string[];
}

export const logQueryKey = (filters: LogFilters, range: DateRange) =>
  JSON.stringify(generationLogParams(filters, range, undefined));

export const firstPage = (queryKey: string): LogPages => ({
  queryKey,
  cursors: [],
});

export const pageCursors = (
  pages: LogPages,
  queryKey: string,
): readonly string[] => (pages.queryKey === queryKey ? pages.cursors : []);

export const nextPage = (
  pages: LogPages,
  queryKey: string,
  nextCursor: string,
): LogPages => ({
  queryKey,
  cursors: [...pageCursors(pages, queryKey), nextCursor],
});

export const previousPage = (pages: LogPages, queryKey: string): LogPages => ({
  queryKey,
  cursors: pageCursors(pages, queryKey).slice(0, -1),
});
