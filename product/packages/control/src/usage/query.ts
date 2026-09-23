import type { GenerationListQuerySchema } from "@gradiated/contracts";
import { z } from "zod";

import { ControlServiceError } from "../errors.js";

type GenerationListQuery = z.infer<typeof GenerationListQuerySchema>;

export type UsageSort = GenerationListQuery["sort"];

export type GenerationStatus = NonNullable<GenerationListQuery["status"]>;

export type UsageRange = {
  from: Date;
  to: Date;
};

export type UsageScope = {
  organizationId: string;
  workspaceId: string;
  range: UsageRange;
};

export type GenerationFilters = UsageScope & {
  apiKeyId?: string;
  model?: string;
  search?: string;
  sort: UsageSort;
  status?: GenerationStatus;
};

export type QueryFilter = {
  where: string[];
  params: Record<string, string | number>;
};

const completedAtSchema = z.iso.datetime({ offset: true });

const cursorSchema = z.discriminatedUnion("sort", [
  z.strictObject({
    completedAt: completedAtSchema,
    id: z.uuid(),
    sort: z.literal("newest"),
  }),
  z.strictObject({
    charge: z.string().regex(/^\d+$/),
    completedAt: completedAtSchema,
    id: z.uuid(),
    sort: z.literal("highest_cost"),
  }),
]);

export type GenerationCursor = z.infer<typeof cursorSchema>;

const parseJson = (text: string): unknown => {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
};

export const decodeCursor = (
  cursor: string,
  sort: UsageSort,
): GenerationCursor => {
  const parsed = cursorSchema.safeParse(
    parseJson(Buffer.from(cursor, "base64url").toString("utf8")),
  );

  if (!parsed.success || parsed.data.sort !== sort) {
    throw new ControlServiceError(
      "not_found",
      "The page cursor is invalid.",
      parsed.error,
    );
  }

  return parsed.data;
};

export const encodeCursor = (
  generation: { charge: string; completed_at: string; id: string },
  sort: UsageSort,
): string => {
  const cursor: GenerationCursor =
    sort === "highest_cost"
      ? {
          charge: generation.charge,
          completedAt: generation.completed_at,
          id: generation.id,
          sort,
        }
      : { completedAt: generation.completed_at, id: generation.id, sort };

  return Buffer.from(JSON.stringify(cursor), "utf8").toString("base64url");
};

export const clickHouseDateTime = (value: Date | string): string =>
  new Date(value).toISOString().replace("T", " ").replace("Z", "");

export const usageMeasures = `
  sum(g.charge) AS charge,
  sum(toUInt64(getSubcolumn(g.properties, 'usage.input_tokens'))) AS input_tokens,
  sum(toUInt64(getSubcolumn(g.properties, 'usage.output_tokens'))) AS output_tokens,
  count() AS generation_count`;

export const rangeFilter = (scope: UsageScope): QueryFilter => ({
  where: [
    "g.organization_id = {organization_id:UUID}",
    "g.workspace_id = {workspace_id:UUID}",
    "g.completed_at >= {from:DateTime64(6, 'UTC')}",
    "g.completed_at < {to:DateTime64(6, 'UTC')}",
  ],
  params: {
    organization_id: scope.organizationId,
    workspace_id: scope.workspaceId,
    from: clickHouseDateTime(scope.range.from),
    to: clickHouseDateTime(scope.range.to),
  },
});

const afterCursor = (cursor: GenerationCursor): QueryFilter => {
  const afterTime =
    "(g.completed_at < {cursor_time:DateTime64(6, 'UTC')} OR (g.completed_at = {cursor_time:DateTime64(6, 'UTC')} AND g.id < {cursor_id:UUID}))";
  const params = {
    cursor_id: cursor.id,
    cursor_time: clickHouseDateTime(cursor.completedAt),
  };

  if (cursor.sort === "newest") return { where: [afterTime], params };

  return {
    where: [
      `(g.charge < {cursor_charge:Int64} OR (g.charge = {cursor_charge:Int64} AND ${afterTime}))`,
    ],
    params: { ...params, cursor_charge: cursor.charge },
  };
};

const noFilter: QueryFilter = { where: [], params: {} };

const optionalFilter = (
  value: string | undefined,
  clause: string,
  param: string,
): QueryFilter =>
  value ? { where: [clause], params: { [param]: value } } : noFilter;

const combine = (filters: QueryFilter[]): QueryFilter => ({
  where: filters.flatMap((filter) => filter.where),
  params: Object.fromEntries(
    filters.flatMap((filter) => Object.entries(filter.params)),
  ),
});

export const generationFilter = (
  filters: GenerationFilters,
  cursor: GenerationCursor | undefined,
): QueryFilter =>
  combine([
    rangeFilter(filters),
    optionalFilter(
      filters.apiKeyId,
      "g.api_key_id = {api_key_id:UUID}",
      "api_key_id",
    ),
    optionalFilter(filters.model, "g.model_id = {model:String}", "model"),
    optionalFilter(
      filters.search,
      "(startsWith(toString(g.id), {search:String}) OR positionCaseInsensitive(g.model_id, {search:String}) > 0 OR positionCaseInsensitive(toString(getSubcolumn(g.properties, 'external_id')), {search:String}) > 0)",
      "search",
    ),
    optionalFilter(filters.status, "g.status = {status:String}", "status"),
    cursor ? afterCursor(cursor) : noFilter,
  ]);
