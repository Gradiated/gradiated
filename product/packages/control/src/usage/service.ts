import type { ClickHouseClient } from "@clickhouse/client";
import { and, eq, isNull } from "drizzle-orm";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import { organizationMembers, workspaces } from "../db/schema/index.js";
import { ControlServiceError } from "../workspaces/service.js";

const unsignedStringSchema = z
  .union([z.string().regex(/^\d+$/), z.number().int().nonnegative()])
  .transform(String);

const usagePointRowSchema = z.strictObject({
  date: z.string(),
  charge: unsignedStringSchema,
  input_tokens: unsignedStringSchema,
  output_tokens: unsignedStringSchema,
  generation_count: unsignedStringSchema,
});

const modelUsageRowSchema = usagePointRowSchema.omit({ date: true }).extend({
  model_id: z.string(),
});

const usageTotalRowSchema = usagePointRowSchema
  .omit({ date: true })
  .extend({ succeeded_count: unsignedStringSchema });

const generationRowSchema = z.strictObject({
  id: z.uuid(),
  external_id: z.string().nullable(),
  model_id: z.string(),
  status: z.enum(["succeeded", "failed", "cancelled", "abandoned"]),
  streamed: z.coerce.number().int().min(0).max(1).transform(Boolean),
  charge: unsignedStringSchema,
  input_tokens: z.coerce.number().int().nonnegative(),
  cached_input_tokens: z.coerce.number().int().nonnegative(),
  cache_write_tokens: z.coerce.number().int().nonnegative(),
  output_tokens: z.coerce.number().int().nonnegative(),
  reasoning_tokens: z.coerce.number().int().nonnegative(),
  finish_reason: z.string().nullable(),
  error_code: z.string().nullable(),
  usable_output_delivered: z.coerce
    .number()
    .int()
    .min(0)
    .max(1)
    .transform(Boolean),
  cancellation_owner: z.enum(["client", "server", "runtime"]).nullable(),
  received_at: z.iso.datetime({ offset: true }),
  started_at: z.iso.datetime({ offset: true }).nullable(),
  first_token_at: z.iso.datetime({ offset: true }).nullable(),
  completed_at: z.iso.datetime({ offset: true }),
});

type UsagePointRecord = z.infer<typeof usagePointRowSchema>;
type ModelUsageRecord = z.infer<typeof modelUsageRowSchema>;
export type GenerationLogRecord = z.infer<typeof generationRowSchema>;

export type UsageSummaryRecord = {
  charge: string;
  inputTokens: string;
  outputTokens: string;
  generationCount: string;
  succeededCount: string;
  daily: UsagePointRecord[];
  models: ModelUsageRecord[];
};

export type UsageRange = {
  from: Date;
  to: Date;
};

export interface UsageService {
  getSummary(input: {
    userId: string;
    organizationId: string;
    workspaceId: string;
    range: UsageRange;
  }): Promise<UsageSummaryRecord>;
  listGenerations(input: {
    userId: string;
    organizationId: string;
    workspaceId: string;
    range: UsageRange;
    cursor?: string;
    limit: number;
    apiKeyId?: string;
    model?: string;
    search?: string;
    sort: "newest" | "highest_cost";
    status?: GenerationLogRecord["status"];
  }): Promise<{ data: GenerationLogRecord[]; nextCursor: string | null }>;
}

const cursorSchema = z.strictObject({
  charge: z.string().regex(/^\d+$/).optional(),
  completedAt: z.iso.datetime({ offset: true }),
  id: z.uuid(),
  sort: z.enum(["newest", "highest_cost"]),
});

const decodeCursor = (cursor: string, sort: "newest" | "highest_cost") => {
  try {
    const decoded = cursorSchema.parse(
      JSON.parse(Buffer.from(cursor, "base64url").toString("utf8")),
    );
    if (decoded.sort !== sort || (sort === "highest_cost" && !decoded.charge)) {
      throw new Error("The cursor sort does not match the request.");
    }
    return decoded;
  } catch (error) {
    throw new ControlServiceError(
      "not_found",
      "The page cursor is invalid.",
      error,
    );
  }
};

const encodeCursor = (
  generation: GenerationLogRecord,
  sort: "newest" | "highest_cost",
) =>
  Buffer.from(
    JSON.stringify({
      ...(sort === "highest_cost" ? { charge: generation.charge } : {}),
      completedAt: generation.completed_at,
      id: generation.id,
      sort,
    }),
    "utf8",
  ).toString("base64url");

const usageUnavailable = (error: unknown) => {
  if (error instanceof ControlServiceError) return error;
  return new ControlServiceError(
    "unavailable",
    "Usage data is temporarily unavailable.",
    error,
  );
};

const clickHouseDateTime = (value: Date | string) =>
  new Date(value).toISOString().replace("T", " ").replace("Z", "");

export const createUsageService = (
  database: ControlDatabase,
  clickhouse: ClickHouseClient,
): UsageService => {
  const requireWorkspaceAccess = async (
    userId: string,
    organizationId: string,
    workspaceId: string,
  ) => {
    const [access] = await database
      .select({ workspaceId: workspaces.id })
      .from(organizationMembers)
      .innerJoin(
        workspaces,
        and(
          eq(workspaces.organizationId, organizationMembers.organizationId),
          eq(workspaces.id, workspaceId),
        ),
      )
      .where(
        and(
          eq(organizationMembers.userId, userId),
          eq(organizationMembers.organizationId, organizationId),
          eq(organizationMembers.status, "active"),
          isNull(workspaces.archivedAt),
        ),
      )
      .limit(1);

    if (!access) {
      throw new ControlServiceError(
        "not_found",
        "The workspace does not exist or is not accessible.",
      );
    }
  };

  const rangeParameters = (input: {
    organizationId: string;
    workspaceId: string;
    range: UsageRange;
  }) => ({
    organization_id: input.organizationId,
    workspace_id: input.workspaceId,
    from: clickHouseDateTime(input.range.from),
    to: clickHouseDateTime(input.range.to),
  });

  return {
    async getSummary(input) {
      await requireWorkspaceAccess(
        input.userId,
        input.organizationId,
        input.workspaceId,
      );
      try {
        const queryParams = rangeParameters(input);
        const [totalResult, dailyResult, modelResult] = await Promise.all([
          clickhouse.query({
            query: `
            SELECT
              sum(charge) AS charge,
              sum(toUInt64(getSubcolumn(properties, 'usage.input_tokens'))) AS input_tokens,
              sum(toUInt64(getSubcolumn(properties, 'usage.output_tokens'))) AS output_tokens,
              count() AS generation_count,
              countIf(status = 'succeeded') AS succeeded_count
            FROM generations
            WHERE organization_id = {organization_id:UUID}
              AND workspace_id = {workspace_id:UUID}
              AND completed_at >= {from:DateTime64(6, 'UTC')}
              AND completed_at < {to:DateTime64(6, 'UTC')}
          `,
            query_params: queryParams,
            format: "JSONEachRow",
          }),
          clickhouse.query({
            query: `
            SELECT
              toString(toDate(completed_at, 'UTC')) AS date,
              sum(charge) AS charge,
              sum(toUInt64(getSubcolumn(properties, 'usage.input_tokens'))) AS input_tokens,
              sum(toUInt64(getSubcolumn(properties, 'usage.output_tokens'))) AS output_tokens,
              count() AS generation_count
            FROM generations
            WHERE organization_id = {organization_id:UUID}
              AND workspace_id = {workspace_id:UUID}
              AND completed_at >= {from:DateTime64(6, 'UTC')}
              AND completed_at < {to:DateTime64(6, 'UTC')}
            GROUP BY date
            ORDER BY date
          `,
            query_params: queryParams,
            format: "JSONEachRow",
          }),
          clickhouse.query({
            query: `
            SELECT
              model_id,
              sum(charge) AS charge,
              sum(toUInt64(getSubcolumn(properties, 'usage.input_tokens'))) AS input_tokens,
              sum(toUInt64(getSubcolumn(properties, 'usage.output_tokens'))) AS output_tokens,
              count() AS generation_count
            FROM generations
            WHERE organization_id = {organization_id:UUID}
              AND workspace_id = {workspace_id:UUID}
              AND completed_at >= {from:DateTime64(6, 'UTC')}
              AND completed_at < {to:DateTime64(6, 'UTC')}
            GROUP BY model_id
            ORDER BY charge DESC, model_id
          `,
            query_params: queryParams,
            format: "JSONEachRow",
          }),
        ]);

        const [total] = usageTotalRowSchema
          .array()
          .parse(await totalResult.json());
        const daily = usagePointRowSchema
          .array()
          .parse(await dailyResult.json());
        const models = modelUsageRowSchema
          .array()
          .parse(await modelResult.json());
        return {
          charge: total?.charge ?? "0",
          inputTokens: total?.input_tokens ?? "0",
          outputTokens: total?.output_tokens ?? "0",
          generationCount: total?.generation_count ?? "0",
          succeededCount: total?.succeeded_count ?? "0",
          daily,
          models,
        };
      } catch (error) {
        throw usageUnavailable(error);
      }
    },

    async listGenerations(input) {
      await requireWorkspaceAccess(
        input.userId,
        input.organizationId,
        input.workspaceId,
      );
      try {
        const cursor = input.cursor
          ? decodeCursor(input.cursor, input.sort)
          : undefined;
        const filters = [
          "g.organization_id = {organization_id:UUID}",
          "g.workspace_id = {workspace_id:UUID}",
          "g.completed_at >= {from:DateTime64(6, 'UTC')}",
          "g.completed_at < {to:DateTime64(6, 'UTC')}",
        ];
        if (input.apiKeyId) {
          filters.push("g.api_key_id = {api_key_id:UUID}");
        }
        if (input.model) filters.push("g.model_id = {model:String}");
        if (input.search) {
          filters.push(
            "(startsWith(toString(g.id), {search:String}) OR positionCaseInsensitive(g.model_id, {search:String}) > 0 OR positionCaseInsensitive(toString(getSubcolumn(g.properties, 'external_id')), {search:String}) > 0)",
          );
        }
        if (input.status) filters.push("g.status = {status:String}");
        if (cursor) {
          filters.push(
            input.sort === "highest_cost"
              ? "(g.charge < {cursor_charge:Int64} OR (g.charge = {cursor_charge:Int64} AND (g.completed_at < {cursor_time:DateTime64(6, 'UTC')} OR (g.completed_at = {cursor_time:DateTime64(6, 'UTC')} AND g.id < {cursor_id:UUID}))))"
              : "(g.completed_at < {cursor_time:DateTime64(6, 'UTC')} OR (g.completed_at = {cursor_time:DateTime64(6, 'UTC')} AND g.id < {cursor_id:UUID}))",
          );
        }
        const orderBy =
          input.sort === "highest_cost"
            ? "g.charge DESC, g.completed_at DESC, g.id DESC"
            : "g.completed_at DESC, g.id DESC";

        const result = await clickhouse.query({
          query: `
          SELECT
            toString(id) AS id,
            nullIf(toString(getSubcolumn(properties, 'external_id')), '') AS external_id,
            model_id,
            status,
            toUInt8(getSubcolumn(properties, 'streamed')) AS streamed,
            charge,
            toUInt64(getSubcolumn(properties, 'usage.input_tokens')) AS input_tokens,
            toUInt64(getSubcolumn(properties, 'usage.cached_input_tokens')) AS cached_input_tokens,
            toUInt64(getSubcolumn(properties, 'usage.cache_write_tokens')) AS cache_write_tokens,
            toUInt64(getSubcolumn(properties, 'usage.output_tokens')) AS output_tokens,
            toUInt64(getSubcolumn(properties, 'usage.reasoning_tokens')) AS reasoning_tokens,
            nullIf(toString(getSubcolumn(properties, 'outcome.finish_reason')), '') AS finish_reason,
            nullIf(toString(getSubcolumn(properties, 'outcome.error_code')), '') AS error_code,
            toUInt8(getSubcolumn(properties, 'outcome.usable_output_delivered')) AS usable_output_delivered,
            nullIf(toString(getSubcolumn(properties, 'outcome.cancellation_owner')), '') AS cancellation_owner,
            formatDateTime(getSubcolumn(properties, 'timing.received_at'), '%Y-%m-%dT%H:%i:%S.%fZ', 'UTC') AS received_at,
            if(isNull(getSubcolumn(properties, 'timing.started_at')), NULL, formatDateTime(getSubcolumn(properties, 'timing.started_at'), '%Y-%m-%dT%H:%i:%S.%fZ', 'UTC')) AS started_at,
            if(isNull(getSubcolumn(properties, 'timing.first_token_at')), NULL, formatDateTime(getSubcolumn(properties, 'timing.first_token_at'), '%Y-%m-%dT%H:%i:%S.%fZ', 'UTC')) AS first_token_at,
            formatDateTime(g.completed_at, '%Y-%m-%dT%H:%i:%S.%fZ', 'UTC') AS completed_at
          FROM generations AS g
          WHERE ${filters.join("\n            AND ")}
          ORDER BY ${orderBy}
          LIMIT {limit:UInt16}
        `,
          query_params: {
            ...rangeParameters(input),
            limit: input.limit + 1,
            ...(cursor
              ? {
                  cursor_id: cursor.id,
                  ...(cursor.charge ? { cursor_charge: cursor.charge } : {}),
                  cursor_time: clickHouseDateTime(cursor.completedAt),
                }
              : {}),
            ...(input.model ? { model: input.model } : {}),
            ...(input.apiKeyId ? { api_key_id: input.apiKeyId } : {}),
            ...(input.search ? { search: input.search } : {}),
            ...(input.status ? { status: input.status } : {}),
          },
          format: "JSONEachRow",
        });
        const rows = generationRowSchema.array().parse(await result.json());
        const hasNextPage = rows.length > input.limit;
        const data = rows.slice(0, input.limit);
        return {
          data,
          nextCursor:
            hasNextPage && data.length
              ? encodeCursor(data[data.length - 1]!, input.sort)
              : null,
        };
      } catch (error) {
        throw usageUnavailable(error);
      }
    },
  };
};
